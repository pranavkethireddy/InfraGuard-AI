import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.app.schemas.incidents import IncidentDetail
from backend.app.schemas.predictions import PredictionResponse
from backend.app.services import simulations

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)


def cooling(client, temp, i, sim=None):
    body = {"asset_id": "cooling-01", "observed_at": (T0 + timedelta(minutes=i)).isoformat(), "data_origin": "simulated",
            "detector_id": "cooling-rule-v1", "readings": {"temperature_c": temp, "fan_speed_rpm": 900}, "simulation_id": sim}
    return client.post("/api/v1/predictions", json=body)


def test_cooling_rule_opens_one_incident_with_impact(client):
    levels = [PredictionResponse.model_validate(cooling(client, t, i).json()).risk_level
              for i, t in enumerate([24.5, 33, 34, 35, 36])]
    assert levels == ["low", "medium", "medium", "high", "high"]
    incs = client.get("/api/v1/incidents").json()
    assert incs["total"] == 1
    inc = IncidentDetail.model_validate(client.get(f"/api/v1/incidents/{incs['items'][0]['incident_id']}").json())
    assert inc.prediction_count == 2 and inc.status == "open"
    imp = inc.impact
    assert imp.estimated_downtime_cost == imp.estimated_downtime_hours * imp.cost_per_hour
    assert imp.estimated_total_impact == imp.estimated_downtime_cost + imp.estimated_repair_cost
    assert imp.cost_per_day == imp.cost_per_hour * 24 and imp.estimated_repair_hours is not None
    assert "not measured" in imp.assumptions_source
    asset = client.get("/api/v1/assets/cooling-01").json()
    assert asset["active_incident_id"] == inc.incident_id and asset["current_risk_level"] == "high"


def test_prediction_is_idempotent(client):
    a, b = cooling(client, 30, 0), cooling(client, 30, 0)
    assert a.status_code == 201 and b.status_code == 200
    assert a.json()["prediction_id"] == b.json()["prediction_id"]


def test_wrong_inputs_and_detector_are_rejected(client):
    r = client.post("/api/v1/predictions", json={"asset_id": "cooling-01", "observed_at": T0.isoformat(),
                    "data_origin": "simulated", "detector_id": "cooling-rule-v1", "readings": {"torque_nm": 40}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_FEATURES"
    r = client.post("/api/v1/predictions", json={"asset_id": "cooling-01", "observed_at": T0.isoformat(),
                    "data_origin": "simulated", "detector_id": "drive-failure-v1", "readings": {"temperature_c": 30}})
    assert r.json()["error"]["code"] == "UNSUPPORTED_DETECTOR"


def test_untrained_model_returns_503(client):
    r = client.post("/api/v1/predictions", json={"asset_id": "drive-01", "observed_at": T0.isoformat(),
                    "data_origin": "simulated", "detector_id": "drive-failure-v1", "readings": {"reallocated_sectors": 0}})
    assert r.status_code == 503 and r.json()["error"]["code"] == "MODEL_UNAVAILABLE"


DRIVE = ROOT / "ml" / "artifacts" / "backblaze" / "pipeline.joblib"


@pytest.mark.skipif(not DRIVE.is_file(), reason="drive model not trained")
def test_drive_model_scores_real_pipeline(client, settings):
    settings.drive_model_artifact_path = str(DRIVE)
    settings.drive_metrics_path = str(ROOT / "ml" / "artifacts" / "metrics" / "drive-failure-v1.json")
    base = {"asset_id": "drive-01", "data_origin": "simulated", "detector_id": "drive-failure-v1"}
    healthy = client.post("/api/v1/predictions", json={**base, "observed_at": T0.isoformat(),
                          "readings": {"reallocated_sectors": 0, "pending_sectors": 0, "power_on_hours": 20000, "temperature_c": 30}})
    sick = client.post("/api/v1/predictions", json={**base, "observed_at": (T0 + timedelta(days=1)).isoformat(),
                       "readings": {"reallocated_sectors": 5000, "pending_sectors": 800, "offline_uncorrectable": 800,
                                    "reported_uncorrectable": 300, "power_on_hours": 40000, "temperature_c": 38}})
    h, s = PredictionResponse.model_validate(healthy.json()), PredictionResponse.model_validate(sick.json())
    assert h.prediction_horizon_hours == 720 and s.risk_score > h.risk_score
    assert h.risk_level == "low" and s.risk_level == "high" and s.incident_id is not None


def test_incident_transitions_and_cooldown(client):
    for i, t in enumerate([33, 34, 35]):
        cooling(client, t, i)
    inc_id = client.get("/api/v1/incidents").json()["items"][0]["incident_id"]
    assert client.patch(f"/api/v1/incidents/{inc_id}", json={"status": "acknowledged", "note": "on it"}).status_code == 200
    r = client.patch(f"/api/v1/incidents/{inc_id}", json={"status": "resolved", "note": "filter replaced"})
    assert r.json()["status"] == "resolved" and r.json()["resolved_by"] == "operator" and len(r.json()["notes"]) == 2
    assert client.patch(f"/api/v1/incidents/{inc_id}", json={"status": "acknowledged"}).json()["error"]["code"] == "INVALID_TRANSITION"
    # Hot again straight away: cooldown blocks a new incident until 3 below-threshold readings.
    for i, t in enumerate([36, 36, 36], start=3):
        cooling(client, t, i)
    assert client.get("/api/v1/incidents?status=open").json()["total"] == 0


def fake_generate(scenario, seed, asset_id):
    return [{"temperature_c": t, "fan_speed_rpm": 900.0} for t in ([24.5] * 3 + [34.0, 35.0, 36.0, 36.5] if scenario == "cooling_anomaly" else [24.5] * 5)]


def wait_done(client, sim_id):
    for _ in range(200):
        s = client.get(f"/api/v1/simulations/{sim_id}").json()
        if s["status"] != "running":
            return s
        time.sleep(0.01)
    raise AssertionError("simulation did not finish")


def test_simulation_runs_detects_and_resets(client, settings, monkeypatch):
    monkeypatch.setattr(simulations, "_generate", fake_generate)
    settings.simulation_tick_seconds = 0.001
    r = client.post("/api/v1/simulations", json={"scenario": "cooling_anomaly", "asset_id": "cooling-01", "seed": 7})
    assert r.status_code == 201
    sim_id = r.json()["simulation_id"]
    s = wait_done(client, sim_id)
    assert s["status"] == "completed" and s["samples_emitted"] == s["samples_total"] == 7
    inc = client.get("/api/v1/incidents?status=open").json()["items"][0]
    assert inc["simulation_id"] == sim_id and inc["data_origin"] == "simulated"
    assert client.get("/api/v1/assets/cooling-01/readings").json()["total"] == 7
    reset = client.post(f"/api/v1/simulations/{sim_id}/reset").json()
    assert reset == {"simulation_id": sim_id, "status": "reset", "readings_deleted": 7, "predictions_deleted": 7, "incidents_resolved": 1}
    assert client.get(f"/api/v1/incidents/{inc['incident_id']}").json()["resolved_by"] == "reset"
    again = client.post(f"/api/v1/simulations/{sim_id}/reset").json()
    assert again["readings_deleted"] == 0 and again["incidents_resolved"] == 0


def test_second_running_simulation_conflicts(client, settings, monkeypatch):
    monkeypatch.setattr(simulations, "_generate", fake_generate)
    settings.simulation_tick_seconds = 5
    first = client.post("/api/v1/simulations", json={"scenario": "normal", "asset_id": "cooling-01"}).json()
    r = client.post("/api/v1/simulations", json={"scenario": "normal", "asset_id": "cooling-01"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SIMULATION_ALREADY_RUNNING"
    client.post(f"/api/v1/simulations/{first['simulation_id']}/reset")

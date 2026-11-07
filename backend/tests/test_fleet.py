import time
from pathlib import Path

import pytest

from backend.app.schemas.fleet import ClearResponse, FaultResponse, FleetMap, FleetStatus, LiveStatus, RackDetail

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "ml" / "artifacts"
needs_models = pytest.mark.skipif(
    not (ART / "backblaze" / "pipeline.joblib").is_file() or not (ART / "ai4i" / "pipeline.joblib").is_file(),
    reason="trained models not present")


@pytest.fixture
def fleet(client, settings):
    settings.model_artifact_path = str(ART / "ai4i" / "pipeline.joblib")
    settings.industrial_metrics_path = str(ART / "metrics" / "industrial-failure-v1.json")
    settings.drive_model_artifact_path = str(ART / "backblaze" / "pipeline.joblib")
    settings.drive_metrics_path = str(ART / "metrics" / "drive-failure-v1.json")
    settings.live_tick_seconds = 0.03
    yield client
    client.post("/api/v1/fleet/live/stop")


def until(fn, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


def test_map_layout_before_start(client):
    m = FleetMap.model_validate(client.get("/api/v1/fleet/map").json())
    assert [h.hall_id for h in m.halls] == ["hall-a", "hall-b", "plant"]
    assert m.summary.machines == 42 and m.summary.racks == 18 and m.summary.no_data == 42
    assert m.live.status == "stopped" and m.halls[0].status == "no_data"
    a = m.halls[0]
    rack = next(r for r in a.racks if r.rack_id == "A1-01")
    assert rack.machine_ids == ["drive-01", "drive-02"] and rack.cooled_by == ["cooling-01"]
    d1 = next(x for x in a.machines if x.asset_id == "drive-01")
    assert d1.placement.rack_id == "A1-01" and d1.placement.slot == 1 and "Rack A1-01" in d1.location


def test_rack_not_found(client):
    r = client.get("/api/v1/fleet/racks/Z9-99")
    assert r.status_code == 404 and r.json()["error"]["code"] == "RACK_NOT_FOUND"


@needs_models
def test_live_readings_are_healthy_then_stop_freezes(fleet):
    s = LiveStatus.model_validate(fleet.post("/api/v1/fleet/live/start").json())
    assert s.status == "running" and s.tick_seconds == 0.03
    assert fleet.post("/api/v1/fleet/live/start").json()["run_id"] == s.run_id  # idempotent
    st = until(lambda: (x := FleetStatus.model_validate(fleet.get("/api/v1/fleet/status?history=5").json()))
               .live.ticks >= 6 and x)
    assert st.summary.healthy == 42 and st.summary.open_incidents == 0
    m = st.machines[0]
    assert m.latest_values and len(m.history) == 5 and m.chart_fields
    stopped = LiveStatus.model_validate(fleet.post("/api/v1/fleet/live/stop").json())
    time.sleep(0.15)
    assert stopped.status == "stopped" and fleet.get("/api/v1/fleet/live").json()["ticks"] == stopped.ticks


@needs_models
def test_faults_open_incidents_and_rack_status(fleet):
    r = fleet.post("/api/v1/fleet/faults", json={"asset_ids": ["cooling-02", "drive-05", "mill-02"]})
    assert r.status_code == 201
    f = FaultResponse.model_validate(r.json())
    assert f.live.status == "running"  # auto-started
    assert {x.kind for x in f.injected} == {"cooling_failure", "drive_degradation", "machine_overstrain"}

    incs = until(lambda: (j := fleet.get("/api/v1/incidents?status=open").json())["total"] == 3 and j)
    assert {i["asset_id"] for i in incs["items"]} == {"cooling-02", "drive-05", "mill-02"}
    assert all(i["risk_level"] == "high" for i in incs["items"])

    m = FleetMap.model_validate(fleet.get("/api/v1/fleet/map").json())
    racks = {r.rack_id: r for h in m.halls for r in h.racks}
    assert racks["A1-03"].status == "critical" and racks["A1-03"].open_incident_ids  # drive-05 lives in A1-03
    assert racks["A2-01"].status == "warning" and any("CRAC Unit 2" in x for x in racks["A2-01"].reasons)
    assert racks["B1-01"].status == "healthy"
    assert m.summary.open_incidents == 3 and m.summary.critical == 3
    assert m.summary.downtime_cost_per_day_at_risk == (12000 + 1500 + 2000) * 24
    assert "not measured" in m.summary.assumptions_source

    rd = RackDetail.model_validate(fleet.get("/api/v1/fleet/racks/A1-03").json())
    assert [x.asset_id for x in rd.machines] == ["drive-05", "drive-06"]
    assert rd.machines[0].simulated_fault.kind == "drive_degradation" and rd.incidents
    assert rd.cooling_units[0].asset_id == "cooling-01"

    # No Gemini key in tests: the automatic investigation uses the deterministic fallback.
    def investigated():
        d = fleet.get(f"/api/v1/incidents/{incs['items'][0]['incident_id']}").json()
        return d["investigation_status"] == "completed" and d
    d = until(investigated)
    assert d["explanation_source"] == "rag" and d["agent_steps"]

    again = fleet.post("/api/v1/fleet/faults", json={"asset_ids": ["drive-05"]})
    assert again.status_code == 409 and again.json()["error"]["code"] == "FAULT_ALREADY_ACTIVE"


@needs_models
def test_random_faults_pick_each_type_and_clear_resets(fleet):
    f = FaultResponse.model_validate(fleet.post("/api/v1/fleet/faults", json={"count": 3}).json())
    types = {"cooling": "cooling_failure", "drive": "drive_degradation", "mill": "machine_overstrain"}
    assert sorted(x.kind for x in f.injected) == sorted(types.values())
    until(lambda: fleet.get("/api/v1/incidents").json()["total"] >= 3)
    c = ClearResponse.model_validate(fleet.post("/api/v1/fleet/clear").json())
    assert c.incidents_deleted >= 3 and c.faults_cleared == 3 and c.readings_deleted > 0
    assert c.live.status == "running" and c.live.active_faults == []
    assert fleet.get("/api/v1/incidents").json()["total"] == 0
    st = until(lambda: (x := fleet.get("/api/v1/fleet/status").json())["summary"]["healthy"] == 42 and x)
    assert st["summary"]["open_incidents"] == 0


def test_unknown_fault_asset(client):
    r = client.post("/api/v1/fleet/faults", json={"asset_ids": ["nope-1"]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "ASSET_NOT_FOUND"
    assert client.get("/api/v1/fleet/live").json()["status"] == "stopped"


@needs_models
def test_single_simulation_blocked_while_live(fleet):
    fleet.post("/api/v1/fleet/live/start")
    r = fleet.post("/api/v1/simulations", json={"scenario": "normal", "asset_id": "cooling-01"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "FLEET_LIVE_RUNNING"


def test_maintenance_search_includes_same_type_equipment(client):
    r = client.post("/api/v1/maintenance/search", json={"query": "CRAC supply temperature filter", "asset_id": "cooling-03"})
    ids = {i["asset_id"] for i in r.json()["items"]}
    assert "cooling-01" in ids and not ids & {"drive-01", "mill-01"}

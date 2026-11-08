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
    assert [h.hall_id for h in m.halls] == ["hall-a", "hall-b", "plant", "electrical", "chillers", "network"]
    assert m.summary.machines == 170 and m.summary.racks == 18 and m.summary.no_data == 170
    assert m.live.status == "stopped" and m.halls[0].status == "no_data"
    a = m.halls[0]
    rack = next(r for r in a.racks if r.rack_id == "A1-01")
    assert rack.machine_ids == ["drive-01", "drive-02"] + [f"srv-A1-01-{i}" for i in range(1, 5)] and rack.cooled_by == ["cooling-01"]
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
    assert st.summary.healthy == 170 and st.summary.open_incidents == 0
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
    assert [x.asset_id for x in rd.machines] == ["drive-05", "drive-06"] + [f"srv-A1-03-{i}" for i in range(1, 5)]
    assert rd.server_ids == [f"srv-A1-03-{i}" for i in range(1, 5)]
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
    f = FaultResponse.model_validate(fleet.post("/api/v1/fleet/faults", json={"count": 3, "site": "datacenter"}).json())
    kinds = sorted(x.kind for x in f.injected)  # one cooling unit, one GPU server, one drive
    assert "cooling_failure" in kinds and "drive_degradation" in kinds
    assert set(kinds) - {"cooling_failure", "drive_degradation"} <= {"gpu_fault", "psu_failure", "server_crash"}
    until(lambda: fleet.get("/api/v1/incidents").json()["total"] >= 3)
    c = ClearResponse.model_validate(fleet.post("/api/v1/fleet/clear").json())
    assert c.incidents_deleted >= 3 and c.faults_cleared == 3 and c.readings_deleted > 0
    assert c.live.status == "running" and c.live.active_faults == []
    assert fleet.get("/api/v1/incidents").json()["total"] == 0
    st = until(lambda: (x := fleet.get("/api/v1/fleet/status").json())["summary"]["healthy"] == 170 and x)
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


def test_mining_site_layout_and_sites_switch(client):
    m = FleetMap.model_validate(client.get("/api/v1/fleet/map?site=mining").json())
    assert m.site_id == "mining" and [h.kind for h in m.halls] == ["mining_container", "mining_container"]
    assert m.summary.machines == 148 and m.summary.racks == 24
    keys = [x.key for x in m.site_metrics]
    assert {"hashrate_phs", "revenue_per_day", "revenue_lost_per_day", "efficiency_j_per_th", "hashprice_usd_per_th_day"} <= set(keys)
    hp = next(x for x in m.site_metrics if x.key == "hashprice_usd_per_th_day")
    assert hp.value and "CloudMineCrypto" in hp.source
    sites = client.get("/api/v1/fleet/sites").json()["sites"]
    assert [(s["site_id"], s["machines"]) for s in sites] == [("datacenter", 170), ("mining", 148)]
    assert client.get("/api/v1/fleet/map?site=moon").status_code == 422
    rack = RackDetail.model_validate(client.get("/api/v1/fleet/racks/M1-01").json())
    assert rack.cooled_by == ["fanwall-m1"] and len(rack.machines) == 6


def test_miner_rule_needs_three_bad_readings_and_prices_lost_revenue(client):
    base = {"hashrate_ths": 130.0, "rated_hashrate_ths": 200.0, "chip_temp_c": 70.0, "fan_speed_rpm": 4800, "hw_error_pct": 2.0}
    levels = []
    for i in range(3):
        r = client.post("/api/v1/predictions", json={"asset_id": "miner-05", "observed_at": f"2026-11-07T20:0{i}:00Z",
                        "data_origin": "simulated", "detector_id": "miner-rule-v1", "readings": base}).json()
        levels.append(r["risk_level"])
    assert levels == ["medium", "medium", "high"] and r["incident_id"]
    assert {e["field"] for e in r["evidence"]} == {"hashrate_ths", "hw_error_pct"}
    inc = client.get(f"/api/v1/incidents/{r['incident_id']}").json()
    imp = inc["impact"]
    # Lost revenue = 200 TH/s x latest hashprice; fixing now ($60) beats failing (72 h down + $550 board).
    assert 0 < imp["cost_per_day"] < 100 and "hashprice" in imp["assumptions_source"]
    assert imp["cost_to_fix_now"] == 60 and imp["cost_if_it_fails"] == pytest.approx(550 + 3 * imp["cost_per_day"], abs=0.02)
    assert imp["savings_if_fixed_now"] > 0 and imp["return_on_repair"] > 1
    fanwall = client.get("/api/v1/assets/fanwall-m1").json()["impact_assumptions"]
    assert fanwall["cost_per_day"] == pytest.approx(36 * imp["cost_per_day"], abs=0.5)  # 36 miners in row M1
    bad = client.post("/api/v1/predictions", json={"asset_id": "miner-05", "observed_at": "2026-11-07T21:00:00Z",
                      "data_origin": "simulated", "detector_id": "miner-rule-v1", "readings": {"hashrate_ths": 1}})
    assert bad.status_code == 422


def test_mining_faults_open_tickets_fast(client, settings):
    settings.live_tick_seconds = 0.05
    try:
        f = FaultResponse.model_validate(client.post("/api/v1/fleet/faults", json={"count": 2, "site": "mining"}).json())
        assert {x.kind for x in f.injected} <= {"cooling_failure", "fan_failure", "hashboard_failure"}
        ids = {x.asset_id for x in f.injected}
        assert all(a.startswith(("miner-", "fanwall-")) for a in ids)
        incs = until(lambda: (x := client.get("/api/v1/incidents").json())["total"] >= 2 and x)
        assert {i["asset_id"] for i in incs["items"]} == ids
        st = FleetStatus.model_validate(client.get("/api/v1/fleet/status?site=mining&history=0").json())
        assert st.summary.open_incidents == 2 and st.summary.savings_if_fixed_now > 0
        assert st.machines[0].status == "critical"
    finally:
        client.post("/api/v1/fleet/live/stop")


def test_site_summaries_only_count_their_own_incidents(client):
    for i, t in enumerate([33, 34, 35]):
        client.post("/api/v1/predictions", json={"asset_id": "cooling-01", "observed_at": f"2026-11-07T20:0{i}:00Z",
                    "data_origin": "simulated", "detector_id": "cooling-rule-v1", "readings": {"temperature_c": t}})
    dc = client.get("/api/v1/fleet/status?site=datacenter&history=0").json()["summary"]
    mine = client.get("/api/v1/fleet/status?site=mining&history=0").json()["summary"]
    assert dc["open_incidents"] == 1 and dc["cost_to_fix_all_now"] == 900 and dc["savings_if_fixed_now"] == 50600
    assert mine["open_incidents"] == 0 and mine["cost_if_all_fail"] == 0

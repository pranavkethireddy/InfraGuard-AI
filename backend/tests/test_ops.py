import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.schemas.fleet import FleetStatus, RackDetail
from backend.app.schemas.ops import DispatchResponse, LearningMatrix, PlanResponse, TechniciansResponse, WhatIf
from backend.app.services import ops

T0 = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)


def fix_clock(client, settings, hour=14):
    """Demo clock at a fixed local time, so windows do not depend on when the test runs."""
    store = client.app.state.store
    with store.lock:
        ops.state(store, settings).start = datetime(2026, 11, 9, hour, 0, tzinfo=ZoneInfo("America/Chicago"))
    return store


def hot_cooling_incident(client, asset_id="cooling-01", start=33.0, n=38, per_tick=0.1) -> str:
    """Supply air rising 0.1 C per reading = 3 C per demo hour at 2 demo minutes per tick."""
    rows = [{"observed_at": (T0 + timedelta(seconds=i)).isoformat(), "values": {"temperature_c": round(start + per_tick * i, 2)}}
            for i in range(n)]
    client.post("/api/v1/readings", json={"asset_id": asset_id, "data_origin": "simulated", "readings": rows})
    for r in rows[-3:]:
        client.post("/api/v1/predictions", json={"asset_id": asset_id, "observed_at": r["observed_at"], "data_origin": "simulated",
                    "detector_id": "cooling-rule-v1", "readings": r["values"]})
    return next(i["incident_id"] for i in client.get("/api/v1/incidents").json()["items"] if i["asset_id"] == asset_id)


def run_ticks(client, settings, n):
    store = client.app.state.store
    for _ in range(n):
        with store.lock:
            ops.advance(store, settings, set())


def test_technicians_show_what_everyone_is_doing(client, settings):
    t = TechniciansResponse.model_validate(client.get("/api/v1/ops/technicians").json())
    assert len(t.technicians) == 7 and t.demo_minutes_per_tick == 2
    maya = next(x for x in t.technicians if x.name == "Maya Ortiz")
    assert maya.status == "working" and maya.current_work_order.kind == "routine"
    assert any(x.status == "idle" for x in t.technicians)
    mining = client.get("/api/v1/ops/technicians?site=mining").json()["technicians"]
    assert {x["site_id"] for x in mining} == {"mining"} and len(mining) == 3


def test_whatif_buy_time_avoids_the_shutdown_that_fixing_alone_hits(client, settings):
    fix_clock(client, settings, hour=14)
    w = WhatIf.model_validate(client.get(f"/api/v1/incidents/{hot_cooling_incident(client)}/whatif").json())
    assert w.metric == "temperature_c" and abs(w.trend_per_hour - 3.0) < 0.01
    assert w.shutdown_threshold == 42 and abs(w.shutdown_in_hours - (42 - 36.7) / 3) < 0.1
    assert w.window.kind == "maintenance_window" and abs(w.window.starts_in_hours - 12) < 0.1
    o = {x.option: x for x in w.options}
    assert o["fix_now"].shutdown_at_hours is not None and o["fix_now"].costs.parts == 3500  # unplanned
    assert o["buy_time"].shutdown_at_hours is None and o["buy_time"].costs.parts == 900  # planned
    assert o["wait_for_window"].costs.total > o["fix_now"].costs.total > o["buy_time"].costs.total
    assert w.recommended == "buy_time" and w.savings_vs_worst == round(o["wait_for_window"].costs.total - o["buy_time"].costs.total, 2)
    assert all(len(x.curve) == 25 for x in w.options)  # every 0.5 h for 12 h
    assert any(p.power_state == "off" for p in o["fix_now"].curve)


def test_dispatch_moves_a_technician_off_routine_work_and_the_repair_teaches_every_site(client, settings):
    store = fix_clock(client, settings)
    inc = hot_cooling_incident(client)
    d = DispatchResponse.model_validate(client.post("/api/v1/ops/dispatch", json={
        "incident_id": inc, "option": "fix_now", "technician_id": "tech-01"}).json())
    assert d.technician.name == "Maya Ortiz" and d.displaced.title.startswith("Quarterly filter change")
    assert d.work_order.status == "traveling" and d.displaced.status == "paused"
    assert client.get(f"/api/v1/incidents/{inc}").json()["status"] == "acknowledged"
    again = client.post("/api/v1/ops/dispatch", json={"incident_id": inc})
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_DISPATCHED"
    run_ticks(client, settings, 5 + 90)  # 10 min travel + 3 h repair at 2 demo minutes per tick
    detail = client.get(f"/api/v1/incidents/{inc}").json()
    assert detail["status"] == "resolved" and detail["resolved_by"] == "technician"
    techs = client.get("/api/v1/ops/technicians").json()
    done = next(w for w in techs["work_orders"] if w["incident_id"] == inc)
    assert done["status"] == "done" and done["cost"]["labor"] == 3 * 95 * 1.5  # overtime outside the window
    run_ticks(client, settings, 1)
    maya = next(t for t in client.get("/api/v1/ops/technicians").json()["technicians"] if t["name"] == "Maya Ortiz")
    assert maya["current_work_order"]["kind"] == "routine"  # back to the filter change
    m = LearningMatrix.model_validate(client.get("/api/v1/learning/matrix").json())
    row = m.rows[0]
    assert m.total_cases == 1 and row.asset_type == "cooling_unit" and row.symptom == "high temperature"
    assert row.sites_seen == ["datacenter"] and row.shared_with_sites == ["datacenter", "mining"]
    # A mining fan wall investigation can now cite the data-center repair.
    with store.lock:
        store.learning = None  # reload from disk: cases persist
    hot = hot_cooling_incident(client, "fanwall-m2")
    inv = client.post(f"/api/v1/incidents/{hot}/investigate").json()
    assert any(s["record_id"] == "lc-0001" and "datacenter" in s["source_name"] for s in inv["maintenance_sources"])


def test_dispatch_rejects_unqualified_or_unknown(client, settings):
    fix_clock(client, settings)
    inc = hot_cooling_incident(client)
    r = client.post("/api/v1/ops/dispatch", json={"incident_id": inc, "technician_id": "tech-02"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "TECHNICIAN_NOT_QUALIFIED"
    assert client.post("/api/v1/ops/dispatch", json={"incident_id": "inc-x"}).status_code == 404
    r = client.post("/api/v1/ops/dispatch", json={"incident_id": inc, "option": "teleport"})
    assert r.status_code == 422


def test_plan_ranks_by_savings_per_tech_hour_and_assigns_different_people(client, settings):
    fix_clock(client, settings)
    hot_cooling_incident(client, "cooling-01")
    hot_cooling_incident(client, "cooling-03")
    p = PlanResponse.model_validate(client.get("/api/v1/ops/plan?site=datacenter").json())
    assert len(p.items) == 2 and all(i.status == "ready" for i in p.items)
    assert len({i.technician_id for i in p.items}) == 2
    assert p.items[0].savings_per_tech_hour >= p.items[1].savings_per_tech_hour
    assert p.total_savings == sum(i.savings for i in p.items)
    assert client.get("/api/v1/ops/plan?site=mining").json()["items"] == []


def test_mining_window_is_power_price_curtailment(client, settings):
    fix_clock(client, settings, hour=9)
    w = WhatIf.model_validate(client.get(f"/api/v1/incidents/{hot_cooling_incident(client, 'fanwall-m1')}/whatif").json())
    assert w.window.kind == "curtailment" and w.window.breakeven_usd_per_mwh > 0
    # Prices pass break-even at 12:00 in the demo curve, 3 h after 09:00.
    assert abs(w.window.starts_in_hours - 3) < 0.1 and w.window.ends_in_hours > w.window.starts_in_hours


def test_operator_resolution_with_note_is_learned(client, settings):
    inc = hot_cooling_incident(client)
    client.patch(f"/api/v1/incidents/{inc}", json={"status": "resolved", "note": "Replaced clogged filter"})
    cases = client.get("/api/v1/learning/cases").json()
    assert cases["total"] == 1 and cases["items"][0]["fix"] == "Replaced clogged filter"
    assert cases["items"][0]["source"] == "operator"


def test_cooling_fault_shuts_racks_down_and_a_repair_brings_them_back(client, settings):
    settings.live_tick_seconds = 0.02
    try:
        client.post("/api/v1/fleet/faults", json={"asset_ids": ["cooling-03"]})
        end = time.monotonic() + 20
        while time.monotonic() < end:
            st = FleetStatus.model_validate(client.get("/api/v1/fleet/status?history=0").json())
            off = [m for m in st.machines if m.power_state == "off"]
            if off:
                break
            time.sleep(0.05)
        assert {m.placement.row for m in off} == {"B1"} and "Thermal shutdown" in off[0].power_reason
        assert st.summary.machines_powered_off == len(off) == 24  # 4 racks x (2 drives + 4 GPU servers)
        rack = RackDetail.model_validate(client.get("/api/v1/fleet/racks/B1-01?history=0").json())
        assert rack.power_state == "off" and any("Thermal shutdown" in r for r in rack.reasons)
        inc = next(i["incident_id"] for i in client.get("/api/v1/incidents").json()["items"] if i["asset_id"] == "cooling-03")
        assert client.post("/api/v1/ops/dispatch", json={"incident_id": inc, "option": "fix_now"}).status_code == 201
        end = time.monotonic() + 20
        while time.monotonic() < end:
            st = FleetStatus.model_validate(client.get("/api/v1/fleet/status?history=0").json())
            if st.summary.machines_powered_off == 0:
                break
            time.sleep(0.05)
        assert st.summary.machines_powered_off == 0
        assert client.get(f"/api/v1/incidents/{inc}").json()["resolved_by"] == "technician"
    finally:
        client.post("/api/v1/fleet/live/stop")


def test_projection_counts_sensor_wobble_against_the_limit(client, settings):
    """Flat at 41.2 C but swinging about 1 C: the next swing touches 42 C, so it must not be called safe."""
    import math
    fix_clock(client, settings)
    rows = [{"observed_at": (T0 + timedelta(seconds=i)).isoformat(),
             "values": {"temperature_c": round(41.2 + math.sin(i / 6), 2)}} for i in range(38)]
    client.post("/api/v1/readings", json={"asset_id": "cooling-01", "data_origin": "simulated", "readings": rows})
    for r in rows[-3:]:
        client.post("/api/v1/predictions", json={"asset_id": "cooling-01", "observed_at": r["observed_at"],
                    "data_origin": "simulated", "detector_id": "cooling-rule-v1", "readings": r["values"]})
    inc = client.get("/api/v1/incidents").json()["items"][0]["incident_id"]
    w = client.get(f"/api/v1/incidents/{inc}/whatif").json()
    assert w["shutdown_in_hours"] is not None and w["shutdown_in_hours"] < 0.5


def test_buy_time_promise_holds_in_the_live_simulation(client, settings):
    """The what-if's buy_time promise matches the live simulation: racks stay on when it says they will,
    and shut down when it says they will."""
    # 0.1 s ticks: fast, but slow enough that request latency does not leave the fault unmitigated for long.
    settings.live_tick_seconds = 0.1  # below the API minimum of 0.2, so set through settings
    store = client.app.state.store
    promises = []
    try:
        for seed, unit in ((42, "cooling-03"), (7, "cooling-01")):
            client.post("/api/v1/fleet/live/stop")
            client.post("/api/v1/fleet/clear")
            assert client.post("/api/v1/fleet/live/start", json={"seed": seed}).status_code == 200
            client.post("/api/v1/fleet/faults", json={"asset_ids": [unit]})
            inc = until(lambda: next((i["incident_id"] for i in client.get("/api/v1/incidents").json()["items"]
                                      if i["asset_id"] == unit), None))
            start = store.live.ticks
            until(lambda: store.live.ticks - start >= 40)  # trend window past the ramp
            w = client.get(f"/api/v1/incidents/{inc}/whatif").json()
            buy = next(o for o in w["options"] if o["option"] == "buy_time")
            promised_safe = buy["shutdown_at_hours"] is None
            promises.append(promised_safe)
            assert client.post("/api/v1/ops/dispatch", json={"incident_id": inc, "option": "buy_time"}).status_code == 201
            until(lambda: client.get(f"/api/v1/incidents/{inc}").json()["status"] == "resolved", 60)
            case = client.get("/api/v1/learning/cases").json()["items"][0]
            expected = "fixed_before_failure" if promised_safe else "fixed_after_shutdown"
            assert case["outcome"] == expected, (seed, unit, buy["shutdown_at_hours"])
        assert any(promises), "no scenario where buying time avoids the shutdown"
    finally:
        client.post("/api/v1/fleet/live/stop")


def until(fn, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.02)
    raise AssertionError("condition not met in time")

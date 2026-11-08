import time

from backend.app.services import chaos, ops, pager


def test_chaos_faults_are_dispatched_to_the_rack(client, settings):
    store = client.app.state.store
    settings.live_tick_seconds = 0.2
    with store.lock:
        ops.state(store, settings).auto_dispatch = True
    assert client.post("/api/v1/fleet/chaos", json={"enabled": True}).json()["enabled"] is True
    with store.lock:
        run = store.live
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline and len(run.chaos_assets) < 3:
        time.sleep(0.5)
    time.sleep(3)
    status = client.get("/api/v1/fleet/chaos").json()
    client.post("/api/v1/fleet/chaos", json={"enabled": False})
    client.post("/api/v1/fleet/live/stop")
    assert status["protected_technicians"] == []
    assert len(run.chaos_assets) >= 3 and all(a.startswith("srv-") for a in run.chaos_assets)
    with store.lock:
        st = ops.state(store, settings)
        chaos_orders = [o for o in st.orders.values() if o.asset_id in run.chaos_assets]
        assert chaos_orders
        assert {o.spot.hall_id for o in chaos_orders} <= {"hall-a", "hall-b"}  # they walk to the rack


def test_reprioritize_changes_only_the_queue(client, settings):
    store = client.app.state.store
    with store.lock:
        st = ops.state(store, settings)
        dev = st.techs["tech-02"]
        cur = dev.current
    import random

    from backend.app.services.live import LiveRun

    run = LiveRun(run_id="r", seed=1, tick_seconds=1, started_at=None, profiles={}, rngs={})
    chaos._reprioritize(store, run, settings, random.Random(0))  # nothing to change: no-op
    with store.lock:
        assert dev.current == cur


def test_escalation_moves_the_queue_not_the_current_job(client, settings):
    from datetime import timedelta

    from backend.tests.test_agent import open_cooling_incident

    store = client.app.state.store
    iid = open_cooling_incident(client)
    assert client.post("/api/v1/ops/dispatch", json={"incident_id": iid}).status_code == 201
    with store.lock:
        st = ops.state(store, settings)
        o = ops.active_order_for(st, iid)
        tech = st.techs[o.technician_id]
        routine = next(x for x in st.orders.values() if x.kind == "routine" and x.status != "done")
        tech.current = routine.work_order_id
        o.status, o.option = "scheduled", "wait_for_window"
        o.scheduled_start = ops.demo_now(st, settings) + timedelta(hours=8)
        if o.work_order_id not in tech.queue:
            tech.queue.append(o.work_order_id)
        st.auto_dispatch = True
    pager.escalate(store, settings, iid)
    with store.lock:
        assert tech.current == routine.work_order_id  # the job in hand is not interrupted
        assert o.scheduled_start is None and o.option == "fix_now" and o.work_order_id in tech.queue
        assert o.why.startswith("Escalated to priority")


def test_during_chaos_a_hand_injected_fault_goes_to_sam(client, settings):
    store = client.app.state.store
    settings.live_tick_seconds = 0.2
    with store.lock:
        ops.state(store, settings).auto_dispatch = True
    client.post("/api/v1/fleet/chaos", json={"enabled": True})
    with store.lock:
        store.live.chaos_assets.discard("srv-B2-02-2")
    assert client.post("/api/v1/fleet/faults", json={"asset_ids": ["srv-B2-02-2"], "kind": "server_crash"}).status_code == 201
    deadline, order = time.monotonic() + 20, None
    while time.monotonic() < deadline and order is None:
        time.sleep(0.3)
        with store.lock:
            order = next((o for o in ops.state(store, settings).orders.values() if o.asset_id == "srv-B2-02-2"), None)
    client.post("/api/v1/fleet/chaos", json={"enabled": False})
    client.post("/api/v1/fleet/live/stop")
    assert order is not None and order.technician_id == "tech-03"


def test_chaos_keeps_sam_on_the_ipad(client, settings):
    store = client.app.state.store
    client.post("/api/v1/fleet/chaos", json={"enabled": True})
    v = client.post("/api/v1/ops/pager/tech-03/release").json()
    assert v["technician"]["device_controlled"] is True  # only the iPad closes his work
    client.post("/api/v1/fleet/chaos", json={"enabled": False})
    assert client.post("/api/v1/ops/pager/tech-03/release").json()["technician"]["device_controlled"] is False
    client.post("/api/v1/fleet/live/stop")

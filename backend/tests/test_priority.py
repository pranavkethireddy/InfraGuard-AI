"""Priority levels drive each technician's own jobs: queue order, takeover, life safety first, and a job awaiting
confirmation is paused (never lost). Jobs stay with the technician they were given."""

from backend.app.services import ops
from backend.app.services.assets import all_assets
from backend.tests.test_pager import server_incident

SAM = "tech-03"


def _order(st, settings, tech_id, asset_id, incident_id=None, risk="high"):
    a = all_assets()[asset_id]
    lay = ops.site_of(asset_id)
    hall = lay.placements[asset_id].hall_id
    return ops._new(st, settings, kind="repair", title=f"{a.name}: fix", site_id=lay.site_id, hall_id=hall,
                    technician_id=tech_id, hours_total=2.0, asset_id=asset_id, incident_id=incident_id,
                    spot=ops.asset_spot(asset_id), risk_level=risk)


def _others(st):
    return [t for t in st.techs if t != SAM]


def _setup(client, settings):
    """Sam on a priority-3 GPU repair; a priority-5 (most urgent) one waits in his queue. Nobody else may take it."""
    store = client.app.state.store
    low_id, high_id = server_incident(client, "srv-B1-01-2"), server_incident(client, "srv-B1-01-3")
    with store.lock:
        st = ops.state(store, settings)
        store.incidents[low_id].priority_rank = 3
        store.incidents[high_id].priority_rank = 5
        sam = st.techs[SAM]
        low = _order(st, settings, SAM, "srv-B1-01-2", low_id)
        sam.current, low.status = low.work_order_id, "in_progress"
        high = _order(st, settings, SAM, "srv-B1-01-3", high_id)
        high.declined_by = _others(st)
        sam.queue.insert(0, high.work_order_id)
    return store, st, sam, low, high


def test_a_more_urgent_priority_takes_over_the_current_job(client, settings):
    store, st, sam, low, high = _setup(client, settings)
    with store.lock:
        ops.advance(store, settings, set())
        assert sam.current == high.work_order_id and high.status in ("traveling", "in_progress")
        assert low.status == "paused" and low.work_order_id in sam.queue


def test_a_finished_job_awaiting_confirmation_does_not_block_a_more_urgent_one(client, settings):
    store, st, sam, low, high = _setup(client, settings)
    with store.lock:
        low.status, low.hours_done = "awaiting_confirmation", low.hours_total
        ops.advance(store, settings, set())
        assert sam.current == high.work_order_id
        assert low.status == "paused" and low.work_order_id in sam.queue and low.hours_done == low.hours_total


def test_queue_is_sorted_by_level_with_life_safety_first(client, settings):
    store, st, sam, low, high = _setup(client, settings)
    with store.lock:
        smoke = _order(st, settings, SAM, "smoke-b", risk="medium")
        sam.queue.append(smoke.work_order_id)
        assert ops._level(store, smoke) < ops._level(store, high) < ops._level(store, low)
        sam.queue.sort(key=lambda i: ops._urgency(store, st.orders[i]))
        assert sam.queue[0] == smoke.work_order_id


def test_jobs_stay_with_their_technician_even_when_others_are_free(client, settings):
    store, st, sam, low, high = _setup(client, settings)
    with store.lock:
        high.declined_by = []
        for t in _others(st):  # everyone else idle
            st.techs[t].current, st.techs[t].queue = None, []
        ops.advance(store, settings, set())
        assert high.technician_id == SAM and sam.current == high.work_order_id
        assert low.technician_id == SAM and low.work_order_id in sam.queue


def test_operator_can_queue_a_less_urgent_job_on_a_busy_technician(client, settings):
    store = client.app.state.store
    store_ids = [server_incident(client, a) for a in ("srv-B1-01-2", "srv-B1-02-2", "srv-B1-03-2")]
    for iid in store_ids:
        r = client.post("/api/v1/ops/dispatch", json={"incident_id": iid, "option": "fix_now", "technician_id": SAM})
        assert r.status_code == 201, r.text
        assert r.json()["work_order"]["technician_id"] == SAM
    view = client.get(f"/api/v1/ops/pager/{SAM}").json()
    assert view["job"] is not None and len(view["queue"]) == 2

"""Walking technicians, closest-technician dispatch, the technician pager and its live stream."""

import time
from datetime import UTC, datetime, timedelta

from backend.app.schemas.ops import FloorPlan, PagerView, TechniciansResponse
from backend.app.services import floor, ops

T0 = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)


def run_ticks(client, settings, n):
    store = client.app.state.store
    for _ in range(n):
        with store.lock:
            ops.advance(store, settings, set())


def server_incident(client, asset_id="srv-B1-01-2") -> str:
    """A crashed GPU server: three readings with the server not responding."""
    vals = {"online": 0, "gpus_online": 0, "psu_ok": 2, "compute_pct": 0.0}
    for i in range(3):
        at = (T0 + timedelta(seconds=i)).isoformat()
        client.post("/api/v1/readings", json={"asset_id": asset_id, "data_origin": "simulated",
                                              "readings": [{"observed_at": at, "values": vals}]})
        client.post("/api/v1/predictions", json={"asset_id": asset_id, "observed_at": at, "data_origin": "simulated",
                                                 "detector_id": "server-rule-v1", "readings": vals})
    return next(i["incident_id"] for i in client.get("/api/v1/incidents").json()["items"] if i["asset_id"] == asset_id)


def test_floor_plan_and_paths():
    fp = FloorPlan.model_validate(floor.plan("datacenter").model_dump())
    a, b = fp.halls[0], fp.halls[1]
    assert (a.hall_id, a.x) == ("hall-a", 0) and b.x == a.width + floor.GAP and fp.corridor_y > max(h.depth for h in fp.halls)
    start = floor.to_floor("datacenter", floor.Spot("hall-a", 2, 3))
    end = floor.to_floor("datacenter", floor.Spot("hall-b", 5, 4.5))
    pts = floor.path("datacenter", start, end)
    assert any(p.hall_id is None and p.y == fp.corridor_y for p in pts)  # goes through the corridor
    assert pts[0] == start and pts[-1] == end
    pos, rest = floor.walk(pts, 5.0)
    assert floor.length(rest) == floor.length(pts) - 5.0 and rest[0] == pos


def test_closest_qualified_technician_is_sent(client, settings):
    inc = server_incident(client)  # Hall B; Sam (idle in Hall B) is closer than Dev (Hall A)
    d = client.post("/api/v1/ops/dispatch", json={"incident_id": inc, "option": "fix_now"}).json()
    assert d["technician"]["name"] == "Sam Rivera" and d["work_order"]["status"] == "traveling"
    assert d["work_order"]["spot"]["hall_id"] == "hall-b" and d["work_order"]["asset_name"].startswith("Rack B1-01")
    t = TechniciansResponse.model_validate(client.get("/api/v1/ops/technicians?site=datacenter").json())
    sam = next(x for x in t.technicians if x.name == "Sam Rivera")
    assert sam.path and sam.walking_minutes_left > 0 and t.walk_cells_per_demo_minute == 2.0


def test_technician_walks_along_the_path(client, settings):
    inc = server_incident(client, "srv-A1-01-1")  # Hall A: Dev pauses his firmware job (closest, in Hall A)
    d = client.post("/api/v1/ops/dispatch", json={"incident_id": inc, "option": "fix_now",
                                                  "technician_id": "tech-03"}).json()  # Sam walks over from Hall B
    before = d["technician"]["position"]
    run_ticks(client, settings, 2)
    sam = next(x for x in client.get("/api/v1/ops/technicians").json()["technicians"] if x["name"] == "Sam Rivera")
    assert sam["position"] != before and sam["status"] == "traveling"
    assert sam["walking_minutes_left"] < d["technician"]["walking_minutes_left"]
    run_ticks(client, settings, 30)
    sam = next(x for x in client.get("/api/v1/ops/technicians").json()["technicians"] if x["name"] == "Sam Rivera")
    assert sam["status"] == "working" and sam["position"] == d["work_order"]["spot"] and sam["path"] == []


def test_pager_accept_walk_and_confirm_done(client, settings):
    v = PagerView.model_validate(client.post("/api/v1/ops/pager/tech-03/claim").json())
    assert v.technician.device_controlled and v.job is None
    inc = server_incident(client)
    client.post("/api/v1/ops/dispatch", json={"incident_id": inc, "option": "fix_now"})
    v = PagerView.model_validate(client.get("/api/v1/ops/pager/tech-03").json())
    assert v.job.work_order.status == "paged" and v.job.actions == ["accept", "decline"]
    assert "Closest qualified technician" in v.job.why_you and v.job.steps and v.job.cost_per_hour_while_down > 0
    run_ticks(client, settings, 5)  # nothing happens until the pager accepts
    assert client.get("/api/v1/ops/pager/tech-03").json()["job"]["work_order"]["status"] == "paged"
    wo = v.job.work_order.work_order_id
    bad = client.post("/api/v1/ops/pager/tech-03/action", json={"action": "done", "work_order_id": wo})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "NOT_STARTED"
    v = PagerView.model_validate(client.post("/api/v1/ops/pager/tech-03/action",
                                             json={"action": "accept", "work_order_id": wo}).json())
    assert v.job.work_order.status in ("traveling", "in_progress")
    run_ticks(client, settings, 80)  # 2 h repair: waits for the pager instead of finishing alone
    v = PagerView.model_validate(client.get("/api/v1/ops/pager/tech-03").json())
    assert v.job.work_order.status == "awaiting_confirmation" and v.job.actions == ["done"]
    v = PagerView.model_validate(client.post("/api/v1/ops/pager/tech-03/action",
                                             json={"action": "done", "work_order_id": wo}).json())
    assert v.job is None
    detail = client.get(f"/api/v1/incidents/{inc}").json()
    assert detail["status"] == "resolved" and detail["resolved_by"] == "technician"
    assert client.get("/api/v1/learning/cases").json()["total"] == 1
    assert not client.post("/api/v1/ops/pager/tech-03/release").json()["technician"]["device_controlled"]


def test_declined_page_goes_to_the_next_closest(client, settings):
    client.post("/api/v1/ops/pager/tech-03/claim")
    inc = server_incident(client)
    client.post("/api/v1/ops/dispatch", json={"incident_id": inc, "option": "fix_now"})
    wo = client.get("/api/v1/ops/pager/tech-03").json()["job"]["work_order"]["work_order_id"]
    v = client.post("/api/v1/ops/pager/tech-03/action", json={"action": "decline", "work_order_id": wo}).json()
    assert v["job"] is None
    detail = client.get(f"/api/v1/incidents/{inc}").json()
    techs = client.get("/api/v1/ops/technicians").json()
    new = next(w for w in techs["work_orders"] if w["work_order_id"] == detail["work_order_id"])
    assert new["technician_id"] == "tech-02" and new["work_order_id"] != wo  # Dev Patel, the only other one
    old = next(w for w in techs["work_orders"] if w["work_order_id"] == wo)
    assert old["status"] == "done" and "declined by Sam Rivera" in old["title"]


def test_pager_errors(client):
    assert client.get("/api/v1/ops/pager/tech-99").status_code == 404
    r = client.post("/api/v1/ops/pager/tech-03/action", json={"action": "accept", "work_order_id": "wo-9999"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_YOUR_JOB"
    assert client.get("/api/v1/ops/stream?technician_id=tech-99").status_code == 404


def test_stream_pushes_the_pager_view(client):
    with client.stream("GET", "/api/v1/ops/stream?technician_id=tech-03&max_seconds=1") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert body.startswith("event: pager\ndata: ")
    PagerView.model_validate_json(body.split("data: ", 1)[1].split("\n", 1)[0])
    with client.stream("GET", "/api/v1/ops/stream?site=datacenter&max_seconds=1") as r:
        body = "".join(r.iter_text())
    assert body.startswith("event: crew\ndata: ")


def test_live_incident_pages_the_closest_technician_automatically(client, settings):
    settings.live_tick_seconds = 0.05
    assert client.post("/api/v1/ops/auto-dispatch", json={"enabled": True}).json() == {"enabled": True}
    client.post("/api/v1/ops/pager/tech-03/claim")
    try:
        client.post("/api/v1/fleet/live/start", json={"seed": 7})  # seed 7 draws a server fault that pages now
        client.post("/api/v1/fleet/faults", json={"asset_ids": ["srv-B1-01-2"]})
        end, v = time.monotonic() + 30, None
        while time.monotonic() < end:
            v = client.get("/api/v1/ops/pager/tech-03").json()
            if v["job"] or v["queue"]:
                break
            time.sleep(0.05)
        assert v["job"] or v["queue"], "Sam was not paged"
        assert client.post("/api/v1/ops/auto-dispatch", json={"enabled": False}).json() == {"enabled": False}
        assert client.get("/api/v1/ops/technicians").json()["auto_dispatch"] is False
    finally:
        client.post("/api/v1/fleet/live/stop")


def test_priority_rank_and_escalation_pulls_a_waiting_repair_forward(client, settings):
    from backend.app.services import incidents, pager
    from backend.tests.test_agent import open_cooling_incident

    assert [incidents.rank(p) for p in (0.95, 0.7, 0.5, 0.3, 0.0, None)] == [1, 2, 3, 4, 5, 5]
    store = client.app.state.store
    iid = open_cooling_incident(client)
    assert client.post("/api/v1/ops/dispatch", json={"incident_id": iid}).status_code == 201
    with store.lock:
        inc = store.incidents[iid]
        assert inc.priority_rank == incidents.rank(inc.priority_index)
        st = ops.state(store, settings)
        o = ops.active_order_for(st, iid)
        tech = st.techs[o.technician_id]
        # Pretend it was parked for the maintenance window.
        if tech.current == o.work_order_id:
            tech.current = None
        o.status, o.option = "scheduled", "wait_for_window"
        o.scheduled_start = ops.demo_now(st, settings) + timedelta(hours=8)
        tech.queue.append(o.work_order_id)
        st.auto_dispatch = True
    pager.escalate(store, settings, iid)
    with store.lock:
        assert o.scheduled_start is None and o.option == "fix_now" and o.status != "scheduled"
        assert tech.current == o.work_order_id and o.why.startswith("Escalated to priority")

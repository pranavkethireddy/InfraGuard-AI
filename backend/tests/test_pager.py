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


def until(fn, timeout=30.0):
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


def test_pager_job_is_accepted_automatically_then_confirmed_done(client, settings):
    v = PagerView.model_validate(client.post("/api/v1/ops/pager/tech-03/claim").json())
    assert v.technician.device_controlled and v.job is None
    inc = server_incident(client)
    client.post("/api/v1/ops/dispatch", json={"incident_id": inc, "option": "fix_now"})
    v = PagerView.model_validate(client.get("/api/v1/ops/pager/tech-03").json())
    # No accept or decline: the job is taken at once and the walk starts (by the parts cabinet).
    assert v.job.work_order.status in ("traveling", "in_progress") and "accept" not in v.job.actions
    assert "Closest qualified technician" in v.job.why_you and v.job.steps and v.job.cost_per_hour_while_down > 0
    wo = v.job.work_order.work_order_id
    run_ticks(client, settings, 90)  # walk + 2 h repair: waits for the pager instead of finishing alone
    v = PagerView.model_validate(client.get("/api/v1/ops/pager/tech-03").json())
    assert v.job.work_order.status == "awaiting_confirmation" and v.job.actions == ["done"]
    v = PagerView.model_validate(client.post("/api/v1/ops/pager/tech-03/action",
                                             json={"action": "done", "work_order_id": wo}).json())
    assert v.job is None
    detail = client.get(f"/api/v1/incidents/{inc}").json()
    assert detail["status"] == "resolved" and detail["resolved_by"] == "technician"
    assert client.get("/api/v1/learning/cases").json()["total"] == 1
    assert not client.post("/api/v1/ops/pager/tech-03/release").json()["technician"]["device_controlled"]


def test_higher_risk_repair_takes_over_from_a_lower_risk_one(client, settings):
    settings.live_tick_seconds = 0.05
    try:
        client.post("/api/v1/fleet/live/start", json={"seed": 1})  # seed 1: srv-B2-02-1 gets psu_failure (medium)
        client.post("/api/v1/fleet/faults", json={"asset_ids": ["srv-B2-02-1"]})
        client.post("/api/v1/fleet/faults", json={"asset_ids": ["srv-B1-01-1"], "kind": "server_crash"})
        incs = until(lambda: (x := {i["asset_id"]: i for i in client.get("/api/v1/incidents").json()["items"]})
                     .keys() >= {"srv-B2-02-1", "srv-B1-01-1"} and x)
        assert incs["srv-B2-02-1"]["risk_level"] == "medium" and incs["srv-B1-01-1"]["risk_level"] == "high"
        low = client.post("/api/v1/ops/dispatch", json={"incident_id": incs["srv-B2-02-1"]["incident_id"],
                                                       "option": "fix_now", "technician_id": "tech-03"}).json()
        high = client.post("/api/v1/ops/dispatch", json={"incident_id": incs["srv-B1-01-1"]["incident_id"],
                                                        "option": "fix_now", "technician_id": "tech-03"})
        assert high.status_code == 201, high.text
        h = high.json()
        assert h["displaced"]["work_order_id"] == low["work_order"]["work_order_id"] and h["displaced"]["status"] == "paused"
        assert h["work_order"]["status"] in ("traveling", "in_progress") and "Moved off" in client.get("/api/v1/ops/pager/tech-03").json()["job"]["why_you"]
    finally:
        client.post("/api/v1/fleet/live/stop")


def test_repair_walk_goes_by_the_parts_cabinet():
    from backend.app.core.config import Settings
    from backend.app.services import floor, ops

    s = Settings()
    a, b = ops.asset_spot("srv-A1-01-1"), ops.asset_spot("cooling-03")
    walk, direct = ops.repair_path("datacenter", a, b, s), floor.path("datacenter", a, b)
    cabinets = {(p.x, p.y) for p in ops.parts_spots("datacenter", s)}
    assert any((p.x, p.y) in cabinets for p in walk) and floor.length(walk) >= floor.length(direct)


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


def test_priority_rank_buckets():
    from backend.app.services import incidents

    assert [incidents.rank(p) for p in (0.95, 0.7, 0.5, 0.3, 0.0, None)] == [1, 2, 3, 4, 5, 5]

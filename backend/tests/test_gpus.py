"""GPU servers: heat throttling, the synchronous job cost, server faults and their what-if."""

import random
import time

from backend.app.schemas.fleet import FleetMap, ServerDetail
from backend.app.schemas.ops import WhatIf
from simulator import fleet as sim


def until(fn, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


def test_gpus_throttle_only_when_the_inlet_air_is_hot():
    prof = sim.profile("gpu_server", "srv-x", 42)
    cool = sim.sample("gpu_server", prof, 0, random.Random(1), 0.0, None, 23.0)
    hot = sim.sample("gpu_server", prof, 0, random.Random(1), 0.0, None, 40.0)
    assert cool["gpus_throttled"] == 0 and cool["compute_pct"] == 100.0
    assert hot["gpus_throttled"] > 0 and hot["min_gpu_clock_pct"] < 100 and hot["max_gpu_temp_c"] > sim.THROTTLE_C
    assert sim.gpu_throttle(80.0) == (80.0, 1.0) and sim.gpu_throttle(93.0)[1] < 1.0


def test_server_fault_signatures():
    prof = sim.profile("gpu_server", "srv-x", 42)
    gpu = sim.sample("gpu_server", prof, 0, random.Random(1), 1.0, "gpu_fault", 23.0)
    psu = sim.sample("gpu_server", prof, 0, random.Random(1), 1.0, "psu_failure", 23.0)
    crash = sim.sample("gpu_server", prof, 0, random.Random(1), 1.0, "server_crash", 23.0)
    assert gpu["gpus_online"] == 7 and gpu["ecc_errors"] > 10 and gpu["compute_pct"] == 87.5
    assert psu["psu_ok"] == 1 and psu["compute_pct"] == 100.0
    assert crash["online"] == 0 and crash["gpus_online"] == 0 and crash["compute_pct"] == 0.0


def test_server_endpoint_and_404(client):
    d = ServerDetail.model_validate(client.get("/api/v1/fleet/servers/srv-B1-01-2").json())
    assert d.rack_id == "B1-01" and len(d.gpus) == 8 and d.psus_total == 2
    assert d.job is not None and d.job.name == "Training job B1" and d.job.gpus == 128
    assert [c.asset_id for c in d.cooled_by] == ["cooling-03"]
    r = client.get("/api/v1/fleet/servers/drive-01")
    assert r.status_code == 404 and r.json()["error"]["code"] == "SERVER_NOT_FOUND"


def test_failing_cooling_slows_the_gpu_job_it_serves(client, settings):
    settings.live_tick_seconds = 0.05
    try:
        client.post("/api/v1/fleet/faults", json={"asset_ids": ["cooling-03"]})

        def slowed():
            m = FleetMap.model_validate(client.get("/api/v1/fleet/map").json())
            job = next(j for j in m.jobs if j.row == "B1")
            return job.gpus_throttled > 0 and (m, job)
        m, job = until(slowed)
        # Throttling first; later the racks may already be shutting down (which stalls the job outright).
        assert job.pace_pct < 100 and job.lost_usd_per_hour > 0
        assert any("throttling" in r or "powered off" in r for r in job.reasons)
        assert all(j.lost_usd_per_hour == 0 for j in m.jobs if j.row != "B1")
        lost = next(x for x in m.site_metrics if x.key == "gpu_compute_lost_per_hour")
        assert lost.value >= job.lost_usd_per_hour and "demo assumption" in lost.source
        srv = ServerDetail.model_validate(client.get("/api/v1/fleet/servers/srv-B1-01-1").json())
        assert srv.machine.power_state == "off" or srv.inlet_temp_c > 27  # normal inlet is about 23 C
    finally:
        client.post("/api/v1/fleet/live/stop")


def test_crashed_server_stalls_its_job_until_restarted_without_it(client, settings):
    settings.live_tick_seconds = 0.05
    try:
        client.post("/api/v1/fleet/faults", json={"asset_ids": ["srv-A1-02-3"]})
        inc = until(lambda: next((i for i in client.get("/api/v1/incidents").json()["items"]
                                  if i["asset_id"] == "srv-A1-02-3"), None))
        assert inc["title"].startswith("GPU server fault") and inc["risk_level"] == "high"
        job = lambda: next(j for j in client.get("/api/v1/fleet/map").json()["jobs"] if j["row"] == "A1")  # noqa: E731
        stalled = until(lambda: (j := job())["servers_down"] and j)
        assert stalled["pace_pct"] == 0 and stalled["lost_usd_per_hour"] == 160 * 2.5  # 20 servers x 8 GPUs in row A1

        w = WhatIf.model_validate(client.get(f"/api/v1/incidents/{inc['incident_id']}/whatif").json())
        assert w.recommended == "buy_time"
        buy = next(o for o in w.options if o.option == "buy_time")
        fix = next(o for o in w.options if o.option == "fix_now")
        assert buy.costs.downtime_or_lost_revenue < fix.costs.downtime_or_lost_revenue

        assert client.post("/api/v1/ops/dispatch", json={"incident_id": inc["incident_id"]}).status_code == 201
        drained = until(lambda: (j := job())["lost_usd_per_hour"] == 8 * 2.5 and j)
        assert any("Restarted without" in r for r in drained["reasons"])
    finally:
        client.post("/api/v1/fleet/live/stop")


def test_lost_power_supply_is_medium_and_can_wait(client, settings):
    settings.live_tick_seconds = 0.05
    try:
        # The fault kind is drawn from the run seed; seed 1's first draw for a GPU server is psu_failure.
        client.post("/api/v1/fleet/live/start", json={"seed": 1})
        f = client.post("/api/v1/fleet/faults", json={"asset_ids": ["srv-B2-02-1"]}).json()
        assert f["injected"][0]["kind"] == "psu_failure"
        inc = until(lambda: next((i for i in client.get("/api/v1/incidents").json()["items"]
                                  if i["asset_id"] == "srv-B2-02-1"), None))
        assert inc["risk_level"] == "medium"
        w = WhatIf.model_validate(client.get(f"/api/v1/incidents/{inc['incident_id']}/whatif").json())
        # Usually the window; fix_now when the demo clock puts the window too far away. Either way no downtime.
        assert w.recommended in ("wait_for_window", "fix_now") and "second one fails" in w.options[1].risk_note
        assert all(o.costs.downtime_or_lost_revenue == 0 for o in w.options)
    finally:
        client.post("/api/v1/fleet/live/stop")


def test_inject_a_chosen_fault_kind(client):
    r = client.post("/api/v1/fleet/faults", json={"kind": "server_crash", "count": 2})
    assert r.status_code == 201, r.text
    assert {f["kind"] for f in r.json()["injected"]} == {"server_crash"}
    assert all(f["asset_id"].startswith("srv-") for f in r.json()["injected"])
    r = client.post("/api/v1/fleet/faults", json={"asset_ids": ["cooling-01"], "kind": "gpu_fault"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "FAULT_KIND_NOT_SUPPORTED"
    client.post("/api/v1/fleet/live/stop")

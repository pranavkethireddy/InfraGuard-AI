"""Facility equipment: power, cooling plant, network, safety and security. Each family has readings, faults,
a rule detector, a failure playbook and a place on the map; every rack has a power strip and a switch."""

import random
import time

from backend.app.schemas.fleet import FleetMap, RackDetail
from backend.app.services import diagnosis
from simulator import fleet as sim


def until(fn, timeout=30.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


def test_every_fault_names_a_specific_playbook():
    for t, spec in sim.FACILITY.items():
        prof = sim.profile(t, "x", 1)
        healthy = sim.sample(t, prof, 0, random.Random(1))
        assert diagnosis.likely_cause(t, healthy) is None, (t, healthy)
        for kind in spec["faults"]:
            v = sim.sample(t, prof, 0, random.Random(1), 1.0, kind)
            assert diagnosis.diagnose(t, [v]) is not None, kind


def test_racks_have_power_strip_and_switch_and_map_has_rooms(client):
    m = FleetMap.model_validate(client.get("/api/v1/fleet/map").json())
    assert {h.kind for h in m.halls} >= {"electrical_room", "chiller_yard", "network_room"}
    rack = next(r for h in m.halls for r in h.racks if r.rack_id == "A1-01")
    assert rack.pdu_id == "pdu-A1-01" and rack.tor_id == "tor-A1-01"
    d = RackDetail.model_validate(client.get("/api/v1/fleet/racks/A1-01").json())
    assert d.pdu.asset_type == "pdu" and d.tor.asset_type == "network_switch"
    assert "pdu-A1-01" not in d.machine_ids


def test_ups_fault_opens_an_incident_with_its_playbook(client, settings):
    settings.live_tick_seconds = 0.05
    try:
        r = client.post("/api/v1/fleet/faults", json={"asset_ids": ["ups-01"], "kind": "ups_on_battery"})
        assert r.status_code == 201, r.text
        inc = until(lambda: next((i for i in client.get("/api/v1/incidents").json()["items"] if i["asset_id"] == "ups-01"), None))
        assert inc["risk_level"] == "high"
        d = client.get(f"/api/v1/incidents/{inc['incident_id']}").json()
        assert d["failure_mode"]["mode_id"].startswith("ups-")
        r = client.post("/api/v1/fleet/faults", json={"asset_ids": ["pdu-B1-02"], "kind": "pdu_overload"})
        assert r.status_code == 201, r.text
        until(lambda: client.get("/api/v1/fleet/racks/B1-02").json()["status"] in ("warning", "critical"))
    finally:
        client.post("/api/v1/fleet/live/stop")

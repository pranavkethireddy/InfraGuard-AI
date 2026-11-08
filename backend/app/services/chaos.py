"""Demo chaos mode: random faults on any equipment and random priority changes, run by the live loop.

- Every `fault_every_ticks`, while fewer than `max_active_faults` chaos faults are running, one random piece of
  equipment at `site` gets a random fault it can have: first a random equipment type (so racks full of servers
  and drives do not crowd out the UPS, chillers or door access), then a healthy machine of that type, then any of
  its fault kinds, server parts included. `kinds` set to a list limits chaos to those kinds instead. The new
  incident is dispatched automatically to the closest qualified technician, never a protected one.
- Every `reprioritize_every_ticks`, one open chaos incident gets a new random priority (1-5). Queues re-sort by
  priority, and a waiting repair that is now more urgent than a technician's current one takes over (see
  ops.advance). Work assigned to a protected technician is never touched.
Settings: configs/operations.json "chaos"."""

from __future__ import annotations

import logging
import random

from ..core.config import Settings
from ..core.errors import ApiError
from ..schemas.fleet import ChaosStatus, FaultRequest
from . import incidents, ops
from .store import Store

log = logging.getLogger(__name__)

# The priority_index in the middle of each rank's band (rank 1 = fix first).
RANK_INDEX = {1: 0.9, 2: 0.7, 3: 0.5, 4: 0.3, 5: 0.1}


def config(settings: Settings) -> dict:
    return ops.config(settings).get("chaos", {})


def protected(settings: Settings) -> list[str]:
    return list(config(settings).get("protected_technicians", []))


def demo_technician(settings: Settings) -> str | None:
    return config(settings).get("demo_technician")


def holds_device(store: Store, settings: Settings, tech_id: str) -> bool:
    """While chaos is on, the demo technician stays on the iPad: only the pager accepts and closes their work."""
    run = store.live
    return bool(run is not None and run.running and run.chaos and tech_id == demo_technician(settings))


def status(store: Store, settings: Settings) -> ChaosStatus:
    with store.lock:
        run = store.live
        on = bool(run is not None and run.running and run.chaos)
        active = sorted(a for a in run.chaos_assets if a in run.faults) if run is not None else []
    return ChaosStatus(enabled=on, protected_technicians=protected(settings), active_faults=active)


def set_enabled(store: Store, settings: Settings, enabled: bool) -> ChaosStatus:
    from . import live
    from ..schemas.fleet import LiveStartRequest

    with store.lock:
        if enabled and (store.live is None or not store.live.running):
            live.start(store, LiveStartRequest(), settings)
        if store.live is not None:
            store.live.chaos = enabled
        demo = demo_technician(settings)
        if enabled and demo:
            st = ops.state(store, settings)
            if demo in st.techs:
                st.techs[demo].device = True
                st.version += 1
    return status(store, settings)


def _rng(run) -> random.Random:
    return random.Random(f"{run.seed}:chaos:{run.ticks}")


def step(store: Store, run, settings: Settings) -> None:
    """Called by the live loop after each tick while chaos mode is on."""
    cfg = config(settings)
    rng = _rng(run)
    if run.ticks % max(1, cfg.get("fault_every_ticks", 20)) == 0:
        _new_fault(store, run, settings, cfg, rng)
    if run.ticks % max(1, cfg.get("reprioritize_every_ticks", 10)) == 5:
        _reprioritize(store, run, settings, rng)


def _new_fault(store: Store, run, settings: Settings, cfg: dict, rng: random.Random) -> None:
    from . import live

    with store.lock:
        active = sum(1 for a in run.chaos_assets if a in run.faults)
    if active >= cfg.get("max_active_faults", 4):
        return
    site = cfg.get("site", "datacenter")
    kinds = cfg.get("kinds", "all")
    try:
        if kinds == "all":
            pick = _any_equipment(store, run, site, rng)
            if pick is None:
                log.info("chaos: no healthy equipment left")
                return
            asset_id, kind = pick
            res = live.inject(store, FaultRequest(asset_ids=[asset_id], kind=kind), settings)
        else:
            kind = rng.choice(kinds)
            res = live.inject(store, FaultRequest(count=1, site=site, kind=kind), settings)
    except ApiError as e:  # e.g. every server is already busy
        log.info("chaos: no new fault (%s)", e.code)
        return
    with store.lock:
        run.chaos_assets.update(f.asset_id for f in res.injected)
    log.info("chaos: %s on %s", kind, ", ".join(f.asset_id for f in res.injected))


def _any_equipment(store: Store, run, site: str, rng: random.Random) -> tuple[str, str] | None:
    """(asset_id, fault kind): a random equipment type, a healthy machine of it, one of its faults."""
    from . import live
    from .layout import get_layout

    fleet = live._fleet()
    lay = get_layout(site)
    with store.lock:
        busy = set(run.faults) | {i.asset_id for i in store.incidents.values() if i.status != "resolved"}
    by_type: dict[str, list[str]] = {}
    for a, x in lay.assets.items():
        if a not in busy and live._kinds(fleet, x.asset_type):
            by_type.setdefault(x.asset_type, []).append(a)
    if not by_type:
        return None
    t = rng.choice(sorted(by_type))
    return rng.choice(sorted(by_type[t])), rng.choice(live._kinds(fleet, t))


def _reprioritize(store: Store, run, settings: Settings, rng: random.Random) -> None:
    keep = set(protected(settings))
    with store.lock:
        st = ops.state(store, settings)
        pool = []
        for inc in store.incidents.values():
            if inc.status == "resolved" or inc.asset_id not in run.chaos_assets:
                continue
            o = ops.active_order_for(st, inc.incident_id)
            if o is not None and o.technician_id in keep:
                continue
            pool.append(inc)
        if not pool:
            return
        inc = rng.choice(sorted(pool, key=lambda i: i.incident_id))
        new = rng.choice([r for r in RANK_INDEX if r != inc.priority_rank])
        inc.priority_index, inc.priority_rank = RANK_INDEX[new], new
        st.version += 1  # queues re-sort on the next crew tick; pushes the change to the crew stream
    log.info("chaos: %s is now priority %d", inc.incident_id, new)

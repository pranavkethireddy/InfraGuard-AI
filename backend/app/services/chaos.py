"""Demo chaos mode: random GPU server faults and random priority changes, run by the live loop.

- Every `fault_every_ticks`, while fewer than `max_active_faults` chaos faults are running, one random GPU
  server at `site` gets a random fault from `kinds` (a GPU fails, or the whole server goes down). The new
  incident is dispatched automatically to the closest qualified technician, never a protected one.
- Every `reprioritize_every_ticks`, one open chaos incident gets a new random priority (1-5). Only the order of
  technicians' queues changes; the job a technician is doing now is never interrupted, and work assigned to a
  protected technician is never touched.
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
    kind = rng.choice(cfg.get("kinds", ["gpu_fault", "server_crash"]))
    try:
        res = live.inject(store, FaultRequest(count=1, site=cfg.get("site", "datacenter"), kind=kind), settings)
    except ApiError as e:  # e.g. every server is already busy
        log.info("chaos: no new fault (%s)", e.code)
        return
    with store.lock:
        run.chaos_assets.update(f.asset_id for f in res.injected)
    log.info("chaos: %s on %s", kind, ", ".join(f.asset_id for f in res.injected))


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

"""Live fleet demo: one background loop that sends a reading for every machine each tick.

Values come from simulator.fleet (pure, seeded). Every reading goes through the normal
readings -> predictions path, so the real cooling rule and trained models decide risk and
open incidents. Injected faults only change the readings; nothing here sets a risk or cost.
New incidents are queued for the AI agent when settings.auto_investigate is on.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime

from ..core.config import Settings
from ..core.errors import ApiError
from ..schemas.fleet import ClearResponse, FaultInfo, FaultRequest, FaultResponse, LiveStartRequest, LiveStatus
from ..schemas.predictions import PredictionRequest
from ..schemas.readings import Reading, ReadingsRequest
from . import agent, predictions
from .assets import all_assets
from .incidents import now
from .store import Store

log = logging.getLogger(__name__)
TYPE_ORDER = ("cooling_unit", "storage_drive", "asic_miner", "industrial_machine")


def _fleet():
    try:
        from simulator import fleet
    except ImportError as e:  # simulator/ not on this checkout
        raise ApiError(503, "SIMULATOR_UNAVAILABLE", "simulator package is not installed.", {}) from e
    return fleet


@dataclass
class Fault:
    asset_id: str
    kind: str
    injected_tick: int
    injected_at: datetime


@dataclass
class LiveRun:
    run_id: str
    seed: int
    tick_seconds: float
    started_at: datetime
    profiles: dict[str, dict]
    rngs: dict[str, random.Random]
    stop: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    stopped_at: datetime | None = None
    ticks: int = 0
    faults: dict[str, Fault] = field(default_factory=dict)
    injections: int = 0

    @property
    def running(self) -> bool:
        return self.stopped_at is None


def _fault_info(run: LiveRun, f: Fault) -> FaultInfo:
    phase, progress = _fleet().fault_phase(f.kind, run.ticks - 1 - f.injected_tick)
    if run.ticks - 1 < f.injected_tick:  # injected, first faulty tick not sent yet
        phase, progress = "ramping", 0.0
    return FaultInfo(asset_id=f.asset_id, kind=f.kind, phase=phase, injected_at=f.injected_at, progress=round(progress, 3))


def status(store: Store, settings: Settings) -> LiveStatus:
    with store.lock:
        run: LiveRun | None = store.live
        if run is None:
            return LiveStatus(status="stopped", run_id=None, seed=None, tick_seconds=None, started_at=None,
                              stopped_at=None, ticks=0, auto_investigate=settings.auto_investigate, active_faults=[])
        return LiveStatus(status="running" if run.running else "stopped", run_id=run.run_id, seed=run.seed,
                          tick_seconds=run.tick_seconds, started_at=run.started_at, stopped_at=run.stopped_at,
                          ticks=run.ticks, auto_investigate=settings.auto_investigate,
                          active_faults=[_fault_info(run, f) for f in run.faults.values()])


def fault_for(store: Store, asset_id: str) -> FaultInfo | None:
    run: LiveRun | None = store.live
    if run is None or not run.running or asset_id not in run.faults:
        return None
    return _fault_info(run, run.faults[asset_id])


def start(store: Store, req: LiveStartRequest, settings: Settings) -> LiveStatus:
    fleet = _fleet()
    with store.lock:
        if store.live is not None and store.live.running:
            return status(store, settings)
        if any(s.status == "running" for s in store.simulations.values()):
            raise ApiError(409, "SIMULATION_ALREADY_RUNNING",
                           "A single-asset simulation is running; reset it before starting the live fleet.", {})
        assets = all_assets()
        run = LiveRun(
            run_id=store.next_id("live"), seed=req.seed, tick_seconds=req.tick_seconds or settings.live_tick_seconds,
            started_at=now(),
            profiles={a.asset_id: fleet.profile(a.asset_type, a.asset_id, req.seed) for a in assets.values()},
            rngs={a.asset_id: fleet.rng_for(req.seed, a.asset_id) for a in assets.values()},
        )
        store.live = run
        run.thread = threading.Thread(target=_loop, args=(store, run, settings), daemon=True, name=run.run_id)
        run.thread.start()
    return status(store, settings)


def stop(store: Store, settings: Settings) -> LiveStatus:
    with store.lock:
        run: LiveRun | None = store.live
        if run is None or not run.running:
            return status(store, settings)
        run.stop.set()
        thread = run.thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=10)
    with store.lock:
        run.stopped_at = now()
        run.faults.clear()
    return status(store, settings)


def inject(store: Store, req: FaultRequest, settings: Settings) -> FaultResponse:
    fleet = _fleet()
    assets = all_assets()
    unknown = [a for a in req.asset_ids or [] if a not in assets]
    if unknown:
        raise ApiError(404, "ASSET_NOT_FOUND", "Unknown asset ids.", {"asset_ids": unknown})
    with store.lock:
        if store.live is None or not store.live.running:
            start(store, LiveStartRequest(), settings)
        run: LiveRun = store.live
        if req.asset_ids:
            busy = [a for a in req.asset_ids if a in run.faults]
            if busy:
                raise ApiError(409, "FAULT_ALREADY_ACTIVE", "A fault is already running on these assets.", {"asset_ids": busy})
            chosen = list(dict.fromkeys(req.asset_ids))
        else:
            pool = assets
            if req.site is not None:
                from .layout import get_layout
                pool = {a: assets[a] for a in get_layout(req.site).assets}
            chosen = _pick(store, run, pool, req.count)
            if not chosen:
                raise ApiError(409, "NO_HEALTHY_ASSETS", "Every machine already has a fault or an open incident; clear first.", {})
        at = now()
        rng = random.Random(f"{run.seed}:kinds:{run.injections}")
        for asset_id in chosen:
            kind = fleet.fault_kind(assets[asset_id].asset_type, rng)
            run.faults[asset_id] = Fault(asset_id=asset_id, kind=kind, injected_tick=run.ticks, injected_at=at)
        run.injections += 1
        injected = [_fault_info(run, run.faults[a]) for a in chosen]
    return FaultResponse(injected=injected, live=status(store, settings))


def _pick(store: Store, run: LiveRun, assets, count: int) -> list[str]:
    """Machines with no fault and no unresolved incident, one asset type at a time so a demo shows variety."""
    busy = set(run.faults) | {i.asset_id for i in store.incidents.values() if i.status != "resolved"}
    rng = random.Random(f"{run.seed}:faults:{run.injections}")
    pools = {t: sorted(a.asset_id for a in assets.values() if a.asset_type == t and a.asset_id not in busy) for t in TYPE_ORDER}
    for pool in pools.values():
        rng.shuffle(pool)
    chosen: list[str] = []
    while len(chosen) < count and any(pools.values()):
        for t in TYPE_ORDER:
            if pools[t] and len(chosen) < count:
                chosen.append(pools[t].pop())
    return chosen


def clear(store: Store, settings: Settings) -> ClearResponse:
    """Delete every reading, prediction and incident and cancel faults. The live loop keeps running."""
    with store.lock:
        readings = sum(len(r) for r in store.readings.values())
        preds, incs = len(store.predictions), len(store.incidents)
        store.readings.clear()
        store.predictions.clear()
        store.latest_prediction.clear()
        store.incidents.clear()
        store.rule_state.clear()
        faults = 0
        if store.live is not None:
            faults = len(store.live.faults)
            store.live.faults.clear()
        sims = 0
        for sim_id, sim in store.simulations.items():
            if sim.status == "running":
                store.sim_stop[sim_id].set()
                sim.status = "reset"
                sim.completed_at = sim.completed_at or now()
                sims += 1
    return ClearResponse(readings_deleted=readings, predictions_deleted=preds, incidents_deleted=incs,
                         faults_cleared=faults, simulations_reset=sims, live=status(store, settings))


def _loop(store: Store, run: LiveRun, settings: Settings) -> None:
    while not run.stop.is_set():
        started = time.monotonic()
        try:
            _tick(store, run, settings)
        except Exception:  # keep the demo alive; one bad tick must not stop the fleet
            log.exception("live tick failed")
        with store.lock:
            run.ticks += 1
            if run.ticks % 20 == 0:
                _prune(store, settings.live_history_limit)
        run.stop.wait(max(0.0, run.tick_seconds - (time.monotonic() - started)))


def _tick(store: Store, run: LiveRun, settings: Settings) -> None:
    fleet = _fleet()
    ts = now()
    for asset in all_assets().values():
        if run.stop.is_set():
            return
        with store.lock:
            fault = run.faults.get(asset.asset_id)
            progress = 0.0
            if fault is not None:
                phase, progress = fleet.fault_phase(fault.kind, run.ticks - fault.injected_tick)
                if phase == "ended":
                    del run.faults[asset.asset_id]
        values = fleet.sample(asset.asset_type, run.profiles[asset.asset_id], run.ticks, run.rngs[asset.asset_id], progress,
                              fault.kind if fault is not None else None)
        predictions.store_readings(store, ReadingsRequest(
            asset_id=asset.asset_id, data_origin="simulated", simulation_id=run.run_id,
            readings=[Reading(observed_at=ts, values=values)]))
        try:
            pred, _ = predictions.predict(store, PredictionRequest(
                asset_id=asset.asset_id, observed_at=ts, data_origin="simulated", detector_id=asset.compatible_detector,
                readings=values, simulation_id=run.run_id), settings)
        except ApiError as e:  # e.g. a model artifact is missing: keep the reading, skip the score
            log.debug("no prediction for %s: %s", asset.asset_id, e.code)
            continue
        if pred.incident_id and settings.auto_investigate:
            _maybe_queue(store, pred.incident_id, settings)


def _maybe_queue(store: Store, incident_id: str, settings: Settings) -> None:
    with store.lock:
        inc = store.incidents.get(incident_id)
        if inc is None or inc.investigation_status is not None or inc.agent_steps is not None:
            return
        inc.investigation_status = "queued"
        if store.investigator is None:
            # One worker per Gemini key: each investigation is one request, and each (model, key) is paced on its own.
            workers = max(1, len(settings.gemini_keys))
            store.investigator = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="investigate")
        pool = store.investigator
    pool.submit(_investigate, store, incident_id, settings)


def _investigate(store: Store, incident_id: str, settings: Settings) -> None:
    with store.lock:
        inc = store.incidents.get(incident_id)
        if inc is None:  # cleared before its turn
            return
        inc.investigation_status = "running"
    try:
        agent.investigate(store, inc, settings)
        result = "completed"
    except Exception:
        log.exception("auto investigation failed for %s", incident_id)
        result = "failed"
    with store.lock:
        inc.investigation_status = result


def _prune(store: Store, keep: int) -> None:
    """Bound memory on long demos: keep the newest `keep` readings per asset and drop older predictions."""
    cutoff = {}
    for asset_id, rows in store.readings.items():
        if len(rows) > keep:
            del rows[: len(rows) - keep]
            cutoff[asset_id] = rows[0].reading.observed_at
    if cutoff:
        old = [k for k in store.predictions if k[0] in cutoff and k[2] < cutoff[k[0]]]
        for k in old:
            del store.predictions[k]

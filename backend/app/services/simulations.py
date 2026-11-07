"""Backend-owned simulation runs. Values come from @sohaswin's simulator.generate (pure, seeded);
the backend adds timestamps and provenance and sends each sample through readings -> predictions."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from ..core.config import Settings
from ..core.errors import ApiError, not_found
from ..schemas.predictions import PredictionRequest
from ..schemas.readings import Reading, ReadingsRequest
from ..schemas.simulations import SimulationRequest, SimulationResetResponse, SimulationResponse
from . import assets as asset_service
from . import incidents, predictions
from .model_registry import COOLING_RULE_ID
from .store import RuleState, Store


def _generate(scenario: str, seed: int, asset_id: str) -> list[dict[str, float]]:
    try:
        from simulator import generate
    except ImportError as e:  # simulator/ not on this checkout yet
        raise ApiError(503, "SIMULATOR_UNAVAILABLE", "simulator package is not installed.", {}) from e
    return generate(scenario, seed, asset_id)


def start(store: Store, req: SimulationRequest, settings: Settings) -> SimulationResponse:
    asset = asset_service.get_asset(req.asset_id)
    if asset.compatible_detector != COOLING_RULE_ID:
        raise ApiError(422, "UNSUPPORTED_DETECTOR", "Simulation scenarios drive the cooling rule only.",
                       {"asset_id": asset.asset_id, "compatible_detector": asset.compatible_detector})
    samples = _generate(req.scenario, req.seed, req.asset_id)
    with store.lock:
        if store.live is not None and store.live.running:
            raise ApiError(409, "FLEET_LIVE_RUNNING", "The live fleet demo is running; stop it before a single-asset run.", {})
        if any(s.asset_id == req.asset_id and s.status == "running" for s in store.simulations.values()):
            raise ApiError(409, "SIMULATION_ALREADY_RUNNING", f"A simulation is already running on {req.asset_id}.",
                           {"asset_id": req.asset_id})
        sim = SimulationResponse(
            simulation_id=store.next_id("sim"), scenario=req.scenario, asset_id=req.asset_id, seed=req.seed,
            status="running", data_origin="simulated", started_at=datetime.now(UTC), completed_at=None,
            tick_seconds=settings.simulation_tick_seconds, samples_total=len(samples), samples_emitted=0,
        )
        store.simulations[sim.simulation_id] = sim
        stop = store.sim_stop[sim.simulation_id] = threading.Event()
    threading.Thread(target=_run, args=(store, sim.simulation_id, samples, stop, settings), daemon=True).start()
    return sim


def _run(store: Store, sim_id: str, samples, stop: threading.Event, settings: Settings) -> None:
    sim = store.simulations[sim_id]
    for values in samples:
        if stop.is_set():
            return
        ts = datetime.now(UTC)
        predictions.store_readings(store, ReadingsRequest(
            asset_id=sim.asset_id, data_origin="simulated", simulation_id=sim_id,
            readings=[Reading(observed_at=ts, values=values)]))
        predictions.predict(store, PredictionRequest(
            asset_id=sim.asset_id, observed_at=ts, data_origin="simulated", detector_id=COOLING_RULE_ID,
            readings=values, simulation_id=sim_id), settings)
        with store.lock:
            if stop.is_set():
                return
            sim.samples_emitted += 1
        if stop.wait(settings.simulation_tick_seconds):
            return
    with store.lock:
        if sim.status == "running":
            sim.status = "completed"
            sim.completed_at = datetime.now(UTC)


def get(store: Store, sim_id: str) -> SimulationResponse:
    sim = store.simulations.get(sim_id)
    if sim is None:
        raise not_found("SIMULATION_NOT_FOUND", f"Simulation '{sim_id}' does not exist.", simulation_id=sim_id)
    return sim


def list_sims(store: Store, status: str | None, asset_id: str | None, limit: int, offset: int):
    with store.lock:
        items = [s for s in store.simulations.values()
                 if (status is None or s.status == status) and (asset_id is None or s.asset_id == asset_id)]
    items.sort(key=lambda s: s.started_at, reverse=True)
    return items[offset : offset + limit], len(items)


def reset(store: Store, sim_id: str) -> SimulationResetResponse:
    with store.lock:
        sim = get(store, sim_id)
        if sim.status == "reset":
            return SimulationResetResponse(simulation_id=sim_id, status="reset", readings_deleted=0,
                                           predictions_deleted=0, incidents_resolved=0)
        store.sim_stop[sim_id].set()
        rows = store.readings.get(sim.asset_id, [])
        kept = [r for r in rows if r.simulation_id != sim_id]
        readings_deleted = len(rows) - len(kept)
        store.readings[sim.asset_id] = kept
        keys = [k for k, p in store.predictions.items() if p.simulation_id == sim_id]
        for k in keys:
            del store.predictions[k]
        store.rebuild_latest()
        resolved = 0
        for inc in store.incidents.values():
            if inc.simulation_id == sim_id and inc.status != "resolved":
                incidents.resolve(store, inc, "reset", 0)
                resolved += 1
        store.rule_state[sim.asset_id] = RuleState()
        sim.status = "reset"
        sim.completed_at = sim.completed_at or datetime.now(UTC)
    return SimulationResetResponse(simulation_id=sim_id, status="reset", readings_deleted=readings_deleted,
                                   predictions_deleted=len(keys), incidents_resolved=resolved)

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from ...schemas.common import Page
from ...schemas.errors import ErrorResponse
from ...schemas.simulations import SimulationRequest, SimulationResetResponse, SimulationResponse
from ...services import simulations
from ..deps import SettingsDep, StoreDep

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post("", response_model=SimulationResponse, status_code=201,
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
def start(req: SimulationRequest, store: StoreDep, settings: SettingsDep) -> SimulationResponse:
    return simulations.start(store, req, settings)


@router.get("", response_model=Page[SimulationResponse])
def list_sims(
    store: StoreDep,
    status: Literal["running", "completed", "reset"] | None = None,
    asset_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[SimulationResponse]:
    items, total = simulations.list_sims(store, status, asset_id, limit, offset)
    return Page[SimulationResponse](items=items, total=total, limit=limit, offset=offset)


@router.get("/{simulation_id}", response_model=SimulationResponse, responses={404: {"model": ErrorResponse}})
def get_sim(simulation_id: str, store: StoreDep) -> SimulationResponse:
    return simulations.get(store, simulation_id)


@router.post("/{simulation_id}/reset", response_model=SimulationResetResponse, responses={404: {"model": ErrorResponse}})
def reset(simulation_id: str, store: StoreDep) -> SimulationResetResponse:
    return simulations.reset(store, simulation_id)

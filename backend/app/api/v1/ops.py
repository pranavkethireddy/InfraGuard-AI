"""Operations: technicians, repair plan, dispatch and the learning matrix."""

from fastapi import APIRouter

from ...schemas.errors import ErrorResponse
from ...schemas.fleet import SiteId
from ...schemas.ops import (DispatchRequest, DispatchResponse, LearnedCases, LearningMatrix, PlanResponse,
                            TechniciansResponse)
from ...services import learning, ops, whatif
from ..deps import SettingsDep, StoreDep

router = APIRouter(tags=["operations"])


@router.get("/ops/technicians", response_model=TechniciansResponse)
def get_technicians(store: StoreDep, settings: SettingsDep, site: SiteId | None = None) -> TechniciansResponse:
    """Every technician and mechanic: what they are doing now, where, and their open and recent work orders."""
    return ops.technicians(store, settings, site)


@router.get("/ops/plan", response_model=PlanResponse)
def get_plan(store: StoreDep, settings: SettingsDep, site: SiteId = "datacenter") -> PlanResponse:
    """Open incidents ranked by money saved per technician-hour, each with a choice and a technician."""
    return whatif.plan(store, settings, site)


@router.post("/ops/dispatch", response_model=DispatchResponse, status_code=201,
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
def dispatch(req: DispatchRequest, store: StoreDep, settings: SettingsDep) -> DispatchResponse:
    """Create a work order: send (or schedule) a technician, moving them off routine work if needed."""
    return ops.dispatch(store, settings, req)


@router.get("/learning/matrix", response_model=LearningMatrix)
def get_matrix(store: StoreDep, settings: SettingsDep) -> LearningMatrix:
    """What every site has learned, by equipment type and symptom, shared with every site that has that equipment."""
    return learning.matrix(store, settings)


@router.get("/learning/cases", response_model=LearnedCases)
def get_cases(store: StoreDep, settings: SettingsDep, asset_type: str | None = None,
              site: SiteId | None = None) -> LearnedCases:
    return learning.cases(store, settings, asset_type, site)

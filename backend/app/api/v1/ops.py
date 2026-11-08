"""Operations: technicians, floor plan, repair plan, dispatch, technician pager and the learning matrix."""

import time
from collections.abc import Iterator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ...schemas.errors import ErrorResponse
from ...schemas.fleet import SiteId
from ...schemas.ops import (AutoDispatchRequest, DispatchRequest, DispatchResponse, FloorPlan, LearnedCases,
                            LearningMatrix, PagerActionRequest, PagerView, PlanResponse, TechniciansResponse)
from ...services import floor, learning, ops, pager, whatif
from ..deps import SettingsDep, StoreDep

router = APIRouter(tags=["operations"])


@router.get("/ops/technicians", response_model=TechniciansResponse)
def get_technicians(store: StoreDep, settings: SettingsDep, site: SiteId | None = None) -> TechniciansResponse:
    """Every technician and mechanic: what they are doing now, where, and their open and recent work orders."""
    return ops.technicians(store, settings, site)


@router.get("/ops/floor", response_model=FloorPlan)
def get_floor(site: SiteId = "datacenter") -> FloorPlan:
    """Where each hall sits on the site floor, its door and the corridor, for drawing walking technicians."""
    return floor.plan(site)


@router.post("/ops/auto-dispatch", response_model=AutoDispatchRequest)
def set_auto_dispatch(req: AutoDispatchRequest, store: StoreDep, settings: SettingsDep) -> AutoDispatchRequest:
    """Turn automatic dispatch of new incidents to the closest qualified technician on or off."""
    return AutoDispatchRequest(enabled=pager.set_auto(store, settings, req.enabled))


NotFound = {404: {"model": ErrorResponse}}


@router.get("/ops/pager/{technician_id}", response_model=PagerView, responses=NotFound)
def get_pager(technician_id: str, store: StoreDep, settings: SettingsDep) -> PagerView:
    """What this technician's pager shows: their current repair, why them, steps, and the allowed actions."""
    return pager.view(store, settings, technician_id)


@router.post("/ops/pager/{technician_id}/claim", response_model=PagerView, responses=NotFound)
def claim(technician_id: str, store: StoreDep, settings: SettingsDep) -> PagerView:
    """A device (iPad) takes over this technician: repairs wait for it to accept and confirm done."""
    return pager.claim(store, settings, technician_id, True)


@router.post("/ops/pager/{technician_id}/release", response_model=PagerView, responses=NotFound)
def release(technician_id: str, store: StoreDep, settings: SettingsDep) -> PagerView:
    """Hand the technician back to the simulation."""
    return pager.claim(store, settings, technician_id, False)


@router.post("/ops/pager/{technician_id}/action", response_model=PagerView,
             responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
def pager_action(technician_id: str, req: PagerActionRequest, store: StoreDep, settings: SettingsDep) -> PagerView:
    """accept / decline a paged repair, or confirm it done."""
    return pager.act(store, settings, technician_id, req)


@router.get("/ops/stream")
def stream(store: StoreDep, settings: SettingsDep, technician_id: str | None = None,
           site: SiteId | None = None,
           max_seconds: float = Query(default=3600, ge=1, le=86400)) -> StreamingResponse:
    """Server-sent events, pushed as soon as something changes (checked every 0.2 s).
    With technician_id: `event: pager` with a PagerView. Otherwise: `event: crew` with the technicians
    response for the site. A `: ping` comment every 15 s keeps the connection open."""
    if technician_id is not None:
        pager.view(store, settings, technician_id)  # 404 before the stream starts

    def snapshot() -> tuple[str, str]:
        if technician_id is not None:
            return "pager", pager.view(store, settings, technician_id).model_dump_json()
        return "crew", ops.technicians(store, settings, site).model_dump_json()

    def events() -> Iterator[str]:
        last, ping, end = None, time.monotonic(), time.monotonic() + max_seconds
        while time.monotonic() < end:
            kind, body = snapshot()
            if body != last:
                last = body
                yield f"event: {kind}\ndata: {body}\n\n"
            elif time.monotonic() - ping > 15:
                ping = time.monotonic()
                yield ": ping\n\n"
            time.sleep(0.2)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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

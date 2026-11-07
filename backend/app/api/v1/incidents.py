from typing import Annotated, Literal

from fastapi import APIRouter, Query

from ...schemas.common import Page
from ...schemas.errors import ErrorResponse
from ...schemas.incidents import IncidentDetail, IncidentPatchRequest, IncidentSummary
from ...services import incidents
from ...services.model_registry import list_models
from ..deps import SettingsDep, StoreDep

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=Page[IncidentSummary])
def list_incidents(
    store: StoreDep,
    status: Literal["open", "acknowledged", "resolved"] | None = None,
    asset_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[IncidentSummary]:
    items, total = incidents.list_incidents(store, status, asset_id, limit, offset)
    return Page[IncidentSummary](items=items, total=total, limit=limit, offset=offset)


@router.get("/{incident_id}", response_model=IncidentDetail, responses={404: {"model": ErrorResponse}})
def get_incident(incident_id: str, store: StoreDep) -> IncidentDetail:
    return incidents.get(store, incident_id)


@router.patch("/{incident_id}", response_model=IncidentDetail,
              responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})
def patch_incident(incident_id: str, req: IncidentPatchRequest, store: StoreDep, settings: SettingsDep) -> IncidentDetail:
    cooldown = next(m.rule_config["cooldown_readings"] for m in list_models(settings) if m.kind == "rule")
    return incidents.patch(store, incident_id, req, cooldown)


@router.post("/{incident_id}/investigate", response_model=IncidentDetail, responses={404: {"model": ErrorResponse}})
def investigate(incident_id: str, store: StoreDep, settings: SettingsDep) -> IncidentDetail:
    """Run the AI agent: it calls InfraGuard tools and writes a cited fix plan onto the incident."""
    from ...services import agent

    return agent.investigate(store, incidents.get(store, incident_id), settings)

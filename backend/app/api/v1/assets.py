from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from ...schemas.assets import AssetDetail, AssetSummary
from ...schemas.common import Page
from ...schemas.errors import ErrorResponse
from ...schemas.readings import AssetReadingsResponse
from ...services import assets as asset_service
from ..deps import SettingsDep, StoreDep

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=Page[AssetSummary])
def list_assets(
    store: StoreDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AssetSummary]:
    items, total = asset_service.list_assets(limit, offset, store)
    return Page[AssetSummary](items=items, total=total, limit=limit, offset=offset)


@router.get("/{asset_id}", response_model=AssetDetail, responses={404: {"model": ErrorResponse}})
def get_asset(asset_id: str, store: StoreDep, settings: SettingsDep) -> AssetDetail:
    return asset_service.with_state(asset_service.get_asset(asset_id), store, settings.impact_assumptions_path)


@router.get("/{asset_id}/readings", response_model=AssetReadingsResponse, responses={404: {"model": ErrorResponse}})
def get_readings(
    asset_id: str,
    store: StoreDep,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> AssetReadingsResponse:
    asset_service.get_asset(asset_id)
    end = end or datetime.now(UTC) + timedelta(seconds=1)
    start = start or end - timedelta(hours=24)
    with store.lock:
        rows = [r.reading for r in store.readings.get(asset_id, []) if start <= r.reading.observed_at < end]
    return AssetReadingsResponse(asset_id=asset_id, start=start, end=end, items=rows[:limit], total=len(rows), limit=limit)

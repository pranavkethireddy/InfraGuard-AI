from typing import Annotated

from fastapi import APIRouter, Query

from ...schemas.assets import AssetDetail, AssetSummary
from ...schemas.common import Page
from ...schemas.errors import ErrorResponse
from ...services import assets as asset_service

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=Page[AssetSummary])
def list_assets(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AssetSummary]:
    items, total = asset_service.list_assets(limit, offset)
    return Page[AssetSummary](items=items, total=total, limit=limit, offset=offset)


@router.get("/{asset_id}", response_model=AssetDetail, responses={404: {"model": ErrorResponse}})
def get_asset(asset_id: str) -> AssetDetail:
    return asset_service.get_asset(asset_id)

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.config import Settings, get_settings
from ...schemas.common import Page
from ...schemas.models import ModelInfo
from ...services.model_registry import list_models

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=Page[ModelInfo])
def get_models(settings: Annotated[Settings, Depends(get_settings)]) -> Page[ModelInfo]:
    items = list_models(settings)
    return Page[ModelInfo](items=items, total=len(items), limit=50, offset=0)

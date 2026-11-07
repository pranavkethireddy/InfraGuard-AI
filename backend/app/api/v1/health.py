from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.config import APP_VERSION, CONTRACT_VERSION, Settings, get_settings
from ...schemas.health import HealthDependencies, HealthResponse
from ...services.model_registry import list_models

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    models = {m.detector_id: m.status for m in list_models(settings)}
    return HealthResponse(
        status="ok",
        contract_version=CONTRACT_VERSION,
        version=APP_VERSION,
        # Database and retrieval are not built yet; report that rather than "ok".
        dependencies=HealthDependencies(database="not_configured", models=models, retrieval="not_configured"),
    )

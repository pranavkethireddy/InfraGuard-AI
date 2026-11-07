from fastapi import APIRouter

from ...schemas.errors import ErrorResponse
from ...schemas.maintenance import MaintenanceSearchRequest, MaintenanceSearchResponse
from ...services import maintenance
from ..deps import SettingsDep

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.post("/search", response_model=MaintenanceSearchResponse, responses={503: {"model": ErrorResponse}})
def search(req: MaintenanceSearchRequest, settings: SettingsDep) -> MaintenanceSearchResponse:
    return maintenance.search(req, settings.maintenance_records_path)

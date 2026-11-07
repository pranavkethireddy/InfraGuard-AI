from fastapi import APIRouter

from ...schemas.readings import ReadingsRequest, ReadingsResponse
from ...services import predictions
from ..deps import StoreDep

router = APIRouter(prefix="/readings", tags=["readings"])


@router.post("", response_model=ReadingsResponse, status_code=201)
def post_readings(req: ReadingsRequest, store: StoreDep) -> ReadingsResponse:
    return ReadingsResponse(asset_id=req.asset_id, accepted=predictions.store_readings(store, req))

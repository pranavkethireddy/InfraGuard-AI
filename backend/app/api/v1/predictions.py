from fastapi import APIRouter, Response

from ...schemas.errors import ErrorResponse
from ...schemas.predictions import PredictionRequest, PredictionResponse
from ...services import predictions
from ..deps import SettingsDep, StoreDep

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("", response_model=PredictionResponse, status_code=201,
             responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def post_prediction(req: PredictionRequest, response: Response, store: StoreDep, settings: SettingsDep) -> PredictionResponse:
    pred, created = predictions.predict(store, req, settings)
    if not created:
        response.status_code = 200
    return pred

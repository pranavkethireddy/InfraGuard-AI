from fastapi import APIRouter

from . import assets, incidents, models, predictions, readings, simulations

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(assets.router)
api_router.include_router(models.router)
for r in (readings, predictions, incidents, simulations):
    api_router.include_router(r.router)

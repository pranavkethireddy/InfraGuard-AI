from fastapi import APIRouter

from . import assets, models

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(assets.router)
api_router.include_router(models.router)

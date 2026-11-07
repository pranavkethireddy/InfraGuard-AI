"""Every JSON fixture in contracts/fixtures must validate against the backend schemas."""

import json
from pathlib import Path

import pytest

from backend.app.schemas.assets import AssetDetail, AssetSummary
from backend.app.schemas.common import Page
from backend.app.schemas.errors import ErrorResponse
from backend.app.schemas.health import HealthResponse
from backend.app.schemas.incidents import IncidentDetail, IncidentPatchRequest, IncidentSummary
from backend.app.schemas.maintenance import MaintenanceSearchRequest, MaintenanceSearchResponse
from backend.app.schemas.models import ModelInfo
from backend.app.schemas.predictions import PredictionRequest, PredictionResponse
from backend.app.schemas.readings import AssetReadingsResponse, ReadingsRequest, ReadingsResponse
from backend.app.schemas.simulations import SimulationRequest, SimulationResetResponse, SimulationResponse

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"

SCHEMAS = {
    "health.response.json": HealthResponse,
    "assets.list.response.json": Page[AssetSummary],
    "asset.detail.response.json": AssetDetail,
    "asset.readings.response.json": AssetReadingsResponse,
    "readings.request.json": ReadingsRequest,
    "readings.response.json": ReadingsResponse,
    "prediction.cooling.request.json": PredictionRequest,
    "prediction.cooling.response.json": PredictionResponse,
    "prediction.industrial.request.json": PredictionRequest,
    "prediction.industrial.response.json": PredictionResponse,
    "models.list.response.json": Page[ModelInfo],
    "incidents.list.response.json": Page[IncidentSummary],
    "incident.detail.response.json": IncidentDetail,
    "incident.patch.request.json": IncidentPatchRequest,
    "simulation.request.json": SimulationRequest,
    "simulation.response.json": SimulationResponse,
    "simulation.reset.response.json": SimulationResetResponse,
    "maintenance.search.request.json": MaintenanceSearchRequest,
    "maintenance.search.response.json": MaintenanceSearchResponse,
    "error.422.json": ErrorResponse,
    "error.404.json": ErrorResponse,
    "error.409.json": ErrorResponse,
    "error.503.json": ErrorResponse,
}

pytestmark = pytest.mark.skipif(not FIXTURES.is_dir(), reason="contracts/fixtures not on this branch yet (PR #3)")


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_fixture_validates(name):
    SCHEMAS[name].model_validate(json.loads((FIXTURES / name).read_text()))


def test_every_fixture_has_a_schema():
    assert sorted(p.name for p in FIXTURES.glob("*.json")) == sorted(SCHEMAS)

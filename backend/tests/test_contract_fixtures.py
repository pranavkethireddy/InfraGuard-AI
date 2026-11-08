"""Every JSON fixture in contracts/fixtures must validate against the backend schemas."""

import json
from pathlib import Path

import pytest

from backend.app.schemas.assets import AssetDetail, AssetSummary
from backend.app.schemas.common import Page
from backend.app.schemas.errors import ErrorResponse
from backend.app.schemas.common import ContractModel
from backend.app.schemas.fleet import (ClearResponse, FaultRequest, FaultResponse, FleetMap, FleetStatus, JobStatus,
                                       LiveStartRequest, LiveStatus, RackDetail, ServerDetail, SiteMetric, SitesResponse)
from backend.app.schemas.health import HealthResponse
from backend.app.schemas.ops import (DispatchRequest, DispatchResponse, LearnedCases, LearningMatrix, PlanResponse,
                                     TechniciansResponse, WhatIf)
from backend.app.schemas.incidents import IncidentDetail, IncidentPatchRequest, IncidentSummary
from backend.app.schemas.maintenance import MaintenanceSearchRequest, MaintenanceSearchResponse
from backend.app.schemas.models import ModelInfo
from backend.app.schemas.predictions import PredictionRequest, PredictionResponse
from backend.app.schemas.readings import AssetReadingsResponse, ReadingsRequest, ReadingsResponse
from backend.app.schemas.simulations import SimulationRequest, SimulationResetResponse, SimulationResponse

class JobsExcerpt(ContractModel):
    """fleet.jobs.excerpt.json: the jobs and site_metrics fields of a FleetMap."""

    jobs: list[JobStatus]
    site_metrics: list[SiteMetric]


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
    "prediction.cooling.normal.response.json": PredictionResponse,
    "models.list.response.json": Page[ModelInfo],
    "model.evaluated.example.json": ModelInfo,
    "incidents.list.response.json": Page[IncidentSummary],
    "incidents.list.empty.response.json": Page[IncidentSummary],
    "incident.detail.response.json": IncidentDetail,
    "incident.resolved.response.json": IncidentDetail,
    "incident.investigate.response.json": IncidentDetail,
    "incident.patch.request.json": IncidentPatchRequest,
    "fleet.map.response.json": FleetMap,
    "fleet.status.response.json": FleetStatus,
    "fleet.rack.response.json": RackDetail,
    "fleet.server.response.json": ServerDetail,
    "fleet.server.crashed.response.json": ServerDetail,
    "fleet.jobs.excerpt.json": JobsExcerpt,
    "fleet.live.response.json": LiveStatus,
    "fleet.live.start.request.json": LiveStartRequest,
    "fleet.faults.request.json": FaultRequest,
    "fleet.faults.response.json": FaultResponse,
    "fleet.clear.response.json": ClearResponse,
    "fleet.sites.response.json": SitesResponse,
    "fleet.status.mining.response.json": FleetStatus,
    "incident.miner.response.json": IncidentDetail,
    "incident.whatif.response.json": WhatIf,
    "incident.server.whatif.response.json": WhatIf,
    "ops.technicians.response.json": TechniciansResponse,
    "ops.plan.response.json": PlanResponse,
    "ops.dispatch.request.json": DispatchRequest,
    "ops.dispatch.response.json": DispatchResponse,
    "learning.matrix.response.json": LearningMatrix,
    "learning.cases.response.json": LearnedCases,
    "simulation.request.json": SimulationRequest,
    "simulation.response.json": SimulationResponse,
    "simulation.status.response.json": SimulationResponse,
    "simulations.list.response.json": Page[SimulationResponse],
    "simulation.reset.response.json": SimulationResetResponse,
    "maintenance.search.request.json": MaintenanceSearchRequest,
    "maintenance.search.response.json": MaintenanceSearchResponse,
    "maintenance.search.no_evidence.response.json": MaintenanceSearchResponse,
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

from typing import Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel, DataOrigin

Scenario = Literal["normal", "cooling_anomaly"]


class SimulationRequest(ContractModel):
    scenario: Scenario
    asset_id: str
    seed: int = Field(default=42, ge=0)


class SimulationResponse(ContractModel):
    simulation_id: str
    scenario: Scenario
    asset_id: str
    seed: int
    status: Literal["running", "completed", "reset"]
    data_origin: DataOrigin
    started_at: AwareDatetime


class SimulationResetResponse(ContractModel):
    simulation_id: str
    status: Literal["reset"]
    readings_deleted: int = Field(ge=0)
    predictions_deleted: int = Field(ge=0)
    incidents_resolved: int = Field(ge=0)

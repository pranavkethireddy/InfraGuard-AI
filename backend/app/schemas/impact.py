from pydantic import Field

from .common import ContractModel


class ImpactAssumptions(ContractModel):
    currency: str
    estimated_downtime_hours: float = Field(ge=0)
    cost_per_hour: float = Field(ge=0)
    estimated_repair_cost: float = Field(ge=0)
    assumptions_source: str


class Impact(ImpactAssumptions):
    estimated_downtime_cost: float = Field(ge=0)
    estimated_total_impact: float = Field(ge=0)

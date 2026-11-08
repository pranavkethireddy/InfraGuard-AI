from pydantic import Field

from .common import ContractModel


class ImpactAssumptions(ContractModel):
    currency: str
    estimated_downtime_hours: float = Field(ge=0)
    cost_per_hour: float = Field(ge=0)
    estimated_repair_cost: float = Field(ge=0)
    assumptions_source: str
    # Additive (contract v1, optional): cost of one full day down, and hands-on time to fix.
    cost_per_day: float | None = Field(default=None, ge=0)
    estimated_repair_hours: float | None = Field(default=None, ge=0)
    # Additive: cost of fixing it now, before it fails (planned work). Defaults to estimated_repair_cost.
    planned_repair_cost: float | None = Field(default=None, ge=0)


class Impact(ImpactAssumptions):
    estimated_downtime_cost: float = Field(ge=0)
    estimated_total_impact: float = Field(ge=0)
    # Business case (additive). cost_if_it_fails = downtime cost + unplanned repair (= estimated_total_impact);
    # cost_to_fix_now = planned repair; savings_if_fixed_now = the difference; return_on_repair = savings / cost_to_fix_now.
    cost_if_it_fails: float | None = Field(default=None, ge=0)
    cost_to_fix_now: float | None = Field(default=None, ge=0)
    savings_if_fixed_now: float | None = None
    return_on_repair: float | None = None

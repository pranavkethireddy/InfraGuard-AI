from typing import Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel


class MaintenanceSource(ContractModel):
    record_id: str
    asset_id: str | None
    recorded_at: AwareDatetime | None
    source_name: str
    excerpt: str
    score: float | None = None


class MaintenanceSearchRequest(ContractModel):
    asset_id: str | None = None
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class MaintenanceSearchResponse(ContractModel):
    items: list[MaintenanceSource]
    total: int = Field(ge=0)
    status: Literal["ok", "no_evidence"]

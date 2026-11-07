from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

DataOrigin = Literal["simulated", "observed"]
RiskLevel = Literal["low", "medium", "high"]
ScoreKind = Literal["heuristic", "model_score", "calibrated_probability"]
Criticality = Literal["low", "medium", "high"]
ExplanationSource = Literal["rule", "template", "rag"]
IncidentStatus = Literal["open", "acknowledged", "resolved"]
ReadingValue = float | int | str


class ContractModel(BaseModel):
    """Unknown fields are rejected so drift from the contract fails loudly."""

    model_config = ConfigDict(extra="forbid")


class Page(ContractModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)

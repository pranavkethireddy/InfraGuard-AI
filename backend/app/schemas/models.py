from typing import Any, Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel, ScoreKind


class InputField(ContractModel):
    name: str
    unit: str | None
    required: bool


class RiskThresholds(ContractModel):
    medium: float = Field(ge=0, le=1)
    high: float = Field(ge=0, le=1)


class ConfusionMatrix(ContractModel):
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    tn: int = Field(ge=0)
    fn: int = Field(ge=0)


class BaselineMetrics(ContractModel):
    name: str
    pr_auc: float | None
    f1: float | None


class ModelMetrics(ContractModel):
    """Copied from ml/artifacts/metrics/<detector_id>.json. Never filled in by hand."""

    split: Literal["test"]
    evaluated_at: AwareDatetime
    dataset_version: str
    seed: int
    n: int = Field(ge=1)
    positives: int = Field(ge=0)
    threshold: float
    threshold_selection: str
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    pr_auc: float = Field(ge=0, le=1)
    roc_auc: float | None = Field(ge=0, le=1)
    brier: float | None = Field(ge=0, le=1)
    calibrated: bool
    confusion_matrix: ConfusionMatrix
    baseline: BaselineMetrics
    metrics_file: str


class ModelInfo(ContractModel):
    detector_id: str
    model_name: str
    model_version: str
    kind: Literal["rule", "ml"]
    asset_types: list[str]
    score_kind: ScoreKind
    target: str
    prediction_horizon_hours: float | None
    input_fields: list[InputField]
    risk_thresholds: RiskThresholds | None
    rule_config: dict[str, Any] | None
    status: Literal["available", "unavailable"]
    evaluation_status: Literal["evaluated", "not_evaluated", "not_applicable"]
    metrics: ModelMetrics | None
    source_dataset: str | None
    model_card_url: str | None
    limitations: list[str]

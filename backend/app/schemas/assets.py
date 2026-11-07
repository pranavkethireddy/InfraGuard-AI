from pydantic import AwareDatetime

from .common import ContractModel, Criticality, DataOrigin, RiskLevel
from .impact import ImpactAssumptions


class AssetSummary(ContractModel):
    asset_id: str
    name: str
    asset_type: str
    location: str
    criticality: Criticality
    compatible_detector: str
    data_origin: DataOrigin
    current_risk_level: RiskLevel | None
    active_incident_id: str | None
    last_reading_at: AwareDatetime | None


class AssetDetail(AssetSummary):
    impact_assumptions: ImpactAssumptions | None

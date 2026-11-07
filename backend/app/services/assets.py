"""Seeded demo assets. In-memory until the SQLite layer (backend/app/db) lands."""

from ..core.errors import not_found
from ..schemas.assets import AssetDetail, AssetSummary
from ..schemas.impact import ImpactAssumptions
from .model_registry import COOLING_RULE_ID, INDUSTRIAL_ID

_PLACEHOLDER_SOURCE = "placeholder demo assumption, not measured; to be agreed with @sohaswin in configs/"

_ASSETS: dict[str, AssetDetail] = {
    a.asset_id: a
    for a in [
        AssetDetail(
            asset_id="cooling-01", name="CRAC Unit 1", asset_type="cooling_unit", location="Hall A",
            criticality="high", compatible_detector=COOLING_RULE_ID, data_origin="simulated",
            current_risk_level=None, active_incident_id=None, last_reading_at=None,
            impact_assumptions=ImpactAssumptions(
                currency="USD", estimated_downtime_hours=4.0, cost_per_hour=12000.0,
                estimated_repair_cost=3500.0, assumptions_source=_PLACEHOLDER_SOURCE,
            ),
        ),
        AssetDetail(
            asset_id="mill-01", name="AI4I Demo Machine", asset_type="industrial_machine",
            location="Benchmark (AI4I synthetic)", criticality="medium", compatible_detector=INDUSTRIAL_ID,
            data_origin="simulated", current_risk_level=None, active_incident_id=None, last_reading_at=None,
            impact_assumptions=None,
        ),
    ]
}


def list_assets(limit: int, offset: int) -> tuple[list[AssetSummary], int]:
    items = sorted(_ASSETS.values(), key=lambda a: a.asset_id)
    page = [AssetSummary(**a.model_dump(exclude={"impact_assumptions"})) for a in items[offset : offset + limit]]
    return page, len(items)


def get_asset(asset_id: str) -> AssetDetail:
    asset = _ASSETS.get(asset_id)
    if asset is None:
        raise not_found("ASSET_NOT_FOUND", f"Asset '{asset_id}' does not exist.", asset_id=asset_id)
    return asset

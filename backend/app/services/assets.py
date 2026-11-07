"""Seeded demo assets. In-memory until the SQLite layer (backend/app/db) lands."""

from ..core.errors import not_found
from ..schemas.assets import AssetDetail, AssetSummary
from .impact import load_assumptions
from .model_registry import COOLING_RULE_ID, DRIVE_ID, INDUSTRIAL_ID
from .store import Store

_ASSETS: dict[str, AssetDetail] = {
    a.asset_id: a
    for a in [
        AssetDetail(
            asset_id="cooling-01", name="CRAC Unit 1", asset_type="cooling_unit", location="Hall A",
            criticality="high", compatible_detector=COOLING_RULE_ID, data_origin="simulated",
            current_risk_level=None, active_incident_id=None, last_reading_at=None, impact_assumptions=None,
        ),
        AssetDetail(
            asset_id="drive-01", name="Storage Node 7, Drive Bay 3", asset_type="storage_drive",
            location="Hall A, Rack 12", criticality="medium", compatible_detector=DRIVE_ID,
            data_origin="simulated", current_risk_level=None, active_incident_id=None, last_reading_at=None,
            impact_assumptions=None,
        ),
        AssetDetail(
            asset_id="mill-01", name="AI4I Demo Machine", asset_type="industrial_machine",
            location="Benchmark (AI4I synthetic)", criticality="medium", compatible_detector=INDUSTRIAL_ID,
            data_origin="simulated", current_risk_level=None, active_incident_id=None, last_reading_at=None,
            impact_assumptions=None,
        ),
    ]
}


def with_state(asset: AssetDetail, store: Store | None, assumptions_path: str | None) -> AssetDetail:
    """Static asset plus live state (latest risk, active incident, last reading) and configs/ assumptions."""
    update: dict = {}
    if assumptions_path:
        update["impact_assumptions"] = load_assumptions(assumptions_path).get(asset.asset_id)
    if store is not None:
        with store.lock:
            preds = [p for p in store.predictions.values() if p.asset_id == asset.asset_id]
            rows = store.readings.get(asset.asset_id, [])
            inc = store.active_incident(asset.asset_id, asset.compatible_detector)
        latest = max(preds, key=lambda p: p.observed_at, default=None)
        update |= {
            "current_risk_level": latest.risk_level if latest else None,
            "active_incident_id": inc.incident_id if inc else None,
            "last_reading_at": rows[-1].reading.observed_at if rows else None,
        }
    return asset.model_copy(update=update)


def list_assets(limit: int, offset: int, store: Store | None = None) -> tuple[list[AssetSummary], int]:
    items = sorted(_ASSETS.values(), key=lambda a: a.asset_id)
    page = [AssetSummary(**with_state(a, store, None).model_dump(exclude={"impact_assumptions"}))
            for a in items[offset : offset + limit]]
    return page, len(items)


def get_asset(asset_id: str) -> AssetDetail:
    asset = _ASSETS.get(asset_id)
    if asset is None:
        raise not_found("ASSET_NOT_FOUND", f"Asset '{asset_id}' does not exist.", asset_id=asset_id)
    return asset

"""Demo assets from both site layouts in configs/ (data center and mining farm). In-memory until the SQLite layer (backend/app/db) lands."""

from ..core.errors import not_found
from ..schemas.assets import AssetDetail, AssetSummary
from .impact import for_asset
from functools import lru_cache

from .layout import load, site_paths
from .store import Store


@lru_cache
def _union(paths: tuple[str, ...]) -> dict[str, AssetDetail]:
    out: dict[str, AssetDetail] = {}
    for p in paths:
        out |= load(p).assets
    return out


def all_assets() -> dict[str, AssetDetail]:
    return _union(tuple(site_paths().values()))


def with_state(asset: AssetDetail, store: Store | None, assumptions_path: str | None) -> AssetDetail:
    """Static asset plus live state (latest risk, active incident, last reading) and configs/ assumptions."""
    update: dict = {}
    if assumptions_path:
        update["impact_assumptions"] = for_asset(assumptions_path, asset.asset_id, asset.asset_type)
    if store is not None:
        with store.lock:
            latest = store.latest_prediction.get(asset.asset_id)
            rows = store.readings.get(asset.asset_id, [])
            inc = store.active_incident(asset.asset_id, asset.compatible_detector)
            last_at = rows[-1].reading.observed_at if rows else None
        update |= {
            "current_risk_level": latest.risk_level if latest else None,
            "active_incident_id": inc.incident_id if inc else None,
            "last_reading_at": last_at,
        }
    return asset.model_copy(update=update)


def list_assets(limit: int, offset: int, store: Store | None = None) -> tuple[list[AssetSummary], int]:
    items = sorted(all_assets().values(), key=lambda a: a.asset_id)
    page = [AssetSummary(**with_state(a, store, None).model_dump(exclude={"impact_assumptions"}))
            for a in items[offset : offset + limit]]
    return page, len(items)


def get_asset(asset_id: str) -> AssetDetail:
    asset = all_assets().get(asset_id)
    if asset is None:
        raise not_found("ASSET_NOT_FOUND", f"Asset '{asset_id}' does not exist.", asset_id=asset_id)
    return asset

"""Business impact from labelled assumptions in configs/. Authoritative; React only displays it."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..schemas.impact import Impact, ImpactAssumptions


def _parse(raw: dict, section: str) -> dict[str, ImpactAssumptions]:
    return {
        key: ImpactAssumptions(currency=raw["currency"], assumptions_source=raw["assumptions_source"],
                               cost_per_day=a["cost_per_hour"] * 24, **a)
        for key, a in raw.get(section, {}).items()
    }


@lru_cache
def _load(path: str) -> tuple[dict[str, ImpactAssumptions], dict[str, ImpactAssumptions]]:
    p = Path(path)
    if not p.is_file():
        return {}, {}
    raw = json.loads(p.read_text())
    return _parse(raw, "assets"), _parse(raw, "asset_type_defaults")


def load_assumptions(path: str) -> dict[str, ImpactAssumptions]:
    """Per-asset entries only."""
    return _load(path)[0]


def for_asset(path: str, asset_id: str, asset_type: str) -> ImpactAssumptions | None:
    """The asset's own entry, else the default for its asset type, else None."""
    per_asset, per_type = _load(path)
    return per_asset.get(asset_id) or per_type.get(asset_type)


def compute(a: ImpactAssumptions) -> Impact:
    downtime_cost = a.estimated_downtime_hours * a.cost_per_hour
    return Impact(
        **a.model_dump(),
        estimated_downtime_cost=downtime_cost,
        estimated_total_impact=downtime_cost + a.estimated_repair_cost,
    )


def max_total_impact(path: str) -> float:
    per_asset, per_type = _load(path)
    totals = [compute(a).estimated_total_impact for a in [*per_asset.values(), *per_type.values()]]
    return max(totals, default=0.0)

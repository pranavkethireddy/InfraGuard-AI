"""Business impact from labelled assumptions in configs/. Authoritative; React only displays it."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..schemas.impact import Impact, ImpactAssumptions


@lru_cache
def load_assumptions(path: str) -> dict[str, ImpactAssumptions]:
    p = Path(path)
    if not p.is_file():
        return {}
    raw = json.loads(p.read_text())
    out = {}
    for asset_id, a in raw["assets"].items():
        out[asset_id] = ImpactAssumptions(
            currency=raw["currency"],
            assumptions_source=raw["assumptions_source"],
            cost_per_day=a["cost_per_hour"] * 24,
            **a,
        )
    return out


def compute(a: ImpactAssumptions) -> Impact:
    downtime_cost = a.estimated_downtime_hours * a.cost_per_hour
    return Impact(
        **a.model_dump(),
        estimated_downtime_cost=downtime_cost,
        estimated_total_impact=downtime_cost + a.estimated_repair_cost,
    )


def max_total_impact(path: str) -> float:
    totals = [compute(a).estimated_total_impact for a in load_assumptions(path).values()]
    return max(totals, default=0.0)

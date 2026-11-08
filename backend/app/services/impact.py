"""Business impact from labelled assumptions in configs/. Authoritative; React only displays it."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..schemas.impact import Impact, ImpactAssumptions

# Entries with "cost_basis": "hashprice" price downtime as lost mining revenue from the daily hashprice.
HASHPRICE = "hashprice"
# Entries with "cost_basis": "gpu_job" price downtime as the whole row's GPU job standing still.
GPU_JOB = "gpu_job"


def _parse(raw: dict, section: str) -> dict[str, tuple[ImpactAssumptions, str | None]]:
    out = {}
    for key, a in raw.get(section, {}).items():
        a = dict(a)
        basis = a.pop("cost_basis", None)
        a.setdefault("cost_per_hour", 0.0)
        a.setdefault("planned_repair_cost", a["estimated_repair_cost"])
        out[key] = (ImpactAssumptions(currency=raw["currency"], assumptions_source=raw["assumptions_source"],
                                      cost_per_day=a["cost_per_hour"] * 24, **a), basis)
    return out


@lru_cache
def _raw(path: str):
    p = Path(path)
    if not p.is_file():
        return {}, {}
    raw = json.loads(p.read_text())
    return _parse(raw, "assets"), _parse(raw, "asset_type_defaults")


def _load(path: str) -> tuple[dict[str, ImpactAssumptions], dict[str, ImpactAssumptions]]:
    per_asset, per_type = _raw(path)
    return {k: v[0] for k, v in per_asset.items()}, {k: v[0] for k, v in per_type.items()}


def _priced(asset_id: str, a: ImpactAssumptions) -> ImpactAssumptions | None:
    """Fill cost_per_hour from the hashprice data. None if the data file is missing."""
    from ..core.config import get_settings
    from . import mining

    path = get_settings().hashprice_data_path
    per_day, hp = mining.revenue_per_day(asset_id, path), mining.hashprice(path)
    if per_day is None or hp is None:
        return None
    src = (f"{a.assumptions_source}; lost revenue = rated hashrate x hashprice ${hp.usd_per_th_day:.4f}/TH/day "
           f"on {hp.as_of} ({mining.SOURCE})")
    return a.model_copy(update={"cost_per_hour": round(per_day / 24, 4), "cost_per_day": round(per_day, 2), "assumptions_source": src})


def load_assumptions(path: str) -> dict[str, ImpactAssumptions]:
    """Per-asset entries only."""
    return _load(path)[0]


def for_asset(path: str, asset_id: str, asset_type: str) -> ImpactAssumptions | None:
    """The asset's own entry, else the default for its asset type, else None."""
    per_asset, per_type = _raw(path)
    entry = per_asset.get(asset_id) or per_type.get(asset_type)
    if entry is None:
        return None
    a, basis = entry
    if basis == HASHPRICE:
        return _priced(asset_id, a)
    if basis == GPU_JOB:
        return _gpu_job(asset_id, a)
    return a


def _gpu_job(asset_id: str, a: ImpactAssumptions) -> ImpactAssumptions:
    """cost_per_hour = GPUs in the server's job x GPU-hour price: a stopped server stalls the whole job."""
    from . import gpus

    job = gpus.job_rate(asset_id)
    if job is None:
        return a
    name, n_gpus, per_gpu = job
    src = f"{a.assumptions_source}; downtime stalls {name}: {n_gpus} GPUs x ${per_gpu:.2f}/GPU-hour ({gpus.PRICE_SOURCE})"
    return a.model_copy(update={"cost_per_hour": round(n_gpus * per_gpu, 2), "cost_per_day": round(n_gpus * per_gpu * 24, 2),
                                "assumptions_source": src})


def compute(a: ImpactAssumptions) -> Impact:
    downtime_cost = a.estimated_downtime_hours * a.cost_per_hour
    total = downtime_cost + a.estimated_repair_cost
    fix_now = a.planned_repair_cost if a.planned_repair_cost is not None else a.estimated_repair_cost
    savings = total - fix_now
    return Impact(
        **a.model_dump(),
        estimated_downtime_cost=round(downtime_cost, 2),
        estimated_total_impact=round(total, 2),
        cost_if_it_fails=round(total, 2),
        cost_to_fix_now=round(fix_now, 2),
        savings_if_fixed_now=round(savings, 2),
        return_on_repair=round(savings / fix_now, 2) if fix_now > 0 else None,
    )


def max_total_impact(path: str) -> float:
    per_asset, per_type = _load(path)
    totals = [compute(a).estimated_total_impact for a in [*per_asset.values(), *per_type.values()]]
    return max(totals, default=0.0)

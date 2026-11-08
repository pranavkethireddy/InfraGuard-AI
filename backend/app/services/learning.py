"""Learning matrix: every finished repair (or operator resolution with a note) becomes a case.

Cases are kept in a JSON file (settings.learned_cases_path) so they survive restarts and /fleet/clear,
and are shared across sites: an investigation at any site that has the same equipment type can cite
them. The matrix groups cases by equipment type and symptom: how often, at which sites, typical repair
time and cost, how often it was caught before failure, and the fix that worked most often.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..core.config import Settings
from ..schemas.maintenance import MaintenanceSource
from ..schemas.ops import LearnedCase, LearnedCases, LearningMatrix, MatrixRow
from .assets import all_assets
from .incidents import now
from .layout import all_layouts, site_of
from .store import Store

SOURCE = "InfraGuard learned case"


def _cases(store: Store, settings: Settings) -> list[LearnedCase]:
    if store.learning is None:
        p = Path(settings.learned_cases_path)
        items = []
        if p.is_file():
            try:
                items = [LearnedCase.model_validate(x) for x in json.loads(p.read_text())]
            except (ValueError, TypeError):
                items = []
        store.learning = items
    return store.learning


def _save(store: Store, settings: Settings) -> None:
    p = Path(settings.learned_cases_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps([c.model_dump(mode="json") for c in store.learning], indent=1))
    tmp.replace(p)


LABELS = {"temperature_c": "high temperature", "chip_temp_c": "chip overheating", "fan_speed_rpm": "fan failing",
          "hashrate_ths": "hashrate drop", "hw_error_pct": "hardware errors", "reallocated_sectors": "reallocated sectors",
          "pending_sectors": "pending sectors", "torque_nm": "high torque", "tool_wear_min": "tool wear"}


def symptom(inc) -> str:
    if inc.detector_id in ("drive-failure-v1", "industrial-failure-v1"):
        return "predicted failure (model)"
    fields = sorted({e.field for e in inc.evidence})
    return " + ".join(LABELS.get(f, f.replace("_", " ")) for f in fields) or inc.detector_id


def record(store: Store, settings: Settings, inc, fix: str, hours: float, cost: float, outcome: str,
           source: str) -> LearnedCase:
    """Called under store.lock."""
    cases = _cases(store, settings)
    asset = all_assets()[inc.asset_id]
    lay = site_of(inc.asset_id)
    case = LearnedCase(case_id=f"lc-{len(cases) + 1:04d}", site_id=lay.site_id if lay else "unknown",
                       asset_id=inc.asset_id, asset_type=asset.asset_type, detector_id=inc.detector_id,
                       symptom=symptom(inc), cause=inc.likely_cause, fix=fix, repair_hours=round(hours, 2),
                       cost=round(cost, 2), outcome=outcome, learned_at=now(), source=source)
    cases.append(case)
    try:
        _save(store, settings)
    except OSError:  # keep learning in memory even if the disk is read-only
        pass
    return case


def search(store: Store, settings: Settings, inc, limit: int = 3) -> list[MaintenanceSource]:
    """Cases for the same equipment type from every site, closest symptom first, newest next."""
    asset_type = all_assets()[inc.asset_id].asset_type
    want = set(symptom(inc).split(" + "))
    with store.lock:
        pool = [c for c in _cases(store, settings) if c.asset_type == asset_type]
    pool.sort(key=lambda c: (len(want & set(c.symptom.split(" + "))), c.learned_at), reverse=True)
    out = []
    for c in pool[:limit]:
        overlap = len(want & set(c.symptom.split(" + "))) / max(1, len(want))
        cause = f" Cause: {c.cause}" if c.cause else ""
        out.append(MaintenanceSource(
            record_id=c.case_id, asset_id=c.asset_id, recorded_at=c.learned_at, source_name=f"{SOURCE} ({c.site_id})",
            excerpt=(f"{c.symptom} on {c.asset_id} at {c.site_id}.{cause} Fix: {c.fix}. "
                     f"{c.repair_hours} h, ${c.cost:,.2f}, {c.outcome.replace('_', ' ')}.")[:400],
            score=round(overlap, 4)))
    return out


def cases(store: Store, settings: Settings, asset_type: str | None, site: str | None) -> LearnedCases:
    with store.lock:
        items = [c for c in _cases(store, settings)
                 if (asset_type is None or c.asset_type == asset_type) and (site is None or c.site_id == site)]
    items = sorted(items, key=lambda c: c.learned_at, reverse=True)
    return LearnedCases(items=items, total=len(items))


def matrix(store: Store, settings: Settings) -> LearningMatrix:
    with store.lock:
        all_cases = list(_cases(store, settings))
    sites_with = {}
    for lay in all_layouts():
        for a in lay.assets.values():
            sites_with.setdefault(a.asset_type, set()).add(lay.site_id)
    groups: dict[tuple[str, str], list[LearnedCase]] = {}
    for c in all_cases:
        groups.setdefault((c.asset_type, c.symptom), []).append(c)
    rows = []
    for (asset_type, sym), cs in groups.items():
        # Hours and cost only come from technician work orders; operator notes carry none.
        timed = [c for c in cs if c.source == "technician"] or cs
        rows.append(MatrixRow(
            asset_type=asset_type, symptom=sym, cases=len(cs), sites_seen=sorted({c.site_id for c in cs}),
            shared_with_sites=sorted(sites_with.get(asset_type, set())),
            avg_repair_hours=round(sum(c.repair_hours for c in timed) / len(timed), 2),
            avg_cost=round(sum(c.cost for c in timed) / len(timed), 2),
            fixed_before_failure_pct=round(100 * sum(c.outcome == "fixed_before_failure" for c in cs) / len(cs), 1),
            best_fix=Counter(c.fix for c in cs).most_common(1)[0][0],
            last_learned_at=max(c.learned_at for c in cs)))
    rows.sort(key=lambda r: (-r.cases, r.asset_type, r.symptom))
    return LearningMatrix(total_cases=len(all_cases), rows=rows)

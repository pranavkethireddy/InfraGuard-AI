"""Incident lifecycle, priority and template explanations (contract: Incidents)."""

from __future__ import annotations

from datetime import UTC, datetime

from ..core.config import Settings
from ..core.errors import ApiError, not_found
from ..schemas.incidents import IncidentDetail, IncidentNote, IncidentPatchRequest, IncidentSummary
from ..schemas.predictions import PredictionResponse
from . import impact as impact_service
from .store import Store

PRIORITY_WEIGHTS = {"risk": 0.5, "criticality": 0.3, "impact": 0.2}
_LEVEL = {"low": 0.0, "medium": 0.5, "high": 1.0}
TRANSITIONS = {"open": {"acknowledged", "resolved"}, "acknowledged": {"resolved"}, "resolved": set()}

# Template actions per detector; the AI agent replaces these with cited, specific steps.
ACTIONS = {
    "cooling-rule-v1": ["Inspect the unit's air filter and fan (human review required).",
                        "Check supply and return air temperatures against the setpoint."],
    "industrial-failure-v1": ["Inspect tool wear and torque load before the next run (human review required)."],
    "drive-failure-v1": ["Back up or migrate data from this drive and confirm RAID redundancy.",
                         "Schedule a hot-swap replacement (human review required)."],
    "miner-rule-v1": ["Check the miner's fans and intake for dust or blockage (human review required).",
                      "If one hashboard is down, schedule a hashboard swap and move the unit to repair."],
    "server-rule-v1": ["Check the server's GPUs, power supplies and logs, then reseat or swap the failed part (human review required).",
                       "Restart the row's job from its last checkpoint without this server so the other GPUs keep working."],
}


def now() -> datetime:
    return datetime.now(UTC)


def priority(risk_level: str, criticality: str, total_impact: float | None, settings: Settings) -> float:
    top = impact_service.max_total_impact(settings.impact_assumptions_path)
    impact_part = (total_impact / top) if (total_impact is not None and top > 0) else 0.0
    w = PRIORITY_WEIGHTS
    return round(w["risk"] * _LEVEL[risk_level] + w["criticality"] * _LEVEL[criticality] + w["impact"] * impact_part, 4)


def rank(priority_index: float | None) -> int:
    """1 = fix first ... 5 = can wait."""
    p = priority_index or 0.0
    return 1 if p >= 0.8 else 2 if p >= 0.6 else 3 if p >= 0.4 else 4 if p >= 0.2 else 5


APPROVAL = "A human must approve physical work."


def _apply_playbook(store: Store, inc: IncidentDetail, asset_type: str) -> None:
    """Match the failure playbook from the asset's recent readings; its steps become the recommended actions."""
    from . import diagnosis

    rows = store.readings.get(inc.asset_id, [])[-60:]
    mode = diagnosis.diagnose(asset_type, [dict(r.reading.values) for r in rows])
    if mode is None:
        return
    changed = inc.failure_mode is None or inc.failure_mode.mode_id != mode.mode_id
    inc.failure_mode = mode
    if changed:
        inc.recommended_actions = [*mode.steps, APPROVAL]
        if not inc.likely_cause or inc.explanation_source in ("template", "rule"):
            inc.likely_cause = f"{mode.title}: {mode.reasoning}"


def open_or_update(store: Store, pred: PredictionResponse, asset, settings: Settings) -> IncidentDetail:
    """Called under store.lock for a triggering prediction."""
    inc = store.active_incident(pred.asset_id, pred.detector_id)
    if inc is not None:
        inc.last_seen_at = pred.observed_at
        inc.prediction_count += 1
        inc.latest_prediction = pred
        if pred.risk_level != inc.risk_level:  # re-rank: medium -> high moves it up the queue
            inc.priority_index = priority(pred.risk_level, asset.criticality,
                                          inc.impact.estimated_total_impact if inc.impact else None, settings)
            new = rank(inc.priority_index)
            if inc.priority_rank is not None and new < inc.priority_rank and inc.incident_id not in store.escalated:
                store.escalated.append(inc.incident_id)
            inc.priority_rank = new
        inc.risk_level = pred.risk_level
        inc.evidence = pred.evidence
        if inc.failure_mode is None or inc.prediction_count % 5 == 0:
            _apply_playbook(store, inc, asset.asset_type)
        return inc
    assumptions = impact_service.for_asset(settings.impact_assumptions_path, asset.asset_id, asset.asset_type)
    imp = impact_service.compute(assumptions) if assumptions else None
    title = {
        "cooling-rule-v1": f"Sustained high temperature on {asset.name}",
        "drive-failure-v1": f"Predicted drive failure within 30 days: {asset.name}",
        "miner-rule-v1": f"ASIC miner fault: {asset.name}",
        "server-rule-v1": f"GPU server fault: {asset.name}",
    }.get(pred.detector_id, f"Elevated failure risk on {asset.name}")
    p_index = priority(pred.risk_level, asset.criticality, imp.estimated_total_impact if imp else None, settings)
    inc = IncidentDetail(
        incident_id=store.next_id("inc"), asset_id=pred.asset_id, detector_id=pred.detector_id, status="open",
        risk_level=pred.risk_level, score_kind=pred.score_kind, data_origin=pred.data_origin, title=title,
        opened_at=pred.observed_at, last_seen_at=pred.observed_at, acknowledged_at=None, resolved_at=None,
        resolved_by=None, prediction_count=1, simulation_id=pred.simulation_id,
        priority_index=p_index, priority_rank=rank(p_index),
        latest_prediction=pred, evidence=pred.evidence, maintenance_sources=[], explanation=pred.explanation,
        explanation_source="template" if pred.explanation_source != "rule" else "rule",
        recommended_actions=list(ACTIONS.get(pred.detector_id, [])), impact=imp, priority_weights=PRIORITY_WEIGHTS,
        notes=[], agent_steps=None,
    )
    _apply_playbook(store, inc, asset.asset_type)
    store.incidents[inc.incident_id] = inc
    return inc


def summary(inc: IncidentDetail) -> IncidentSummary:
    return IncidentSummary(**inc.model_dump(include=set(IncidentSummary.model_fields)))


def list_incidents(store: Store, status: str | None, asset_id: str | None, limit: int, offset: int):
    with store.lock:
        items = [i for i in store.incidents.values()
                 if (status is None or i.status == status) and (asset_id is None or i.asset_id == asset_id)]
    items.sort(key=lambda i: (i.status == "resolved", -(i.priority_index or 0), i.opened_at))
    return [summary(i) for i in items[offset : offset + limit]], len(items)


def get(store: Store, incident_id: str) -> IncidentDetail:
    inc = store.incidents.get(incident_id)
    if inc is None:
        raise not_found("INCIDENT_NOT_FOUND", f"Incident '{incident_id}' does not exist.", incident_id=incident_id)
    return inc


def resolve(store: Store, inc: IncidentDetail, by: str, cooldown: int) -> None:
    inc.status = "resolved"
    inc.resolved_at = now()
    inc.resolved_by = by
    st = store.rule_state.get(inc.asset_id)
    if st is not None and by in ("operator", "technician"):
        st.cooldown_remaining = cooldown
        st.consecutive_above = 0


def patch(store: Store, incident_id: str, req: IncidentPatchRequest, cooldown: int) -> IncidentDetail:
    with store.lock:
        inc = get(store, incident_id)
        if req.status not in TRANSITIONS[inc.status]:
            raise ApiError(409, "INVALID_TRANSITION", f"Cannot move incident from {inc.status} to {req.status}.",
                           {"from": inc.status, "to": req.status})
        if req.status == "acknowledged":
            inc.status = "acknowledged"
            inc.acknowledged_at = now()
        else:
            resolve(store, inc, "operator", cooldown)
        if req.note:
            inc.notes.append(IncidentNote(note=req.note, status=inc.status, created_at=now()))
        return inc

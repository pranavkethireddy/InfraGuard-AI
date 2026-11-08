"""InfraGuard incident agent.

The backend runs the InfraGuard tools itself (incident and model output, model card, impact, maintenance
search, recent readings), all local and fast, then makes ONE Gemini request with the results. Gemini
writes the problem, likely cause, fix plan and money at stake, citing maintenance record IDs. One request
per incident keeps the free tier lasting about 4x longer than a multi-turn tool loop. Numbers come only
from tool results; Gemini is told never to invent costs or times. Without GEMINI_API_KEY (or if Gemini fails) a
deterministic fallback runs the same tools and fills a template, marked explanation_source="rag".
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Callable

import httpx

from ..core.config import Settings
from ..core.errors import ApiError
from ..schemas.incidents import AgentStep, IncidentDetail
from ..schemas.maintenance import MaintenanceSearchRequest
from . import assets as asset_service
from . import impact as impact_service
from . import maintenance
from .model_registry import list_models
from .store import Store

log = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM = """You are InfraGuard, an operations agent for data centers and crypto mining farms. You get the tool
results for one incident (incident, model card, impact, maintenance records, recent readings). Write the case
for the operator: the problem, the likely cause, how to fix it, and what it costs to fix now versus if it fails.
Rules: use only numbers in the tool results; never invent costs, times, or records; cite maintenance records by
record_id and say which unit a record is from (records may come from similar equipment); say clearly when
evidence is missing; a human must approve any physical work.
Answer with ONLY this JSON object:
{"problem": "<1 sentence: what is wrong, on which machine, where>",
 "likely_cause": "<1 sentence from the readings and records, or say the cause is unknown>",
 "explanation": "<3-5 sentences: evidence, likely cause, cost if it fails vs cost to fix now and the savings, repair time>",
 "recommended_actions": ["<step 1>", "<step 2>", "..."],
 "cited_record_ids": ["mr-..."]}"""

class Toolbox:
    def __init__(self, store: Store, inc: IncidentDetail, settings: Settings):
        self.store, self.inc, self.settings = store, inc, settings
        self.steps: list[AgentStep] = []
        self.sources: dict[str, Any] = {}

    def call(self, name: str, args: dict) -> dict:
        fn: Callable[..., dict] | None = getattr(self, f"t_{name}", None)
        try:
            out = fn(**args) if fn else {"error": f"unknown tool {name}"}
        except Exception as e:  # tool errors go back to the model, not to the user
            out = {"error": str(e)}
        self.steps.append(AgentStep(tool=name, summary=_summ(name, args, out)))
        return out

    def t_get_incident(self) -> dict:
        i = self.inc
        p = i.latest_prediction
        asset = asset_service.get_asset(i.asset_id)
        return {"incident_id": i.incident_id, "asset_id": i.asset_id, "asset_name": asset.name, "location": asset.location,
                "detector_id": i.detector_id, "status": i.status, "risk_level": i.risk_level, "title": i.title,
                "prediction_count": i.prediction_count, "data_origin": i.data_origin,
                "evidence": [e.model_dump(exclude_none=True) for e in i.evidence],
                "latest": None if p is None else {"risk_score": p.risk_score, "score_kind": p.score_kind,
                                                  "horizon_hours": p.prediction_horizon_hours, "explanation": p.explanation}}

    def t_get_model_card(self, detector_id: str) -> dict:
        m = {x.detector_id: x for x in list_models(self.settings)}.get(detector_id)
        if m is None:
            return {"error": "unknown detector"}
        met = m.metrics
        return {"target": m.target, "kind": m.kind, "horizon_hours": m.prediction_horizon_hours,
                "evaluation_status": m.evaluation_status, "limitations": m.limitations,
                "test_metrics": None if met is None else {"pr_auc": met.pr_auc, "precision": met.precision,
                                                          "recall": met.recall, "n": met.n, "dataset": met.dataset_version},
                "rule_config": m.rule_config}

    def t_estimate_impact(self, asset_id: str) -> dict:
        try:
            asset_type = asset_service.get_asset(asset_id).asset_type
        except ApiError:
            return {"error": "unknown asset"}
        a = impact_service.for_asset(self.settings.impact_assumptions_path, asset_id, asset_type)
        return {"error": "no impact assumptions for this asset"} if a is None else impact_service.compute(a).model_dump()

    def t_search_maintenance(self, query: str, asset_id: str | None = None) -> dict:
        r = maintenance.search(MaintenanceSearchRequest(query=query, asset_id=asset_id or self.inc.asset_id, limit=4),
                               self.settings.maintenance_records_path)
        for s in r.items:
            self.sources[s.record_id] = s
        return {"status": r.status, "records": [{"record_id": s.record_id, "unit": s.asset_id or "site-wide", "recorded_at": str(s.recorded_at),
                                                 "text": s.excerpt} for s in r.items]}

    def t_get_recent_readings(self, asset_id: str, n: int = 5) -> dict:
        with self.store.lock:
            rows = self.store.readings.get(asset_id, [])[-max(1, min(n, 20)):]
        return {"readings": [{"observed_at": r.reading.observed_at.isoformat(), **r.reading.values} for r in rows]}


def _summ(name: str, args: dict, out: dict) -> str:
    if "error" in out:
        return f"{name} failed: {out['error']}"
    if name == "search_maintenance":
        ids = [r["record_id"] for r in out["records"]]
        return f"Searched maintenance records for '{args.get('query')}': {', '.join(ids) or 'no evidence'}"
    if name == "estimate_impact":
        return (f"Impact: {_usd(out['cost_per_hour'])}/h, {_usd(out['cost_per_day'])}/day down; "
                f"{_usd(out['cost_if_it_fails'])} if it fails vs {_usd(out['cost_to_fix_now'])} to fix now")
    if name == "get_model_card":
        return f"Read model card for {args.get('detector_id')} ({out['evaluation_status']})"
    if name == "get_recent_readings":
        return f"Read {len(out['readings'])} recent readings"
    return f"Read incident {out.get('incident_id')} ({out.get('risk_level')} risk)"


def _parse(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    if isinstance(d.get("explanation"), str) and isinstance(d.get("recommended_actions"), list):
        return d
    return None


def _usd(x: float) -> str:
    """Whole dollars for big numbers, cents for small ones (a single miner earns a few dollars a day)."""
    return f"${x:,.0f}" if abs(x) >= 100 else f"${x:,.2f}"


def _text(v) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() else None


RETRY_STATUS = {429, 500, 502, 503, 504}
RETRY_DELAYS = (3.0, 8.0, 15.0, 30.0)
# Longest we will wait for a rate-limited slot. Daily quotas ask for hours; then we move on at once.
MAX_RETRY_DELAY = 45.0
_slot_lock = threading.Lock()
# Gemini quotas are per project and per model, so pacing and parking are tracked per (model, key).
_slot_state: dict[tuple[str, str], dict[str, float]] = {}


def _ready_at(slot: tuple[str, str], min_interval: float) -> float:
    st = _slot_state.setdefault(slot, {"last": float("-inf"), "until": 0.0})
    return max(st["last"] + min_interval, st["until"])


def _take_slot(slots: list[tuple[str, str]], min_interval: float) -> tuple[str, str] | None:
    """The first (model, key) in preference order that is free now; otherwise the one free soonest,
    after waiting for it. None when every slot is parked longer than MAX_RETRY_DELAY."""
    with _slot_lock:
        now = time.monotonic()
        slot = next((x for x in slots if _ready_at(x, min_interval) <= now), None)
        if slot is None:
            slot = min(slots, key=lambda x: _ready_at(x, min_interval))
            wait = _ready_at(slot, min_interval) - now
            if wait > MAX_RETRY_DELAY:
                return None
            time.sleep(wait)
        _slot_state[slot]["last"] = time.monotonic()
        return slot


def _park(slot: tuple[str, str], seconds: float) -> None:
    with _slot_lock:
        _slot_state[slot]["until"] = time.monotonic() + seconds


def _retry_delay(r: httpx.Response, default: float) -> float:
    """Use the server's RetryInfo delay on 429 when it gives one (e.g. "21s")."""
    try:
        for d in r.json().get("error", {}).get("details", []):
            if "retryDelay" in d:
                return float(str(d["retryDelay"]).rstrip("s")) + 1.0
    except (ValueError, AttributeError):
        pass
    return default


def _post(client: httpx.Client, settings: Settings, payload: dict) -> httpx.Response:
    """POST to Gemini. Tries the main model on each key, then the fallback models. A rate-limited
    (model, key) is parked for the server's retry delay and the next one is used straight away;
    transient server and network errors are retried with backoff."""
    keys = settings.gemini_keys
    slots = [(m, k) for m in settings.gemini_models for k in keys]
    delays = list(RETRY_DELAYS)
    rate_limits_left = len(RETRY_DELAYS) + len(slots)
    last: httpx.Response | None = None
    while True:
        slot = _take_slot(slots, settings.gemini_min_interval_seconds)
        if slot is None:  # every model and key is out of quota for a long time: caller falls back now
            if last is not None:
                last.raise_for_status()
            raise httpx.HTTPError("all Gemini models and keys are rate limited")
        model, key = slot
        try:
            r = client.post(API.format(model=model), headers={"x-goog-api-key": key}, json=payload)
        except httpx.TransportError as e:  # network blip: retry like a 503
            if not delays:
                raise
            wait = delays.pop(0)
            log.info("Gemini request failed (%s), retrying in %.0f s", type(e).__name__, wait)
            time.sleep(wait)
            continue
        if r.status_code == 429 and rate_limits_left > 0:
            rate_limits_left -= 1
            last = r
            wait = _retry_delay(r, delays[0] if delays else MAX_RETRY_DELAY)
            log.info("Gemini %s key %d rate limited; parking it for %.0f s", model, keys.index(key) + 1, wait)
            _park(slot, wait)
            continue
        if r.status_code in RETRY_STATUS and r.status_code != 429 and delays:
            wait = delays.pop(0)
            log.info("Gemini %s returned %s, retrying in %.0f s", model, r.status_code, wait)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r


def _gather(box: Toolbox) -> dict:
    """Run every tool locally (milliseconds) so Gemini needs only one request."""
    inc = box.inc
    query = " ".join([inc.title] + [e.field.replace("_", " ") for e in inc.evidence])
    return {
        "get_incident": box.call("get_incident", {}),
        "get_recent_readings": box.call("get_recent_readings", {"asset_id": inc.asset_id, "n": 8}),
        "estimate_impact": box.call("estimate_impact", {"asset_id": inc.asset_id}),
        "search_maintenance": box.call("search_maintenance", {"query": query}),
        "get_model_card": box.call("get_model_card", {"detector_id": inc.detector_id}),
    }


def _gemini(box: Toolbox, settings: Settings, context: dict) -> dict | None:
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": "Tool results:\n" + json.dumps(context, default=str)}]}],
        "generation_config": {"temperature": 0.2, "response_mime_type": "application/json"},
    }
    with httpx.Client(timeout=45) as client:
        r = _post(client, settings, body)
    parts = r.json()["candidates"][0]["content"].get("parts", [])
    return _parse("".join(p.get("text", "") for p in parts))


def _fallback(box: Toolbox, context: dict) -> dict:
    """Same tool results, filled into a template (no LLM)."""
    inc = box.inc
    imp, recs = context["estimate_impact"], context["search_maintenance"].get("records", [])
    where = context["get_incident"].get("location", "")
    text = inc.explanation
    if "error" not in imp:
        text += (f" Downtime costs {_usd(imp['cost_per_hour'])} per hour ({_usd(imp['cost_per_day'])} per day)."
                 f" If it fails: about {_usd(imp['cost_if_it_fails'])} (downtime plus unplanned repair);"
                 f" fixing it now: about {_usd(imp['cost_to_fix_now'])}, saving {_usd(imp['savings_if_fixed_now'])}"
                 f" (assumptions; repair about {imp['estimated_repair_hours']} h).")
    text += f" Most similar past record: {recs[0]['record_id']}: {recs[0]['text']}" if recs else " No similar maintenance records were found."
    return {"problem": f"{inc.title} ({where}).", "likely_cause": recs[0]["text"] if recs else None,
            "explanation": text, "recommended_actions": inc.recommended_actions,
            "cited_record_ids": [r["record_id"] for r in recs[:2]]}


def investigate(store: Store, inc: IncidentDetail, settings: Settings) -> IncidentDetail:
    box = Toolbox(store, inc, settings)
    context = _gather(box)
    result, source = None, "rag"
    if settings.gemini_keys:
        try:
            result = _gemini(box, settings, context)
            source = "agent"
            if result is None:
                log.warning("Gemini gave no usable answer for %s; using fallback", inc.incident_id)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            # Never log the request (it carries the API key header); the status or error type is enough.
            reason = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else type(e).__name__
            log.warning("Gemini call failed for %s (%s); using fallback", inc.incident_id, reason)
            result = None
    if result is None:
        result, source = _fallback(box, context), "rag"
    cited = [box.sources[r] for r in result.get("cited_record_ids", []) if r in box.sources]
    with store.lock:
        inc.problem = _text(result.get("problem"))
        inc.likely_cause = _text(result.get("likely_cause"))
        inc.explanation = result["explanation"]
        inc.recommended_actions = [str(a) for a in result["recommended_actions"]][:8]
        inc.maintenance_sources = cited
        inc.explanation_source = source
        inc.agent_steps = box.steps
    return inc

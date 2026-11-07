"""InfraGuard incident agent.

Gemini plans and calls InfraGuard tools (trained-model results, impact, maintenance search, readings),
then writes a fix plan that cites maintenance record IDs. Numbers come only from tool results; the
agent is told never to invent costs or times. Without GEMINI_API_KEY (or if Gemini fails) a
deterministic fallback runs the same tools and fills a template, marked explanation_source="rag".
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

import httpx

from ..core.config import Settings
from ..schemas.incidents import AgentStep, IncidentDetail
from ..schemas.maintenance import MaintenanceSearchRequest
from . import assets as asset_service
from . import impact as impact_service
from . import maintenance
from .model_registry import list_models
from .store import Store

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_TURNS = 8

SYSTEM = """You are InfraGuard, an operations agent for a data center. Investigate the incident with the tools.
Always call get_incident first, then the other tools you need (search_maintenance at least once).
Rules: use only numbers returned by tools; never invent costs, times, or records; cite maintenance records by
record_id; say clearly when evidence is missing; a human must approve any physical work.
Finish with ONLY a JSON object, no markdown:
{"explanation": "<3-5 sentences: what is wrong, why, likely cause from records, money at stake per hour/day, expected repair time and cost>",
 "recommended_actions": ["<step 1>", "<step 2>", "..."],
 "cited_record_ids": ["mr-..."]}"""

TOOLS = [
    {"name": "get_incident", "description": "Incident status, detector, risk level, evidence and latest model/rule output.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_model_card", "description": "How the detector was trained and tested: target, horizon, held-out metrics, limitations.",
     "parameters": {"type": "object", "properties": {"detector_id": {"type": "string"}}, "required": ["detector_id"]}},
    {"name": "estimate_impact", "description": "Downtime cost per hour and per day, repair cost and repair time for the asset (labelled assumptions).",
     "parameters": {"type": "object", "properties": {"asset_id": {"type": "string"}}, "required": ["asset_id"]}},
    {"name": "search_maintenance", "description": "Search past maintenance records for similar problems and fixes.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "asset_id": {"type": "string"}}, "required": ["query"]}},
    {"name": "get_recent_readings", "description": "Latest sensor readings for the asset (most recent last).",
     "parameters": {"type": "object", "properties": {"asset_id": {"type": "string"}, "n": {"type": "integer"}}, "required": ["asset_id"]}},
]


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
        return {"incident_id": i.incident_id, "asset_id": i.asset_id, "asset_name": asset_service.get_asset(i.asset_id).name,
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
        a = impact_service.load_assumptions(self.settings.impact_assumptions_path).get(asset_id)
        return {"error": "no impact assumptions for this asset"} if a is None else impact_service.compute(a).model_dump()

    def t_search_maintenance(self, query: str, asset_id: str | None = None) -> dict:
        r = maintenance.search(MaintenanceSearchRequest(query=query, asset_id=asset_id or self.inc.asset_id, limit=4),
                               self.settings.maintenance_records_path)
        for s in r.items:
            self.sources[s.record_id] = s
        return {"status": r.status, "records": [{"record_id": s.record_id, "recorded_at": str(s.recorded_at),
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
        return (f"Impact: ${out['cost_per_hour']:,.0f}/h, ${out['cost_per_day']:,.0f}/day down; repair "
                f"${out['estimated_repair_cost']:,.0f}, about {out['estimated_repair_hours']} h")
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


def _gemini(box: Toolbox, settings: Settings) -> dict | None:
    contents = [{"role": "user", "parts": [{"text": f"Investigate incident {box.inc.incident_id}."}]}]
    body = {"system_instruction": {"parts": [{"text": SYSTEM}]}, "tools": [{"function_declarations": TOOLS}],
            "generation_config": {"temperature": 0.2}}
    with httpx.Client(timeout=60) as client:
        for _ in range(MAX_TURNS):
            r = client.post(API.format(model=settings.gemini_model), headers={"x-goog-api-key": settings.gemini_api_key},
                            json={**body, "contents": contents})
            r.raise_for_status()
            content = r.json()["candidates"][0]["content"]
            contents.append(content)
            calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
            if not calls:
                return _parse("".join(p.get("text", "") for p in content.get("parts", [])))
            contents.append({"role": "user", "parts": [
                {"functionResponse": {"name": c["name"], "response": box.call(c["name"], c.get("args") or {})}} for c in calls]})
    return None


def _fallback(box: Toolbox) -> dict:
    inc = box.inc
    box.call("get_incident", {})
    box.call("get_model_card", {"detector_id": inc.detector_id})
    imp = box.call("estimate_impact", {"asset_id": inc.asset_id})
    query = " ".join([inc.title] + [e.field.replace("_", " ") for e in inc.evidence])
    found = box.call("search_maintenance", {"query": query})
    recs = found.get("records", [])
    text = inc.explanation
    if "error" not in imp:
        text += (f" Estimated downtime cost is ${imp['cost_per_hour']:,.0f} per hour (${imp['cost_per_day']:,.0f} per day);"
                 f" repair is estimated at ${imp['estimated_repair_cost']:,.0f} and about {imp['estimated_repair_hours']} h (assumptions).")
    text += f" Most similar past record: {recs[0]['record_id']}: {recs[0]['text']}" if recs else " No similar maintenance records were found."
    return {"explanation": text, "recommended_actions": inc.recommended_actions, "cited_record_ids": [r["record_id"] for r in recs[:2]]}


def investigate(store: Store, inc: IncidentDetail, settings: Settings) -> IncidentDetail:
    box = Toolbox(store, inc, settings)
    result, source = None, "rag"
    if settings.gemini_api_key:
        try:
            result = _gemini(box, settings)
            source = "agent"
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            result = None
    if result is None:
        box.steps.clear()
        result, source = _fallback(box), "rag"
    cited = [box.sources[r] for r in result.get("cited_record_ids", []) if r in box.sources]
    with store.lock:
        inc.explanation = result["explanation"]
        inc.recommended_actions = [str(a) for a in result["recommended_actions"]][:8]
        inc.maintenance_sources = cited
        inc.explanation_source = source
        inc.agent_steps = box.steps
    return inc

from datetime import UTC, datetime, timedelta

import httpx

from backend.app.schemas.incidents import IncidentDetail
from backend.app.services import agent

T0 = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)


def open_cooling_incident(client) -> str:
    for i, t in enumerate([33, 34, 35]):
        client.post("/api/v1/predictions", json={"asset_id": "cooling-01", "observed_at": (T0 + timedelta(minutes=i)).isoformat(),
                    "data_origin": "simulated", "detector_id": "cooling-rule-v1", "readings": {"temperature_c": t}})
    return client.get("/api/v1/incidents").json()["items"][0]["incident_id"]


def test_maintenance_search_cites_records_or_says_no_evidence(client):
    hit = client.post("/api/v1/maintenance/search", json={"query": "supply temperature fan belt", "asset_id": "cooling-01"}).json()
    assert hit["status"] == "ok" and hit["items"][0]["record_id"].startswith("mr-")
    assert all(i["asset_id"] in ("cooling-01", None) for i in hit["items"])
    miss = client.post("/api/v1/maintenance/search", json={"query": "quantum flux capacitor"}).json()
    assert miss == {"items": [], "total": 0, "status": "no_evidence"}


def test_fallback_without_key_uses_tools_and_real_numbers(client):
    d = IncidentDetail.model_validate(client.post(f"/api/v1/incidents/{open_cooling_incident(client)}/investigate").json())
    assert d.explanation_source == "rag"
    assert [s.tool for s in d.agent_steps] == ["get_incident", "get_model_card", "estimate_impact", "search_maintenance"]
    assert "$12,000 per hour ($288,000 per day)" in d.explanation
    assert d.maintenance_sources and d.maintenance_sources[0].record_id in d.explanation


def test_gemini_failure_falls_back(client, settings, monkeypatch):
    settings.gemini_api_key = "test"

    def boom(box, s):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(agent, "_gemini", boom)
    d = client.post(f"/api/v1/incidents/{open_cooling_incident(client)}/investigate").json()
    assert d["explanation_source"] == "rag" and d["agent_steps"]


def test_gemini_path_keeps_only_cited_records_the_tools_returned(client, settings, monkeypatch):
    settings.gemini_api_key = "test"

    def fake(box, s):
        box.call("get_incident", {})
        box.call("search_maintenance", {"query": "filter clogged temperature"})
        return {"explanation": "Likely clogged filter.", "recommended_actions": ["Replace filter (human approval)."],
                "cited_record_ids": ["mr-0042", "mr-9999"]}

    monkeypatch.setattr(agent, "_gemini", fake)
    d = client.post(f"/api/v1/incidents/{open_cooling_incident(client)}/investigate").json()
    assert d["explanation_source"] == "agent"
    assert [m["record_id"] for m in d["maintenance_sources"]] == ["mr-0042"]  # invented id dropped
    assert d["recommended_actions"] == ["Replace filter (human approval)."]


def test_parse_rejects_non_json():
    assert agent._parse("no json here") is None
    assert agent._parse('```json\n{"explanation": "x", "recommended_actions": []}\n```')["explanation"] == "x"

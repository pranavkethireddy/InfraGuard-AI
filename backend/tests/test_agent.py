from datetime import UTC, datetime, timedelta

import httpx
import pytest

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
    assert [s.tool for s in d.agent_steps] == ["get_incident", "get_recent_readings", "estimate_impact",
                                               "search_maintenance", "diagnose_readings", "get_model_card",
                                               "search_learned_cases"]
    assert d.likely_cause and "unknown" not in d.likely_cause.lower()
    assert "$12,000 per hour ($288,000 per day)" in d.explanation
    # Business case: $48,000 downtime + $3,500 unplanned repair if it fails, vs $900 planned now.
    assert "$51,500" in d.explanation and "$900" in d.explanation and "$50,600" in d.explanation
    assert d.impact.cost_if_it_fails == 51500 and d.impact.cost_to_fix_now == 900 and d.impact.savings_if_fixed_now == 50600
    assert d.problem and d.problem.startswith("Sustained high temperature on CRAC Unit 1")
    assert d.maintenance_sources and d.maintenance_sources[0].record_id in d.explanation


def test_gemini_failure_falls_back(client, settings, monkeypatch):
    settings.gemini_api_key = "test"

    def boom(box, s, ctx):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(agent, "_gemini", boom)
    d = client.post(f"/api/v1/incidents/{open_cooling_incident(client)}/investigate").json()
    assert d["explanation_source"] == "rag" and d["agent_steps"]


def test_gemini_path_keeps_only_cited_records_the_tools_returned(client, settings, monkeypatch):
    settings.gemini_api_key = "test"

    def fake(box, s, ctx):
        box.call("search_maintenance", {"query": "filter clogged temperature"})
        return {"problem": "CRAC Unit 1 is overheating.", "likely_cause": "Clogged filter (mr-0042).","explanation": "Likely clogged filter.", "recommended_actions": ["Replace filter (human approval)."],
                "cited_record_ids": ["mr-0042", "mr-9999"]}

    monkeypatch.setattr(agent, "_gemini", fake)
    d = client.post(f"/api/v1/incidents/{open_cooling_incident(client)}/investigate").json()
    assert d["explanation_source"] == "agent"
    assert [m["record_id"] for m in d["maintenance_sources"]] == ["mr-0042"]  # invented id dropped
    assert d["recommended_actions"] == ["Replace filter (human approval)."]
    assert d["problem"] == "CRAC Unit 1 is overheating." and d["likely_cause"] == "Clogged filter (mr-0042)."


def test_gemini_investigation_is_one_request_with_all_tool_results(client, settings, monkeypatch):
    settings.gemini_api_key = "test"
    sent = []

    def fake_post(c, s, payload):
        sent.append(payload)
        text = '{"problem": "p", "likely_cause": "c", "explanation": "e", "recommended_actions": ["a"], "cited_record_ids": []}'
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
                              request=httpx.Request("POST", "http://x"))

    monkeypatch.setattr(agent, "_post", fake_post)
    d = client.post(f"/api/v1/incidents/{open_cooling_incident(client)}/investigate").json()
    assert len(sent) == 1 and "tools" not in sent[0]
    prompt = sent[0]["contents"][0]["parts"][0]["text"]
    assert all(t in prompt for t in ("get_incident", "estimate_impact", "search_maintenance", "cost_if_it_fails"))
    assert d["explanation_source"] == "agent" and d["problem"] == "p"


def test_parse_rejects_non_json():
    assert agent._parse("no json here") is None
    assert agent._parse('```json\n{"explanation": "x", "recommended_actions": []}\n```')["explanation"] == "x"


def test_rate_limited_key_switches_to_second_key_without_waiting(settings, monkeypatch):
    settings.gemini_api_key, settings.gemini_api_key_2, settings.gemini_min_interval_seconds = "k1", "k2", 0.0
    monkeypatch.setattr(agent, "_slot_state", {})
    settings.gemini_fallback_models = ""
    seen, slept = [], []
    monkeypatch.setattr(agent.time, "sleep", slept.append)

    def reply(req):
        seen.append(req.headers["x-goog-api-key"])
        if len(seen) == 1:
            return httpx.Response(429, json={"error": {"details": [{"retryDelay": "30s"}]}})
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(reply)) as c:
        assert agent._post(c, settings, {}).json() == {"ok": True}
        assert seen == ["k1", "k2"] and slept == []
        # k1 is still parked, so the next request goes to k2 as well.
        agent._post(c, settings, {})
    assert seen[-1] == "k2"


def test_single_key_waits_for_the_server_retry_delay(settings, monkeypatch):
    settings.gemini_api_key, settings.gemini_api_key_2, settings.gemini_min_interval_seconds = "only", None, 0.0
    monkeypatch.setattr(agent, "_slot_state", {})
    settings.gemini_fallback_models = ""
    replies = [httpx.Response(429, json={"error": {"details": [{"retryDelay": "7s"}]}}),
               httpx.Response(200, json={"ok": True})]
    slept = []
    monkeypatch.setattr(agent.time, "sleep", slept.append)
    with httpx.Client(transport=httpx.MockTransport(lambda req: replies.pop(0))) as c:
        assert agent._post(c, settings, {}).json() == {"ok": True}
    assert len(slept) == 1 and 7.5 < slept[0] <= 8.0


def test_daily_quota_on_every_key_fails_fast(settings, monkeypatch):
    settings.gemini_api_key, settings.gemini_api_key_2, settings.gemini_min_interval_seconds = "k1", "k2", 0.0
    settings.gemini_model, settings.gemini_fallback_models = "main", "lite"
    monkeypatch.setattr(agent, "_slot_state", {})
    slept, calls = [], []
    monkeypatch.setattr(agent.time, "sleep", slept.append)

    def reply(req):
        calls.append((req.url.path.split("/")[-1].split(":")[0], req.headers["x-goog-api-key"]))
        return httpx.Response(429, json={"error": {"details": [{"retryDelay": "29848s"}]}})

    with httpx.Client(transport=httpx.MockTransport(reply)) as c, pytest.raises(httpx.HTTPStatusError):
        agent._post(c, settings, {})
    assert calls == [("main", "k1"), ("main", "k2"), ("lite", "k1"), ("lite", "k2")] and slept == []


def test_main_model_out_of_quota_moves_to_fallback_model(settings, monkeypatch):
    settings.gemini_api_key, settings.gemini_api_key_2, settings.gemini_min_interval_seconds = "k1", None, 0.0
    settings.gemini_model, settings.gemini_fallback_models = "main", "lite"
    monkeypatch.setattr(agent, "_slot_state", {})
    models = []

    def reply(req):
        models.append(req.url.path.split("/")[-1].split(":")[0])
        if models[-1] == "main":
            return httpx.Response(429, json={"error": {"details": [{"retryDelay": "29848s"}]}})
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(reply)) as c:
        assert agent._post(c, settings, {}).json() == {"ok": True}
        agent._post(c, settings, {})  # main stays parked
    assert models == ["main", "lite", "lite"]


def test_diagnosis_names_the_cause_from_the_readings():
    from backend.app.services import diagnosis

    belt = diagnosis.likely_cause("cooling_unit", {"temperature_c": 36.2, "fan_speed_rpm": 790})
    assert "fan belt" in belt and "790" in belt
    assert "filter" in diagnosis.likely_cause("cooling_unit", {"temperature_c": 33.0, "fan_speed_rpm": 1150})
    assert diagnosis.likely_cause("cooling_unit", {"temperature_c": 23.8, "fan_speed_rpm": 1160}) is None
    assert "crashed" in diagnosis.likely_cause("gpu_server", {"online": 0, "gpus_online": 0})
    assert "cooling unit" in diagnosis.likely_cause("gpu_server", {"online": 1, "gpus_online": 8, "gpus_throttled": 5,
                                                                   "inlet_temp_c": 33.1, "ecc_errors": 0, "psu_ok": 2})
    assert diagnosis.is_unknown("The cause is unknown based on current readings.")

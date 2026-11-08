from backend.app.schemas.health import HealthResponse
from backend.app.services.model_registry import FACILITY_RULE_IDS


def test_health_reports_contract_and_honest_dependencies(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = HealthResponse.model_validate(r.json())
    assert body.contract_version == "1"
    assert body.dependencies.models == {"cooling-rule-v1": "available", "industrial-failure-v1": "unavailable", "drive-failure-v1": "unavailable",
                                            "miner-rule-v1": "available", "server-rule-v1": "available",
                                            **{d: "available" for d in FACILITY_RULE_IDS.values()}}
    assert body.dependencies.database == "not_configured"
    assert r.headers["X-Request-ID"].startswith("req-")


def test_industrial_model_available_when_artifact_exists(client, settings, tmp_path):
    artifact = tmp_path / "pipeline.joblib"
    artifact.write_bytes(b"placeholder")
    settings.model_artifact_path = str(artifact)
    r = client.get("/health")
    assert r.json()["dependencies"]["models"]["industrial-failure-v1"] == "available"


def test_serves_the_built_frontend_on_the_same_origin(settings, tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "app.js").write_text("console.log(1)")
    c = TestClient(create_app(settings.model_copy(update={"static_dir": str(tmp_path)})))
    assert c.get("/").text == "<div id=root></div>"
    assert c.get("/operations").text == "<div id=root></div>"  # client-side route
    assert c.get("/app.js").text == "console.log(1)"
    assert c.get("/api/v1/assets").status_code == 200
    assert c.get("/api/v1/nope").status_code == 404
    assert c.get("/../backend/.env").text == "<div id=root></div>"

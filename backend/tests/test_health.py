from backend.app.schemas.health import HealthResponse


def test_health_reports_contract_and_honest_dependencies(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = HealthResponse.model_validate(r.json())
    assert body.contract_version == "1"
    assert body.dependencies.models == {"cooling-rule-v1": "available", "industrial-failure-v1": "unavailable"}
    assert body.dependencies.database == "not_configured"
    assert r.headers["X-Request-ID"].startswith("req-")


def test_industrial_model_available_when_artifact_exists(client, settings, tmp_path):
    artifact = tmp_path / "pipeline.joblib"
    artifact.write_bytes(b"placeholder")
    settings.model_artifact_path = str(artifact)
    r = client.get("/health")
    assert r.json()["dependencies"]["models"]["industrial-failure-v1"] == "available"

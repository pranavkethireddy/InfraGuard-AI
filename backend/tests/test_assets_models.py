import json
from pathlib import Path

import pytest


from backend.app.schemas.assets import AssetDetail, AssetSummary
from backend.app.schemas.common import Page
from backend.app.schemas.models import ModelInfo, ModelMetrics


def test_list_assets(client):
    r = client.get("/api/v1/assets")
    assert r.status_code == 200
    page = Page[AssetSummary].model_validate(r.json())
    ids = [a.asset_id for a in page.items]
    assert page.total == 262 and ids == sorted(ids)
    assert {"cooling-01", "drive-01", "mill-01"} <= set(ids)
    assert all(a.data_origin == "simulated" for a in page.items)


def test_list_assets_pagination(client):
    page = client.get("/api/v1/assets?limit=1&offset=1").json()
    assert page["total"] == 262 and page["limit"] == 1 and page["offset"] == 1
    assert [a["asset_id"] for a in page["items"]] == ["cooling-02"]


def test_asset_detail_includes_labelled_assumptions(client):
    asset = AssetDetail.model_validate(client.get("/api/v1/assets/cooling-01").json())
    assert asset.compatible_detector == "cooling-rule-v1"
    assert "not measured" in asset.impact_assumptions.assumptions_source


def test_models_never_report_unearned_metrics(client):
    page = Page[ModelInfo].model_validate(client.get("/api/v1/models").json())
    by_id = {m.detector_id: m for m in page.items}
    assert by_id["cooling-rule-v1"].score_kind == "heuristic"
    industrial = by_id["industrial-failure-v1"]
    assert industrial.status == "unavailable"
    assert industrial.evaluation_status == "not_evaluated"
    assert industrial.metrics is None
    assert industrial.prediction_horizon_hours is None


REAL_METRICS = Path(__file__).resolve().parents[2] / "ml" / "artifacts" / "metrics" / "industrial-failure-v1.json"


def _industrial(client) -> ModelInfo:
    page = Page[ModelInfo].model_validate(client.get("/api/v1/models").json())
    return {m.detector_id: m for m in page.items}["industrial-failure-v1"]


@pytest.fixture
def artifact(settings, tmp_path):
    p = tmp_path / "pipeline.joblib"
    p.write_bytes(b"placeholder")
    settings.model_artifact_path = str(p)


@pytest.mark.skipif(not REAL_METRICS.is_file(), reason="model not trained")
def test_models_report_training_metrics_unchanged(client, settings, artifact):
    settings.industrial_metrics_path = str(REAL_METRICS)
    raw = json.loads(REAL_METRICS.read_text())
    m = _industrial(client)
    assert m.status == "available" and m.evaluation_status == "evaluated"
    assert m.metrics.model_dump(mode="json") == ModelMetrics.model_validate(raw["contract_metrics"]).model_dump(mode="json")
    assert m.risk_thresholds.model_dump() == raw["risk_thresholds"]
    assert m.metrics.split == "test"


def test_missing_metrics_file_means_not_evaluated(client, artifact):
    m = _industrial(client)
    assert m.status == "available"
    assert m.evaluation_status == "not_evaluated" and m.metrics is None and m.risk_thresholds is None


@pytest.mark.parametrize("content", ["{not json", "[]", '{"contract_metrics": {"split": "train"}, "risk_thresholds": {"medium": 0.1, "high": 0.5}}'])
def test_broken_metrics_file_means_not_evaluated(client, settings, artifact, tmp_path, content):
    bad = tmp_path / "bad.json"
    bad.write_text(content)
    settings.industrial_metrics_path = str(bad)
    m = _industrial(client)
    assert m.evaluation_status == "not_evaluated" and m.metrics is None and m.risk_thresholds is None


@pytest.mark.skipif(not REAL_METRICS.is_file(), reason="model not trained")
def test_metrics_hidden_when_pipeline_missing(client, settings):
    settings.industrial_metrics_path = str(REAL_METRICS)
    m = _industrial(client)
    assert m.status == "unavailable" and m.evaluation_status == "not_evaluated" and m.metrics is None


DRIVE_METRICS = Path(__file__).resolve().parents[2] / "ml" / "artifacts" / "metrics" / "drive-failure-v1.json"


@pytest.mark.skipif(not DRIVE_METRICS.is_file(), reason="drive model not trained")
def test_drive_model_reports_horizon_and_metrics(client, settings, tmp_path):
    p = tmp_path / "drive.joblib"
    p.write_bytes(b"placeholder")
    settings.drive_model_artifact_path = str(p)
    settings.drive_metrics_path = str(DRIVE_METRICS)
    page = Page[ModelInfo].model_validate(client.get("/api/v1/models").json())
    m = {x.detector_id: x for x in page.items}["drive-failure-v1"]
    assert m.prediction_horizon_hours == 720 and m.asset_types == ["storage_drive"]
    assert m.evaluation_status == "evaluated"
    assert m.metrics.pr_auc == json.loads(DRIVE_METRICS.read_text())["contract_metrics"]["pr_auc"]

from backend.app.schemas.assets import AssetDetail, AssetSummary
from backend.app.schemas.common import Page
from backend.app.schemas.models import ModelInfo


def test_list_assets(client):
    r = client.get("/api/v1/assets")
    assert r.status_code == 200
    page = Page[AssetSummary].model_validate(r.json())
    assert [a.asset_id for a in page.items] == ["cooling-01", "mill-01"]
    assert all(a.data_origin == "simulated" for a in page.items)


def test_list_assets_pagination(client):
    page = client.get("/api/v1/assets?limit=1&offset=1").json()
    assert page["total"] == 2 and page["limit"] == 1 and page["offset"] == 1
    assert [a["asset_id"] for a in page["items"]] == ["mill-01"]


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

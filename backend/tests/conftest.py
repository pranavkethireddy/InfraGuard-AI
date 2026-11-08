import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    # No artifact or metrics at these paths, so the AI4I model reports "unavailable" and "not_evaluated".
    return Settings(
        cors_origins="http://localhost:5173",
        model_artifact_path=str(tmp_path / "missing.joblib"),
        industrial_metrics_path=str(tmp_path / "missing.json"),
        drive_model_artifact_path=str(tmp_path / "missing-drive.joblib"),
        drive_metrics_path=str(tmp_path / "missing-drive.json"),
        gemini_api_key=None,  # tests never call Gemini live
        gemini_api_key_2=None,
        vultr_inference_api_key=None,  # nor Vultr
        learned_cases_path=str(tmp_path / "learned_cases.json"),
        auto_dispatch=False,  # tests dispatch explicitly; test_pager covers automatic dispatch
    )


@pytest.fixture
def client(settings) -> TestClient:
    from backend.app.core.config import get_settings

    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app, raise_server_exceptions=False)

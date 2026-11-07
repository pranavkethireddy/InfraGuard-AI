"""Runtime settings, read from environment variables or backend/.env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"
CONTRACT_VERSION = "1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="backend/.env", extra="ignore")

    database_url: str = "sqlite:///./infraguard.db"
    # Comma-separated list of allowed browser origins.
    cors_origins: str = "http://localhost:5173"
    model_artifact_path: str = "ml/artifacts/ai4i/pipeline.joblib"
    # Written by scripts/train_industrial.py; read as-is, never edited by hand.
    industrial_metrics_path: str = "ml/artifacts/metrics/industrial-failure-v1.json"
    drive_model_artifact_path: str = "ml/artifacts/backblaze/pipeline.joblib"
    drive_metrics_path: str = "ml/artifacts/metrics/drive-failure-v1.json"
    simulation_enabled: bool = True
    simulation_tick_seconds: float = 2.0
    impact_assumptions_path: str = "configs/impact_assumptions.json"
    maintenance_records_path: str = "data/maintenance/records.json"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

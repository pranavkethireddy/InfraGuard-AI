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
    # Live fleet demo (services/live.py).
    datacenter_layout_path: str = "configs/datacenter_layout.json"
    mining_layout_path: str = "configs/mining_layout.json"
    # Daily Bitcoin hashprice (CloudMineCrypto open data, CC BY 4.0); prices lost mining revenue.
    hashprice_data_path: str = "data/market/hashprice_daily.csv"
    # Crew, windows, demo clock and thermal limits (services/ops.py, services/whatif.py).
    operations_path: str = "configs/operations.json"
    # Learned repair cases; survives restarts and /fleet/clear. Not committed.
    learned_cases_path: str = "backend/var/learned_cases.json"
    live_tick_seconds: float = 1.0
    # Start the live fleet loop when the server boots (deployed demo); off for local dev and tests.
    live_autostart: bool = False
    # Folder with the built frontend (index.html); when set, the API also serves the app on the same origin.
    static_dir: str | None = None
    live_history_limit: int = 300
    auto_investigate: bool = True
    # Page the closest qualified technician as soon as an incident opens (can be switched at /ops/auto-dispatch).
    auto_dispatch: bool = True
    impact_assumptions_path: str = "configs/impact_assumptions.json"
    maintenance_records_path: str = "data/maintenance/records.json"
    # Vultr Serverless Inference (OpenAI-style chat API). When set, it writes incident explanations and Gemini
    # becomes the backup. Empty vultr_model picks the first chat model the account offers.
    vultr_inference_api_key: str | None = None
    vultr_inference_url: str = "https://api.vultrinference.com/v1"
    vultr_model: str = ""
    gemini_api_key: str | None = None
    # Optional second key: when one key is rate limited, requests move to the other.
    gemini_api_key_2: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    # Tried in order when the main model is rate limited on every key (free-tier quotas are per model).
    gemini_fallback_models: str = "gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    # Minimum gap between Gemini requests, shared by all investigations (free-tier rate limits).
    gemini_min_interval_seconds: float = 4.0

    @property
    def gemini_keys(self) -> list[str]:
        return [k for k in dict.fromkeys([self.gemini_api_key, self.gemini_api_key_2]) if k]

    @property
    def gemini_models(self) -> list[str]:
        extra = [m.strip() for m in self.gemini_fallback_models.split(",") if m.strip()]
        return list(dict.fromkeys([self.gemini_model, *extra]))

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

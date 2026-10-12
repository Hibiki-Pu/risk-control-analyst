"""Application settings.

All secrets are read from environment variables only (never hard-coded, never
committed). Every setting has a safe default so the demo runs with zero keys.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# services/api/app/core/config.py -> services/api/app/core -> services/api
API_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = API_DIR.parents[1]


class Settings(BaseSettings):
    """Runtime settings for the calculation service (prefix ``RCA_``)."""

    model_config = SettingsConfigDict(
        env_prefix="RCA_",
        env_file=(REPO_ROOT / ".env", API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    data_dir: Path = REPO_ROOT / "data" / "synthetic"
    runtime_dir: Path = API_DIR / "runtime"
    synthetic_data: bool = True

    # AI analyst -----------------------------------------------------------
    llm_provider: str = "deterministic"
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_timeout_seconds: float = 30.0
    llm_max_output_tokens: int = 1200
    tool_log_path: Path | None = None

    # Business rules -------------------------------------------------------
    #: Working-capital days used when a scenario keeps DSO/DIO/DPO flat.
    risk_interest_coverage_min: float = 2.0
    risk_dso_max_days: float = 60.0
    risk_cash_runway_min_months: float = 3.0
    risk_net_leverage_max: float = 3.0
    stale_market_data_days: int = 120

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def tool_log_file(self) -> Path:
        return self.tool_log_path or (self.runtime_dir / "tool_calls.jsonl")

    def ensure_runtime_dir(self) -> Path:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        return self.runtime_dir


class FredSettings(BaseSettings):
    """Optional FRED connector settings (prefix ``FRED_``)."""

    model_config = SettingsConfigDict(
        env_prefix="FRED_",
        env_file=(REPO_ROOT / ".env", API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = ""
    base_url: str = "https://api.stlouisfed.org/fred"
    timeout_seconds: float = 8.0
    max_retries: int = 2
    cache_ttl_seconds: int = 3600
    min_request_interval_seconds: float = 0.5

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_fred_settings() -> FredSettings:
    return FredSettings()


class EdgarSettings(BaseSettings):
    """Optional SEC EDGAR connector settings (prefix ``EDGAR_``).

    The connector is **designed but not implemented in v1** (see
    ``docs/market-data-sources.md``). The settings exist so the interface, the
    access policy and the refusal message are explicit rather than implicit.
    """

    model_config = SettingsConfigDict(
        env_prefix="EDGAR_",
        env_file=(REPO_ROOT / ".env", API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = False
    #: SEC requires a descriptive User-Agent with contact details; requests without
    #: one are refused by the SEC fair-access policy.
    user_agent: str = ""
    base_url: str = "https://data.sec.gov"
    archive_url: str = "https://www.sec.gov"
    timeout_seconds: float = 10.0
    max_retries: int = 2
    min_request_interval_seconds: float = 0.2
    cache_ttl_seconds: int = 86400

    @property
    def configured(self) -> bool:
        return bool(self.user_agent.strip())


@lru_cache
def get_edgar_settings() -> EdgarSettings:
    return EdgarSettings()

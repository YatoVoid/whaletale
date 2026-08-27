from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://whaletale:whaletale@localhost:5432/whaletale",
        validation_alias="DATABASE_URL",
    )
    # spec 6.4: entry threshold, also the floor the report uses to sanity-check
    # edge-authored buckets.
    min_dwell_seconds: float = Field(default=3.0, validation_alias="WHALETALE_MIN_DWELL_SECONDS")
    # spec 6.5: trailing window for the "against itself" comparison.
    baseline_weeks: int = Field(default=4, validation_alias="WHALETALE_BASELINE_WEEKS")
    # spec 6.5: standard deviations from baseline before a bucket is flagged.
    anomaly_sigma: float = Field(default=2.0, validation_alias="WHALETALE_ANOMALY_SIGMA")


settings = Settings()

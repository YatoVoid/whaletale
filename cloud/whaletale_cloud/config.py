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
    # spec 9: the internal fleet admin API. Unset disables it.
    admin_token: str = Field(default="", validation_alias="WHALETALE_ADMIN_TOKEN")
    # spec 9: Sentry for exceptions.
    sentry_dsn: str = Field(default="", validation_alias="SENTRY_DSN")
    # spec 8.5 / 12: Stripe billing on camera count.
    stripe_secret_key: str = Field(default="", validation_alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(default="", validation_alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_id: str = Field(default="", validation_alias="STRIPE_PRICE_ID")
    billing_grace_days: int = Field(default=7, validation_alias="WHALETALE_BILLING_GRACE_DAYS")
    billing_export_window_days: int = Field(
        default=30, validation_alias="WHALETALE_BILLING_EXPORT_DAYS"
    )


settings = Settings()

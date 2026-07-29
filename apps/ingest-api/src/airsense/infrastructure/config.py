"""Process configuration. The only place a host, port or threshold literal lives."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "ci", "production"]
TicketSinkName = Literal["memory", "hubspot"]


class Settings(BaseSettings):
    """Environment-sourced settings for the ingest service.

    Connection strings have no defaults: a missing DSN must fail at startup
    rather than silently fall back to a local address in production.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Environment = "local"
    log_level: str = "INFO"
    service_name: str = "ingest-api"
    service_version: str = "0.1.0"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Comma-separated rather than a list: pydantic-settings decodes complex
    # types as JSON, which makes the compose file and .env awkward to read.
    cors_allow_origins: str = ""

    database_dsn: str
    redis_dsn: str

    mqtt_host: str
    mqtt_port: int = 1883
    mqtt_topic_prefix: str = "airsense/telemetry"
    mqtt_client_id: str = "airsense-ingest"

    ticket_sink: TicketSinkName = "memory"
    hubspot_access_token: str | None = None
    # Pipeline and stage identifiers are per-account; there is no sensible
    # default, and a wrong one files tickets into a stage nobody watches.
    hubspot_pipeline: str = "0"
    hubspot_open_stage: str = "1"
    hubspot_closed_stage: str = "4"

    model_dir: Path = Path("models")

    # ─── Domain rule thresholds ───────────────────────────────────────────
    # Defaults live here, not in the domain: the rules take their thresholds as
    # arguments so they can be exercised at values a test chooses. These are the
    # values the running system uses, and every one is overridable by env var.
    #
    # Entry/exit gaps of 0.10 give the deadband. Five sustained samples is five
    # seconds at the simulator's pacing — long enough to reject a spike, short
    # enough to stay inside a reviewer's ten-second window.
    watch_enter: float = 0.50
    watch_exit: float = 0.40
    alert_enter: float = 0.75
    alert_exit: float = 0.65
    sustained_samples: int = 5

    severity_medium_band: float = 0.60
    severity_high_band: float = 0.75
    severity_critical_band: float = 0.90
    # Health index per sample. At ~0.008 a device crosses a full severity band
    # in roughly a minute of replay, which is the point at which "how fast" is
    # worth more than "how bad".
    fast_degradation_per_sample: float = 0.008

    ticket_cooldown_minutes: int = 30
    # Enough to satisfy the longest debounce window and still measure a slope.
    condition_history_samples: int = 20

    @property
    def model_path(self) -> Path:
        return self.model_dir / "compressor_degradation.onnx"

    @property
    def feature_spec_path(self) -> Path:
        return self.model_dir / "feature_spec.json"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def emit_json_logs(self) -> bool:
        return self.environment != "local"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]

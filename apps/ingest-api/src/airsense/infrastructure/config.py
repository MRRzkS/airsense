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

    model_dir: Path = Path("models")

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

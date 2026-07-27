"""Simulator configuration, sourced entirely from the environment."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["local", "ci", "production"] = "local"
    log_level: str = "INFO"
    service_name: str = "device-simulator"
    service_version: str = "0.1.0"

    api_host: str = "0.0.0.0"
    api_port: int = 8001

    mqtt_host: str
    mqtt_port: int = 1883
    mqtt_topic_prefix: str = "airsense/telemetry"
    mqtt_client_id: str = "airsense-simulator"

    publish_interval_seconds: float = 1.0
    fixture_path: Path = Path("data/replay_fd001.parquet")

    @property
    def emit_json_logs(self) -> bool:
        return self.environment != "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

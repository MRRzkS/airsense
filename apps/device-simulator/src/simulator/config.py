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

    # The dashboard calls this service directly for fault injection, so it needs
    # its own CORS allowance rather than borrowing the ingest service's.
    cors_allow_origins: str = ""

    mqtt_host: str
    mqtt_port: int = 1883
    mqtt_topic_prefix: str = "airsense/telemetry"
    mqtt_client_id: str = "airsense-simulator"

    # Five frames a second. The scorer needs a 20-sample window and the rules
    # need 5 sustained samples on top, so at 1 Hz an injected fault would take
    # well over a minute to reach ALERT. Measured worst case across the four
    # demo devices at this rate is 7.6 s, inside the ten-second budget with
    # room for transport and rendering.
    publish_interval_seconds: float = 0.2
    fixture_path: Path = Path("data/replay_fd001.parquet")

    # Life fraction below which a device is considered healthy. Idle devices
    # ping-pong through this prefix so an untouched fleet never self-alerts.
    healthy_ceiling: float = 0.45

    # Where an injected fault enters the trajectory. Later than the healthy
    # ceiling on purpose: entering at the boundary costs 49-56 samples to reach
    # ALERT against 33-38 from here, and the gap is the whole demo budget.
    fault_injection_start: float = 0.60

    # The control surface is public in the demo deployment; without a limit one
    # script can drive the broker and the database as hard as it likes.
    inject_rate_limit: str = "10/minute"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def emit_json_logs(self) -> bool:
        return self.environment != "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()

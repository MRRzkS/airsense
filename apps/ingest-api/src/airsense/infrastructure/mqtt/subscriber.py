"""MQTT ingest loop."""

import asyncio
from dataclasses import dataclass

import aiomqtt
import structlog
from prometheus_client import Counter
from pydantic import ValidationError

from airsense.application.use_cases.ingest_reading import IngestReading
from airsense.domain.telemetry import ImplausibleReadingError
from airsense.infrastructure.wire import TelemetryMessage

# Not labelled by device: label cardinality grows with the fleet, and a
# per-device counter belongs in the time-series database, not in Prometheus.
READINGS_INGESTED = Counter("airsense_readings_ingested_total", "Readings accepted and persisted")
READINGS_REJECTED = Counter("airsense_readings_rejected_total", "Readings dropped", ["reason"])

log = structlog.get_logger("mqtt")


@dataclass(frozen=True, slots=True)
class MqttTelemetrySubscriber:
    host: str
    port: int
    topic_prefix: str
    client_id: str
    ingest: IngestReading
    reconnect_seconds: float = 3.0

    async def run(self) -> None:
        """Consume telemetry until cancelled, reconnecting whenever the broker drops."""
        topic = f"{self.topic_prefix}/+"
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.host, port=self.port, identifier=self.client_id
                ) as client:
                    # QoS 1: losing a frame is acceptable, silently losing every
                    # frame after a reconnect is not. Duplicates are absorbed by
                    # the repository's idempotent upsert.
                    await client.subscribe(topic, qos=1)
                    log.info("mqtt.subscribed", topic=topic)
                    async for message in client.messages:
                        await self._handle(message.payload)
            except aiomqtt.MqttError as exc:
                log.warning("mqtt.disconnected", error=str(exc), retry_in=self.reconnect_seconds)
                await asyncio.sleep(self.reconnect_seconds)

    async def _handle(self, payload: object) -> None:
        if not isinstance(payload, bytes | str):
            READINGS_REJECTED.labels(reason="non_text_payload").inc()
            return
        try:
            reading = TelemetryMessage.model_validate_json(payload).to_domain()
        except (ValidationError, ImplausibleReadingError, ValueError) as exc:
            READINGS_REJECTED.labels(reason=type(exc).__name__).inc()
            log.warning("reading.rejected", error=str(exc))
            return

        await self.ingest(reading)
        READINGS_INGESTED.inc()

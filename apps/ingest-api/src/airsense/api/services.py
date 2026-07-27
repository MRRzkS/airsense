"""Typed container for everything the composition root wires up.

`app.state` is untyped, so routers reach their collaborators through this
instead of poking at attributes the type checker cannot see. Every field is a
port, which is what lets the test suite substitute in-memory doubles.
"""

from dataclasses import dataclass

from airsense.application.ports.health import DependencyHealth
from airsense.application.ports.telemetry import TelemetryStream
from airsense.application.use_cases.ingest_reading import IngestReading
from airsense.application.use_cases.query_fleet import ListFleet, ReadHistory


@dataclass(frozen=True, slots=True)
class Services:
    stream: TelemetryStream
    probe: DependencyHealth
    ingest: IngestReading
    list_fleet: ListFleet
    read_history: ReadHistory

"""HubSpot-backed `TicketSink`.

Written against HubSpot's documented CRM v3 Tickets API and covered by contract
tests that assert request shape and response parsing against a mocked
transport. It has **never been run against a real HubSpot account** — see the
README's Limitations section. The demo defaults to the in-memory sink precisely
so that this being unproven cannot break it.

Two account-specific things must exist before it will work:

* custom ticket properties `airsense_device_id`, `airsense_fault_class` and
  `airsense_severity`
* the pipeline and stage ids configured in `Settings`
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import httpx

from airsense.domain.severity import Severity
from airsense.domain.telemetry import DeviceId
from airsense.domain.ticketing import FAULT_CODE, FaultClass, Ticket, TicketStatus

BASE_URL: Final = "https://api.hubapi.com"
TICKETS: Final = "/crm/v3/objects/tickets"

DEVICE_PROPERTY: Final = "airsense_device_id"
FAULT_PROPERTY: Final = "airsense_fault_class"
SEVERITY_PROPERTY: Final = "airsense_severity"

# HubSpot's stock hs_ticket_priority vocabulary is LOW/MEDIUM/HIGH. CRITICAL has
# no counterpart, so it maps onto HIGH and the exact severity is preserved in a
# custom property rather than silently lost.
PRIORITY: Final[dict[Severity, str]] = {
    Severity.LOW: "LOW",
    Severity.MEDIUM: "MEDIUM",
    Severity.HIGH: "HIGH",
    Severity.CRITICAL: "HIGH",
}

PROPERTIES: Final[list[str]] = [
    "hs_object_id",
    "subject",
    "hs_pipeline_stage",
    "hs_ticket_priority",
    "createdate",
    "hs_lastmodifieddate",
    "closed_date",
    DEVICE_PROPERTY,
    FAULT_PROPERTY,
    SEVERITY_PROPERTY,
]


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class HubSpotTicketSink:
    client: httpx.AsyncClient
    pipeline: str
    open_stage: str
    closed_stage: str

    async def latest_for(self, device_id: DeviceId, fault_class: FaultClass) -> Ticket | None:
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": DEVICE_PROPERTY,
                            "operator": "EQ",
                            "value": device_id.value,
                        },
                        {
                            "propertyName": FAULT_PROPERTY,
                            "operator": "EQ",
                            "value": fault_class.value,
                        },
                    ]
                }
            ],
            "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
            "properties": PROPERTIES,
            "limit": 1,
        }
        response = await self.client.post(f"{TICKETS}/search", json=payload)
        response.raise_for_status()
        results = response.json().get("results", [])
        return self._to_domain(results[0]) if results else None

    async def open(
        self,
        device_id: DeviceId,
        fault_class: FaultClass,
        severity: Severity,
        at: datetime,
    ) -> Ticket:
        code = FAULT_CODE[fault_class]
        response = await self.client.post(
            TICKETS,
            json={
                "properties": {
                    "subject": f"{device_id.value} — {code} compressor degradation",
                    "content": (
                        f"Opened automatically by airsense at {at.isoformat()}. "
                        f"Diagnostic code {FAULT_CODE[fault_class]}, severity {severity.value}."
                    ),
                    "hs_pipeline": self.pipeline,
                    "hs_pipeline_stage": self.open_stage,
                    "hs_ticket_priority": PRIORITY[severity],
                    DEVICE_PROPERTY: device_id.value,
                    FAULT_PROPERTY: fault_class.value,
                    SEVERITY_PROPERTY: severity.value,
                }
            },
        )
        response.raise_for_status()
        return self._to_domain(response.json())

    async def escalate(self, ticket_id: str, severity: Severity, at: datetime) -> Ticket:
        return await self._patch(
            ticket_id,
            {
                "hs_ticket_priority": PRIORITY[severity],
                SEVERITY_PROPERTY: severity.value,
            },
        )

    async def resolve(self, ticket_id: str, at: datetime) -> Ticket:
        return await self._patch(ticket_id, {"hs_pipeline_stage": self.closed_stage})

    async def list_recent(self, *, limit: int) -> list[Ticket]:
        response = await self.client.get(
            TICKETS, params={"limit": limit, "properties": ",".join(PROPERTIES)}
        )
        response.raise_for_status()
        return [self._to_domain(item) for item in response.json().get("results", [])]

    async def _patch(self, ticket_id: str, properties: dict[str, str]) -> Ticket:
        response = await self.client.patch(
            f"{TICKETS}/{ticket_id}", json={"properties": properties}
        )
        response.raise_for_status()
        return self._to_domain(response.json())

    def _to_domain(self, payload: dict[str, Any]) -> Ticket:
        properties: dict[str, Any] = payload.get("properties", {})
        stage = properties.get("hs_pipeline_stage")
        closed = stage == self.closed_stage

        opened_at = _parse_timestamp(properties.get("createdate")) or datetime.now(UTC)
        updated_at = _parse_timestamp(properties.get("hs_lastmodifieddate")) or opened_at
        # HubSpot only populates closed_date once the ticket reaches a closed
        # stage; fall back to the modification time so the cooldown rule always
        # has something to measure from.
        closed_at = (
            (_parse_timestamp(properties.get("closed_date")) or updated_at) if closed else None
        )

        return Ticket(
            ticket_id=str(payload.get("id") or properties.get("hs_object_id")),
            device_id=DeviceId(properties[DEVICE_PROPERTY]),
            fault_class=FaultClass(properties[FAULT_PROPERTY]),
            severity=Severity(properties[SEVERITY_PROPERTY]),
            status=TicketStatus.CLOSED if closed else TicketStatus.OPEN,
            opened_at=opened_at,
            updated_at=updated_at,
            closed_at=closed_at,
        )


def create_client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=httpx.Timeout(10.0),
    )

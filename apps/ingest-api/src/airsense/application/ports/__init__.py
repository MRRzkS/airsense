"""Outbound port declarations.

Each port is a `typing.Protocol` describing what the application needs from the
outside world. `TicketSink` (P3) is the one a reviewer should look at first: it
is why swapping the CRM is a configuration change rather than a code change.
"""

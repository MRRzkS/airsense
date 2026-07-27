"""Minimal structlog setup.

The simulator is a test harness rather than a production service, so it gets a
plain renderer chain instead of the stdlib bridge the ingest service uses.
"""

import logging

import structlog
from structlog.typing import Processor


def configure_logging(*, level: str, json_output: bool) -> None:
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        cache_logger_on_first_use=True,
    )

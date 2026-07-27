"""Container entrypoint."""

import uvicorn

from simulator.api import create_app
from simulator.config import get_settings

__all__ = ["create_app"]


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "simulator.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "local",
        log_config=None,
    )


if __name__ == "__main__":
    run()

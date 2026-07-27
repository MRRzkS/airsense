"""Container entrypoint."""

import uvicorn

from airsense.api.app import create_app
from airsense.infrastructure.config import get_settings

__all__ = ["create_app"]


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "airsense.main:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "local",
        # Uvicorn installs its own handlers otherwise, which bypasses the
        # structlog formatter and splits the log stream in two.
        log_config=None,
    )


if __name__ == "__main__":
    run()

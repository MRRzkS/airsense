"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request

from airsense.api.services import Services
from airsense.infrastructure.config import Settings, get_settings


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


SettingsDep = Annotated[Settings, Depends(get_settings)]
ServicesDep = Annotated[Services, Depends(get_services)]

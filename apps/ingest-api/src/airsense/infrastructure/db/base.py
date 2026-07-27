"""Declarative base. Alembic autogenerate discovers tables through this metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

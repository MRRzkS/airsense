"""add health index to readings

Revision ID: 0002_health_index
Revises: 0001_readings
Create Date: 2026-07-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_health_index"
down_revision: str | None = "0001_readings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable by design: readings taken before a device has filled its first
    # feature window are genuinely unscored, and 0.0 would read as "healthy".
    op.add_column("readings", sa.Column("health_index", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("readings", "health_index")

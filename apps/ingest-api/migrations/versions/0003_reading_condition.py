"""add debounced device condition to readings

Revision ID: 0003_condition
Revises: 0002_health_index
Create Date: 2026-07-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_condition"
down_revision: str | None = "0002_health_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Not null with a default rather than nullable: every reading has a
    # condition, and rows written before this column existed were, by
    # definition, taken while nothing had escalated.
    op.add_column(
        "readings",
        sa.Column("condition", sa.String(8), nullable=False, server_default="NORMAL"),
    )


def downgrade() -> None:
    op.drop_column("readings", "condition")

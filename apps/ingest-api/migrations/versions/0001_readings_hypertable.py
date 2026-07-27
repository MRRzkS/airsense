"""create readings hypertable

Revision ID: 0001_readings
Revises:
Create Date: 2026-07-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_readings"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "readings",
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", sa.String(16), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("compressor_current_a", sa.Float(), nullable=False),
        sa.Column("discharge_pressure_kpa", sa.Float(), nullable=False),
        sa.Column("suction_temperature_c", sa.Float(), nullable=False),
        sa.Column("ambient_temperature_c", sa.Float(), nullable=False),
        sa.Column("vibration_rms_mm_s", sa.Float(), nullable=False),
        # Time first: TimescaleDB requires the partitioning column in every
        # unique constraint, and the composite key is what makes ingest
        # idempotent under MQTT's at-least-once delivery.
        sa.PrimaryKeyConstraint("recorded_at", "device_id"),
    )

    # The older positional signature rather than by_range(): it is deprecated in
    # recent TimescaleDB but accepted across every 2.x release, and the image tag
    # is the thing most likely to move on someone else's machine.
    op.execute("SELECT create_hypertable('readings', 'recorded_at', if_not_exists => TRUE)")

    # Serves the only history query we make: one device, newest first.
    op.create_index(
        "ix_readings_device_recorded_at",
        "readings",
        ["device_id", sa.text("recorded_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_readings_device_recorded_at", table_name="readings")
    op.drop_table("readings")

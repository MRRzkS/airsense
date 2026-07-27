"""SQLAlchemy mapping for the readings hypertable."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from airsense.infrastructure.db.base import Base


class ReadingRow(Base):
    __tablename__ = "readings"

    # TimescaleDB partitions on the time column, and requires it to be part of
    # any unique constraint — hence the composite key rather than a surrogate id.
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(16), primary_key=True)

    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Nullable: a device's first WINDOW_SIZE readings arrive before the model
    # can say anything, and storing 0.0 there would be indistinguishable from
    # a genuinely healthy score.
    health_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    compressor_current_a: Mapped[float] = mapped_column(Float, nullable=False)
    discharge_pressure_kpa: Mapped[float] = mapped_column(Float, nullable=False)
    suction_temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    ambient_temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    vibration_rms_mm_s: Mapped[float] = mapped_column(Float, nullable=False)

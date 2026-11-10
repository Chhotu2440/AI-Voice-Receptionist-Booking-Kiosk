"""Kiosk devices and kiosk sessions (no customer PII is stored on sessions)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import UTCDateTime, UUIDBinary, enum_check

DEVICE_STATUSES = ("PENDING", "ACTIVE", "DISABLED")


class KioskDevice(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "kiosk_devices"
    __table_args__ = (enum_check("status", DEVICE_STATUSES, "status"),)

    name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    # SHA-256 of a 256-bit random secret (high entropy, so a fast hash is appropriate).
    secret_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pairing_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    pairing_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    paired_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    health: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class KioskSession(UUIDPrimaryKey, Base):
    __tablename__ = "kiosk_sessions"
    __table_args__ = (Index("ix_kiosk_sessions_device_started", "device_id", "started_at"),)

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary(), ForeignKey("kiosk_devices.id", ondelete="CASCADE")
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
    final_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    furthest_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mode: Mapped[str] = mapped_column(String(8), default="TOUCH")
    language: Mapped[str] = mapped_column(String(5), default="en")
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUIDBinary(), nullable=True)
    enquiry_id: Mapped[uuid.UUID | None] = mapped_column(UUIDBinary(), nullable=True)

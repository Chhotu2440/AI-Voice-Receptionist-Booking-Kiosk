"""Outbound notifications (WhatsApp via Interakt) and inbound webhook events."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.db.types import UTCDateTime, UUIDBinary, enum_check

NOTIFICATION_STATUSES = ("QUEUED", "SENDING", "SENT", "DELIVERED", "READ", "FAILED", "SKIPPED")


class NotificationLog(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notification_logs"
    __table_args__ = (
        enum_check("status", NOTIFICATION_STATUSES, "status"),
        Index("ix_notification_logs_due", "status", "next_attempt_at"),
    )

    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDBinary(), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(16), default="WHATSAPP")
    provider: Mapped[str] = mapped_column(String(16), default="INTERAKT")
    template: Mapped[str] = mapped_column(String(64))
    to_masked: Mapped[str] = mapped_column(String(20))
    variables: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class WebhookEvent(UUIDPrimaryKey, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_key"),)

    provider: Mapped[str] = mapped_column(String(16))
    event_key: Mapped[str] = mapped_column(String(160))  # provider message id + event type (dedupe)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

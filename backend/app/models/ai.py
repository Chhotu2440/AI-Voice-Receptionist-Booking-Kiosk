"""Per-session voice AI usage and cost (VOICE-06). No transcripts or audio are stored."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, Index, Integer, Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.db.base import Base, UUIDPrimaryKey
from app.db.types import UTCDateTime, UUIDBinary


class AiUsageLog(UUIDPrimaryKey, Base):
    __tablename__ = "ai_usage_logs"
    __table_args__ = (Index("ix_ai_usage_logs_business_date", "business_date"),)

    device_id: Mapped[uuid.UUID] = mapped_column(UUIDBinary())
    kiosk_session_id: Mapped[uuid.UUID | None] = mapped_column(UUIDBinary(), nullable=True)
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))
    business_date: Mapped[date] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ended_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    seconds: Mapped[int] = mapped_column(Integer)
    audio_in_tokens: Mapped[int] = mapped_column(Integer, default=0)
    audio_out_tokens: Mapped[int] = mapped_column(Integer, default=0)
    text_in_tokens: Mapped[int] = mapped_column(Integer, default=0)
    text_cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    text_out_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(SmallInteger, default=0)
    tools_blocked: Mapped[int] = mapped_column(SmallInteger, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 5))
    price_version: Mapped[str] = mapped_column(String(32))
    end_reason: Mapped[str] = mapped_column(String(32), default="")

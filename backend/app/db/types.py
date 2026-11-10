"""Portable column types: UUID as BINARY(16), UTC datetimes as DATETIME(6), money as DECIMAL(12,2)."""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Dialect, LargeBinary, Numeric, String
from sqlalchemy.dialects import mysql
from sqlalchemy.types import TypeDecorator, TypeEngine


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: 48-bit unix ms timestamp + random bits (time-ordered, index friendly)."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version
    value |= ((rand >> 68) & 0xFFF) << 64  # rand_a (12 bits)
    value |= 0b10 << 62  # variant
    value |= rand & ((1 << 62) - 1)  # rand_b (62 bits)
    return uuid.UUID(int=value)


class UUIDBinary(TypeDecorator[uuid.UUID]):
    """UUID stored as BINARY(16) on MySQL (BLOB on SQLite)."""

    impl = LargeBinary(16)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.BINARY(16))
        return dialect.type_descriptor(LargeBinary(16))

    def process_bind_param(self, value: Any, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = uuid.UUID(value)
        return bytes(value.bytes)

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        return uuid.UUID(bytes=bytes(value))


class UTCDateTime(TypeDecorator[datetime]):
    """Stores naive UTC (DATETIME(6) on MySQL); always returns timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("UTCDateTime expects a datetime")
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime; use timezone-aware values")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        assert isinstance(value, datetime)
        return value.replace(tzinfo=UTC)


def Money() -> Numeric[Any]:
    return Numeric(12, 2, asdecimal=True)


def Percent() -> Numeric[Any]:
    return Numeric(5, 2, asdecimal=True)


def enum_column(length: int = 32) -> String:
    return String(length)


def enum_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)

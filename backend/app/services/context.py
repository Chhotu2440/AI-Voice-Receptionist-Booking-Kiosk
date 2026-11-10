"""Who is performing an operation; passed to services for authorization-aware auditing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ActorType = Literal["USER", "SYSTEM", "KIOSK", "AI", "WEBHOOK", "PUBLIC"]


@dataclass(frozen=True)
class Actor:
    type: ActorType
    id: str | None = None
    ip: str | None = None
    request_id: str | None = None

    @classmethod
    def system(cls) -> Actor:
        return cls(type="SYSTEM")

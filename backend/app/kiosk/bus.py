"""In-process fan-out of kiosk state changes, so the screen and the voice agent stay in sync.

Touch intents arrive on /ws/kiosk and voice tool calls on /ws/voice; both go through KioskFlow, which
publishes the new state here. Each connection subscribes for its device and receives changes made by the
other channel. (Single-process today; swap for Redis pub/sub when the voice gateway runs as its own
process - the interface stays the same.)
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from app.kiosk.state import KioskState

Source = Literal["touch", "voice", "system"]


@dataclass(frozen=True)
class StateChange:
    state: KioskState
    source: Source
    intent: str


class KioskBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[StateChange]]] = defaultdict(set)

    def subscribe(self, device_id: str) -> asyncio.Queue[StateChange]:
        q: asyncio.Queue[StateChange] = asyncio.Queue(maxsize=100)
        self._subs[device_id].add(q)
        return q

    def unsubscribe(self, device_id: str, q: asyncio.Queue[StateChange]) -> None:
        self._subs[device_id].discard(q)
        if not self._subs[device_id]:
            self._subs.pop(device_id, None)

    def publish(self, device_id: str, change: StateChange) -> None:
        for q in list(self._subs.get(device_id, ())):
            if q.full():  # a stuck consumer must never block the kiosk
                q.get_nowait()
            q.put_nowait(change)

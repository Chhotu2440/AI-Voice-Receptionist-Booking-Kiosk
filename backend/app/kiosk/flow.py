"""Kiosk conversation flow: validates intents against the state machine (docs/05) and calls the booking
services. Touch and (later) voice submit the same intents, so the screen and the assistant can't diverge,
and neither can skip a mandatory step."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.exceptions import DomainError, ValidationFailed
from app.core.timeutil import today_local, utcnow
from app.kiosk.bus import KioskBus, Source, StateChange
from app.kiosk.state import FLOW, KioskError, KioskState, PackageCard
from app.kiosk.store import KioskStateStore
from app.models.kiosk import KioskSession
from app.repositories import catalogue as catalogue_repo
from app.schemas.booking import BookingCreate, BookingOut, CustomerIn, EnquiryCreate, HoldCreate
from app.schemas.pricing import quote_out
from app.services import (
    availability_service,
    booking_service,
    enquiry_service,
    hold_service,
    notification_service,
    package_service,
    pricing_service,
    schedule_service,
    settings_service,
)
from app.services.context import Actor
from app.services.phone import normalize_indian_mobile

KIOSK = "KIOSK"


class InvalidTransitionError(DomainError):
    status_code, code = 409, "INVALID_STATE_TRANSITION"
    default_message = "That step isn't available right now."


ALLOWED: dict[str, set[str]] = {
    "IDLE": {"start"},
    "GREETING": {"continue"},
    "CUSTOMER_NAME": {"set_name"},
    "CUSTOMER_PHONE": {"set_phone", "confirm_phone"},
    "GUEST_COUNT": {"set_guests"},
    "OCCASION": {"set_occasion"},
    "CUSTOM_EVENT_DETAILS": {"submit_enquiry"},
    "PACKAGE_DISCOVERY": {"select_package"},
    "DATE_SELECTION": {"select_date"},
    "SLOT_SELECTION": {"select_slot", "select_date"},
    "BOOKING_SUMMARY": {"confirm_booking", "set_consent", "extend_hold"},
    "BOOKING_CONFIRMED": {"finish"},
    "SESSION_COMPLETE": {"finish"},
    "STAFF_ASSISTANCE": {"staff_resume"},
    "SESSION_CANCELLED": {"finish"},
}
IN_SESSION = {"back", "edit", "staff_assist", "cancel"}
ALWAYS = {"reset", "set_language"}

EDIT_TARGETS = {
    "name": "CUSTOMER_NAME",
    "phone": "CUSTOMER_PHONE",
    "guests": "GUEST_COUNT",
    "occasion": "OCCASION",
    "package": "PACKAGE_DISCOVERY",
    "date": "DATE_SELECTION",
    "slot": "SLOT_SELECTION",
}
HOLD_RECOVERABLE = {"HOLD_EXPIRED", "HOLD_NOT_ACTIVE", "SLOT_UNAVAILABLE"}
Handler = Callable[[str, KioskState, dict[str, Any]], Awaitable[KioskState]]


def idem_key(*parts: object) -> str:
    """Deterministic idempotency key that fits the 64-char column (UUID-based parts would not)."""
    return "kiosk-" + hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:48]


def allowed_intents(s: KioskState) -> set[str]:
    base = ALLOWED.get(s.state, set()) | ALWAYS
    return base | IN_SESSION if s.state not in ("IDLE", "SESSION_COMPLETE", "BOOKING_CONFIRMED") else base


class KioskFlow:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        settings: Settings,
        store: KioskStateStore,
        bus: KioskBus | None = None,
    ) -> None:
        self.maker = maker
        self.settings = settings
        self.store = store
        self.bus = bus or KioskBus()

    # --- entry points ------------------------------------------------------------------------------

    async def current(self, device_id: str) -> KioskState:
        return await self.store.get(device_id) or KioskState()

    async def connect(self, device_id: str, resume_session_id: str | None) -> KioskState:
        """A (re)connecting screen resumes only the session it was showing; a fresh page load (browser crash,
        reboot) never gets the previous customer's data back - that session is ended and the slot released."""
        s = await self.current(device_id)
        if s.session_id and s.session_id == resume_session_id:
            return s
        if s.session_id:
            await self._end(device_id, s, "DISCONNECTED")
            s = KioskState()
            await self.store.put(device_id, s)
        return s

    async def handle(
        self, device_id: str, name: str, payload: dict[str, Any], source: Source = "touch"
    ) -> KioskState:
        s = await self.current(device_id)
        if name not in allowed_intents(s):
            raise InvalidTransitionError(details={"state": s.state, "intent": name})
        handler: Handler = getattr(self, f"_i_{name}")
        s.error = None
        s.intent_seq += 1
        try:
            s = await handler(device_id, s, payload)
        except ValidationError as exc:
            s.error = KioskError(code="VALIDATION_ERROR", message=_first_message(exc))
        except DomainError as exc:
            s.error = KioskError(code=exc.code, message=exc.message)
        s.version += 1
        s.updated_at = utcnow()
        if s.state in FLOW:
            s.furthest_index = max(s.furthest_index, FLOW.index(s.state))
        await self.store.put(device_id, s)
        self.bus.publish(device_id, StateChange(s, source, name))
        return s

    # --- helpers ----------------------------------------------------------------------------------

    async def _release_hold(self, s: KioskState) -> None:
        if s.hold_id and s.hold_token:
            async with self.maker() as db:
                try:
                    await hold_service.release_hold(db, self.settings, uuid.UUID(s.hold_id), s.hold_token)
                except DomainError:
                    pass
        s.hold_id = s.hold_token = None
        s.hold_expires_at, s.hold_can_extend, s.quote, s.start_time = None, False, None, None

    async def _clear_from(self, s: KioskState, target: str) -> None:
        """Invalidate everything that depends on the step being re-entered (docs/05 dependency table)."""
        idx = FLOW.index(target) if target in FLOW else len(FLOW)
        if idx <= FLOW.index("SLOT_SELECTION"):
            await self._release_hold(s)
        if idx <= FLOW.index("DATE_SELECTION"):
            s.play_date, s.slots = None, []
        if idx <= FLOW.index("PACKAGE_DISCOVERY"):
            s.package_id, s.available_dates = None, []
        if idx <= FLOW.index("OCCASION"):
            s.packages = []

    async def _end(self, device_id: str, s: KioskState, reason: str) -> None:
        await self._release_hold(s)
        if not s.session_id:
            return
        async with self.maker() as db:
            row = await db.get(KioskSession, uuid.UUID(s.session_id))
            if row is not None and row.ended_at is None:
                row.ended_at, row.end_reason, row.final_state = utcnow(), reason, s.state
                row.furthest_state = FLOW[s.furthest_index] if s.furthest_index < len(FLOW) else s.state
                row.language = s.language
                if s.booking:
                    row.booking_id = s.booking.id
                await db.commit()

    async def _load_packages(self, db: AsyncSession, s: KioskState) -> None:
        assert s.guest_count is not None
        today = today_local()
        rows = await package_service.list_public(db, today, s.guest_count)
        cards = []
        for p, preview in rows:
            eligible = p.min_guests <= s.guest_count <= p.max_guests
            cards.append(
                PackageCard(
                    id=str(p.id),
                    code=p.code,
                    name_en=p.name_en,
                    name_hi=p.name_hi or p.name_en,
                    description_en=p.description_en,
                    description_hi=p.description_hi,
                    duration_min=p.duration_min,
                    games_count=p.games_count,
                    formats_count=p.formats_count,
                    features=[{"en": f.text_en, "hi": f.text_hi or f.text_en} for f in p.features],
                    recommended=p.is_recommended,
                    eligible=eligible,
                    min_guests=p.min_guests,
                    max_guests=p.max_guests,
                    price_per_person=str(preview.price_per_person) if preview else None,
                    estimated_total=(
                        str(preview.estimated_total) if preview and preview.estimated_total else None
                    ),
                    day_type=preview.day_type if preview else None,
                )
            )
        s.packages = [c for c in cards if c.price_per_person is not None]

    async def _load_slots(self, db: AsyncSession, s: KioskState) -> None:
        assert s.package_id and s.play_date and s.guest_count
        day = await availability_service.slots_for_day(
            db, uuid.UUID(s.package_id), s.play_date, s.guest_count
        )
        s.slots = day.slots

    # --- intents ----------------------------------------------------------------------------------

    async def _i_start(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        s = KioskState(language=s.language)
        async with self.maker() as db:
            row = KioskSession(
                device_id=uuid.UUID(device_id), started_at=utcnow(), mode="TOUCH", language=s.language
            )
            db.add(row)
            await db.commit()
            s.session_id = str(row.id)
        s.state = "GREETING"
        return s

    async def _i_continue(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        s.state = "CUSTOMER_NAME"
        return s

    async def _i_set_name(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        s.customer_name = CustomerIn(name=str(p.get("name", "")), phone="9000000000").name
        if s.resume_state and s.phone_confirmed:
            s.state, s.resume_state = s.resume_state, None  # type: ignore[assignment]
        else:
            s.state = "CUSTOMER_PHONE"
        return s

    async def _i_set_phone(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        s.phone_e164 = normalize_indian_mobile(str(p.get("phone", "")))
        s.phone_confirmed = False
        return s

    async def _i_confirm_phone(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        if not s.phone_e164:
            raise ValidationFailed("Please enter your mobile number first.")
        s.phone_confirmed = True
        if s.resume_state:
            s.state, s.resume_state = s.resume_state, None  # type: ignore[assignment]
        else:
            s.state = "GUEST_COUNT"
        return s

    async def _i_set_guests(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        count = p.get("count")
        if not isinstance(count, int) or not 1 <= count <= 1000:
            raise ValidationFailed("Please choose how many players (1 or more).")
        s.guest_count = count
        s.state = "OCCASION"
        return s

    async def _i_set_occasion(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        code = str(p.get("code", ""))
        async with self.maker() as db:
            occasion = await catalogue_repo.get_occasion(db, code)
            if occasion is None or not occasion.is_active:
                raise ValidationFailed("Please choose an occasion.")
            details = booking_service.validate_details(occasion, dict(p.get("details") or {}))
            booking = await settings_service.get_booking_settings(db)
            resource = await schedule_service.primary_resource(db)
            s.occasion_code, s.occasion_details = code, details
            assert s.guest_count is not None
            needs_team = s.guest_count > min(booking.large_group_threshold, resource.max_players)
            if occasion.always_enquiry or needs_team:
                s.state = "CUSTOM_EVENT_DETAILS"
                return s
            await self._load_packages(db, s)
        s.state = "PACKAGE_DISCOVERY"
        return s

    async def _i_select_package(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        package_id = str(p.get("package_id", ""))
        card = next((c for c in s.packages if c.id == package_id), None)
        if card is None:
            raise ValidationFailed("Please choose one of the packages shown.")
        if not card.eligible:
            raise ValidationFailed(f"{card.name_en} is for {card.min_guests}-{card.max_guests} players.")
        s.package_id = package_id
        async with self.maker() as db:
            assert s.guest_count is not None
            s.available_dates = await availability_service.dates(
                db, uuid.UUID(package_id), s.guest_count, None, None
            )
        s.state = "DATE_SELECTION"
        return s

    async def _i_select_date(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        try:
            play_date = date.fromisoformat(str(p.get("date", "")))
        except ValueError as exc:
            raise ValidationFailed("Please choose a date.") from exc
        await self._release_hold(s)
        s.play_date = play_date
        async with self.maker() as db:
            await self._load_slots(db, s)
        s.state = "SLOT_SELECTION"
        return s

    async def _i_select_slot(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        start = str(p.get("start_time", ""))
        if not any(slot.start_time == start for slot in s.slots):
            raise ValidationFailed("Please choose one of the times shown.")
        await self._release_hold(s)
        assert s.package_id and s.play_date and s.guest_count
        async with self.maker() as db:
            try:
                _, hold = await hold_service.create_hold(
                    db,
                    self.settings,
                    HoldCreate(
                        package_id=uuid.UUID(s.package_id),
                        date=s.play_date,
                        start_time=start,
                        guest_count=s.guest_count,
                    ),
                    channel=KIOSK,
                    idempotency_key=idem_key(s.session_id, "hold", s.intent_seq),
                )
            except DomainError:
                await self._load_slots(db, s)  # someone else got it: show fresh times
                raise
            breakdown, quote_id, expires = await pricing_service.quote(
                db, self.settings, uuid.UUID(s.package_id), s.play_date, s.guest_count
            )
        s.hold_id, s.hold_token = hold["hold_id"], hold["hold_token"]
        s.hold_expires_at = datetime.fromisoformat(hold["expires_at"])
        s.hold_can_extend, s.start_time = hold["can_extend"], start
        s.quote = quote_out(breakdown, quote_id, expires)
        s.state = "BOOKING_SUMMARY"
        return s

    async def _i_set_consent(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        s.whatsapp_consent = bool(p.get("whatsapp"))
        return s

    async def _i_extend_hold(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        assert s.hold_id and s.hold_token
        async with self.maker() as db:
            st = await hold_service.extend_hold(db, self.settings, uuid.UUID(s.hold_id), s.hold_token)
        s.hold_expires_at, s.hold_can_extend = st.expires_at, st.can_extend
        return s

    async def _i_confirm_booking(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        assert s.hold_id and s.hold_token and s.customer_name and s.phone_e164 and s.occasion_code
        data = BookingCreate(
            hold_id=uuid.UUID(s.hold_id),
            hold_token=s.hold_token,
            customer=CustomerIn(name=s.customer_name, phone=s.phone_e164),
            occasion_code=s.occasion_code,
            occasion_details=s.occasion_details,
            consents={"whatsapp": s.whatsapp_consent},
            quote_id=s.quote.quote_id if s.quote else None,
        )
        async with self.maker() as db:
            try:
                _, body = await booking_service.create_booking(
                    db,
                    self.settings,
                    data,
                    channel=KIOSK,
                    idempotency_key=idem_key(s.session_id, "book", s.hold_id),
                    actor=Actor("KIOSK", device_id),
                )
            except DomainError as exc:
                if exc.code == "PRICE_CHANGED" and s.package_id and s.play_date and s.guest_count:
                    breakdown, quote_id, expires = await pricing_service.quote(
                        db, self.settings, uuid.UUID(s.package_id), s.play_date, s.guest_count
                    )
                    s.quote = quote_out(breakdown, quote_id, expires)
                elif exc.code in HOLD_RECOVERABLE:
                    s.hold_id = s.hold_token = None
                    s.quote, s.hold_expires_at = None, None
                    await self._load_slots(db, s)
                    s.state = "SLOT_SELECTION"
                raise
        notification_service.schedule_send(self.maker, self.settings)
        s.booking = BookingOut.model_validate(body)
        s.hold_id = s.hold_token = None
        s.state = "BOOKING_CONFIRMED"
        async with self.maker() as db:
            row = await db.get(KioskSession, uuid.UUID(s.session_id)) if s.session_id else None
            if row is not None:
                row.booking_id = s.booking.id
                await db.commit()
        return s

    async def _i_submit_enquiry(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        assert s.customer_name and s.phone_e164 and s.occasion_code and s.guest_count
        preferred = p.get("preferred_date")
        details = {**s.occasion_details, **dict(p.get("details") or {})}
        data = EnquiryCreate(
            customer=CustomerIn(name=s.customer_name, phone=s.phone_e164),
            occasion_code=s.occasion_code,
            guest_count=s.guest_count,
            preferred_date=date.fromisoformat(preferred) if preferred else None,
            details=details,
            consents={"whatsapp": bool(p.get("whatsapp"))},
        )
        async with self.maker() as db:
            _, body = await enquiry_service.create(
                db,
                data,
                channel=KIOSK,
                idempotency_key=idem_key(s.session_id, "enquiry"),
                actor=Actor("KIOSK", device_id),
            )
        s.enquiry_reference = body["reference"]
        s.state = "SESSION_COMPLETE"
        return s

    async def _i_finish(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        await self._end(device_id, s, "COMPLETED" if s.state != "SESSION_CANCELLED" else "CANCELLED")
        return KioskState(language="en")

    async def _i_back(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        if s.state == "CUSTOM_EVENT_DETAILS":
            s.state = "OCCASION"
            return s
        if s.state not in FLOW or FLOW.index(s.state) <= 1:
            return s
        target = FLOW[FLOW.index(s.state) - 1]
        await self._clear_from(s, target)
        if target == "PACKAGE_DISCOVERY" and not s.packages:
            async with self.maker() as db:
                await self._load_packages(db, s)
        s.state = target  # type: ignore[assignment]
        return s

    async def _i_edit(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        target = EDIT_TARGETS.get(str(p.get("field", "")))
        if target is None or FLOW.index(target) > s.furthest_index:
            raise ValidationFailed("That detail can't be changed yet.")
        if target in ("CUSTOMER_NAME", "CUSTOMER_PHONE"):
            s.resume_state = s.state if s.state in FLOW and FLOW.index(s.state) > FLOW.index(target) else None
            if target == "CUSTOMER_PHONE":
                s.phone_confirmed = False
        else:
            s.resume_state = None
            await self._clear_from(s, target)
            if target == "PACKAGE_DISCOVERY":
                async with self.maker() as db:
                    await self._load_packages(db, s)
            if target == "SLOT_SELECTION" and s.play_date:
                async with self.maker() as db:
                    await self._load_slots(db, s)
        s.state = target  # type: ignore[assignment]
        return s

    async def _i_staff_assist(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        if s.state != "STAFF_ASSISTANCE":
            s.resume_state = s.state
            s.state = "STAFF_ASSISTANCE"
        return s

    async def _i_staff_resume(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        s.state = s.resume_state or "GREETING"  # type: ignore[assignment]
        s.resume_state = None
        return s

    async def _i_cancel(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        await self._end(device_id, s, "CANCELLED")
        return KioskState(language="en", state="SESSION_CANCELLED")

    async def _i_reset(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        reason = str(p.get("reason", "TIMEOUT"))[:24].upper()
        await self._end(device_id, s, reason)
        return KioskState(language="en")

    async def _i_set_language(self, device_id: str, s: KioskState, p: dict[str, Any]) -> KioskState:
        lang = p.get("language")
        if lang not in ("en", "hi"):
            raise ValidationFailed("Unsupported language.")
        s.language = lang
        return s


def _first_message(exc: ValidationError) -> str:
    err = exc.errors()[0]
    msg = str(err.get("msg", "Invalid value"))
    return msg.removeprefix("Value error, ")

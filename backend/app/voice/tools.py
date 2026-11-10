"""Allowlisted voice tools (docs/10 §3). Each tool maps onto a kiosk intent, so voice gets exactly the same
validation and state machine as touch. There is deliberately NO tool to confirm a booking: the customer
must tap "Confirm booking" on the screen (decision D-07), and no tool exposes prices the backend didn't
compute, other customers' data, or anything outside the current session."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import DomainError
from app.kiosk.flow import KioskFlow, allowed_intents
from app.kiosk.state import KioskState
from app.services import schedule_service
from app.voice.provider import ToolSpec

S = dict[str, Any]


def _obj(props: S, required: list[str] | None = None) -> S:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


TOOLS: list[ToolSpec] = [
    ToolSpec("get_current_step", "Get the booking step on screen and everything collected so far.", _obj({})),
    ToolSpec("get_business_information", "Venue name, address, phone and opening hours.", _obj({})),
    ToolSpec(
        "continue_from_greeting", "Move on from the welcome screen to asking the customer's name.", _obj({})
    ),
    ToolSpec(
        "set_customer_name",
        "Save the customer's name exactly as they said it (letters only).",
        _obj({"name": {"type": "string", "maxLength": 80}}, ["name"]),
    ),
    ToolSpec(
        "set_customer_phone",
        "Save the customer's 10-digit Indian mobile number (digits only, e.g. 9876543210). "
        "Then read it back in groups and ask them to confirm.",
        _obj({"phone_digits": {"type": "string", "pattern": "^[0-9+ ]{10,16}$"}}, ["phone_digits"]),
    ),
    ToolSpec(
        "confirm_customer_phone", "Call only after the customer confirmed the read-back number.", _obj({})
    ),
    ToolSpec(
        "set_guest_count",
        "Number of players (including the customer).",
        _obj({"count": {"type": "integer", "minimum": 1, "maximum": 1000}}, ["count"]),
    ),
    ToolSpec(
        "set_occasion",
        "Why they are visiting.",
        _obj(
            {
                "occasion": {
                    "type": "string",
                    "enum": [
                        "FRIENDS_FAMILY",
                        "BIRTHDAY",
                        "CORPORATE",
                        "SCHOOL_COLLEGE",
                        "PRIVATE_PARTY",
                        "OTHER",
                    ],
                },
                "birthday_person_name": {"type": "string", "maxLength": 80},
                "birthday_person_age": {"type": "integer", "minimum": 0, "maximum": 120},
            },
            ["occasion"],
        ),
    ),
    ToolSpec(
        "select_package",
        "Choose a package by its code, only from get_current_step's package list.",
        _obj({"package_code": {"type": "string"}}, ["package_code"]),
    ),
    ToolSpec(
        "select_date",
        "Choose the play date (YYYY-MM-DD, Asia/Kolkata). Returns the available start times.",
        _obj({"date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}}, ["date"]),
    ),
    ToolSpec(
        "select_start_time",
        "Reserve one of the offered start times (HH:MM). The screen then shows the summary with the total.",
        _obj({"start_time": {"type": "string", "pattern": "^\\d{2}:\\d{2}$"}}, ["start_time"]),
    ),
    ToolSpec(
        "set_whatsapp_consent",
        "Record whether the customer agreed to receive the confirmation on WhatsApp.",
        _obj({"consent": {"type": "boolean"}}, ["consent"]),
    ),
    ToolSpec(
        "submit_event_enquiry",
        "Send a custom event / large group enquiry to the team (only on the event details step).",
        _obj(
            {
                "preferred_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                "requirements": {"type": "string", "maxLength": 200},
            }
        ),
    ),
    ToolSpec(
        "change_detail",
        "Go back to change something already given.",
        _obj(
            {
                "field": {
                    "type": "string",
                    "enum": ["name", "phone", "guests", "occasion", "package", "date", "slot"],
                }
            },
            ["field"],
        ),
    ),
    ToolSpec("go_back", "Go back one step.", _obj({})),
    ToolSpec(
        "set_screen_language",
        "Switch the screen text.",
        _obj({"language": {"type": "string", "enum": ["en", "hi"]}}, ["language"]),
    ),
    ToolSpec("request_staff_assistance", "Call a team member to the kiosk.", _obj({})),
    ToolSpec("cancel_session", "The customer wants to stop; clears everything.", _obj({})),
]
TOOL_NAMES = {t.name for t in TOOLS}


def summarize(s: KioskState) -> S:
    """What the assistant may know and say: only backend-provided facts, phone masked."""
    pub = s.public()
    out: S = {
        "step": s.state,
        "allowed_actions": sorted(allowed_intents(s)),
        "customer_name": s.customer_name,
        "phone": pub.get("phone_display"),
        "phone_confirmed": s.phone_confirmed,
        "guest_count": s.guest_count,
        "occasion": s.occasion_code,
        "language_on_screen": s.language,
    }
    if s.packages:
        out["packages"] = [
            {
                "code": p.code,
                "name": p.name_en,
                "duration_min": p.duration_min,
                "games": p.games_count,
                "formats": p.formats_count,
                "features": [f["en"] for f in p.features],
                "price_per_person_today_inr": p.price_per_person,
                "estimated_total_today_inr": p.estimated_total,
                "available_for_group": p.eligible,
                "recommended": p.recommended,
            }
            for p in s.packages
        ]
    if s.package_id:
        chosen = next((p for p in s.packages if p.id == s.package_id), None)
        out["selected_package"] = chosen.code if chosen else None
    if s.available_dates:
        out["dates"] = [
            {"date": d.date.isoformat(), "status": d.status, "slots": d.slots_available}
            for d in s.available_dates
        ]
    if s.play_date:
        out["selected_date"] = s.play_date.isoformat()
    if s.state == "SLOT_SELECTION":
        out["available_start_times"] = [f"{x.start_time}-{x.end_time}" for x in s.slots]
    if s.quote:
        out["summary"] = {
            "start_time": s.start_time,
            "price_per_person_inr": str(s.quote.price_per_person),
            "total_inr": str(s.quote.total),
            "gst_included": s.quote.tax.included,
            "payment": "pay at reception",
            "next": "Ask the customer to check the screen and tap 'Confirm booking'. You can't confirm it.",
        }
    if s.booking:
        out["booking"] = {"reference": s.booking.reference, "status": s.booking.status}
    if s.enquiry_reference:
        out["enquiry_reference"] = s.enquiry_reference
    if s.error:
        out["last_error"] = s.error.message
    return out


class ToolExecutor:
    def __init__(self, flow: KioskFlow, maker: async_sessionmaker[AsyncSession], device_id: str) -> None:
        self.flow = flow
        self.maker = maker
        self.device_id = device_id

    async def _intent(self, name: str, payload: S | None = None) -> S:
        try:
            s = await self.flow.handle(self.device_id, name, payload or {}, source="voice")
        except DomainError as exc:
            current = await self.flow.current(self.device_id)
            return {"ok": False, "error": exc.message, "state": summarize(current)}
        if s.error:
            return {"ok": False, "error": s.error.message, "state": summarize(s)}
        return {"ok": True, "state": summarize(s)}

    async def execute(self, name: str, args: S) -> S:
        if name not in TOOL_NAMES:  # allowlist: anything else is refused, whatever the model asks
            return {"ok": False, "error": f"Unknown tool {name!r}."}
        try:
            return await self._dispatch(name, args)
        except (KeyError, TypeError, ValueError):
            return {
                "ok": False,
                "error": "Invalid arguments.",
                "state": summarize(await self.flow.current(self.device_id)),
            }

    async def _dispatch(self, name: str, a: S) -> S:
        if name == "get_current_step":
            return {"ok": True, "state": summarize(await self.flow.current(self.device_id))}
        if name == "get_business_information":
            async with self.maker() as db:
                loc = await schedule_service.primary_location(db)
                hours = await schedule_service.get_hours(db)
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            return {
                "ok": True,
                "name": loc.name,
                "address": f"{loc.address}, {loc.city} {loc.postal_code}",
                "phone": loc.phone,
                "hours": {
                    days[h.weekday]: (
                        "closed" if h.is_closed else f"{h.open_time:%H:%M}-{h.close_time:%H:%M}"
                    )
                    for h in hours
                },
            }
        if name == "continue_from_greeting":
            return await self._intent("continue")
        if name == "set_customer_name":
            return await self._intent("set_name", {"name": str(a["name"])})
        if name == "set_customer_phone":
            return await self._intent("set_phone", {"phone": str(a["phone_digits"])})
        if name == "confirm_customer_phone":
            return await self._intent("confirm_phone")
        if name == "set_guest_count":
            return await self._intent("set_guests", {"count": int(a["count"])})
        if name == "set_occasion":
            details: S = {}
            if a.get("birthday_person_name"):
                details["birthday_person_name"] = str(a["birthday_person_name"])
            if a.get("birthday_person_age") is not None:
                details["birthday_person_age"] = int(a["birthday_person_age"])
            return await self._intent("set_occasion", {"code": str(a["occasion"]), "details": details})
        if name == "select_package":
            s = await self.flow.current(self.device_id)
            code = str(a["package_code"]).strip().upper()
            card = next((p for p in s.packages if p.code == code), None)
            if card is None:
                return {"ok": False, "error": "That package isn't offered right now.", "state": summarize(s)}
            return await self._intent("select_package", {"package_id": card.id})
        if name == "select_date":
            return await self._intent("select_date", {"date": str(a["date"])})
        if name == "select_start_time":
            return await self._intent("select_slot", {"start_time": str(a["start_time"])})
        if name == "set_whatsapp_consent":
            return await self._intent("set_consent", {"whatsapp": bool(a["consent"])})
        if name == "submit_event_enquiry":
            payload: S = {"details": {}}
            if a.get("preferred_date"):
                payload["preferred_date"] = str(a["preferred_date"])
            if a.get("requirements"):
                payload["details"] = {"special_requirements": str(a["requirements"])[:200]}
            return await self._intent("submit_enquiry", payload)
        if name == "change_detail":
            return await self._intent("edit", {"field": str(a["field"])})
        if name == "go_back":
            return await self._intent("back")
        if name == "set_screen_language":
            return await self._intent("set_language", {"language": str(a["language"])})
        if name == "request_staff_assistance":
            return await self._intent("staff_assist")
        if name == "cancel_session":
            return await self._intent("cancel")
        raise ValueError(
            name
        )  # pragma: no cover - TOOL_NAMES and the dispatch table are kept in sync by tests

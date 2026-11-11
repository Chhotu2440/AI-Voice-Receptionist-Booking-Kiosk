"""Admin customers (DPDP access / correction / erasure) and the audit log viewer."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models.booking import Booking, Customer
from app.models.notification import NotificationLog
from tests.api.test_notifications import book, settings  # noqa: F401  (fixture reuse)

API = "/api/v1/admin"


async def _customer_id(client: AsyncClient, headers: dict[str, str], q: str) -> str:
    r = await client.get(f"{API}/customers", params={"q": q}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    return str(r.json()["items"][0]["id"])


async def test_search_detail_correct_and_export(
    client: AsyncClient,
    owner_headers: dict[str, str],
    maker: async_sessionmaker[AsyncSession],
    settings: Settings,  # noqa: F811
) -> None:
    await book(maker, settings)
    by_name = await _customer_id(client, owner_headers, "riya")
    by_phone = await _customer_id(client, owner_headers, "98765 43210")
    by_tail = await _customer_id(client, owner_headers, "3210")
    assert by_name == by_phone == by_tail

    d = (await client.get(f"{API}/customers/{by_name}", headers=owner_headers)).json()
    assert d["name"] == "Riya Sharma" and d["phone"] == "+919876543210" and d["bookings"] == 1
    assert d["consents"] == {"WHATSAPP_TRANSACTIONAL": True} and d["consent_log"][0]["notice_version"]
    assert d["bookings_list"][0]["status"] == "CONFIRMED" and int(d["total_spent"].split(".")[0]) > 0

    bad = await client.patch(f"{API}/customers/{by_name}", headers=owner_headers, json={"name": "R1ya"})
    assert bad.status_code == 422
    fixed = await client.patch(
        f"{API}/customers/{by_name}",
        headers=owner_headers,
        json={"name": "Riya  Sharma-Kapoor", "email": "riya@example.com", "preferred_language": "hi"},
    )
    assert fixed.status_code == 200 and fixed.json()["name"] == "Riya Sharma-Kapoor"

    ex = await client.get(f"{API}/customers/{by_name}/export", headers=owner_headers)
    assert ex.status_code == 200 and "attachment" in ex.headers["content-disposition"]
    assert ex.headers["cache-control"] == "no-store"
    body = ex.json()
    assert body["customer"]["email"] == "riya@example.com" and len(body["bookings"]) == 1
    assert body["messages"][0]["template"] == "booking_confirmation"

    audit = (
        await client.get(f"{API}/audit", params={"entity_type": "customer"}, headers=owner_headers)
    ).json()
    actions = [a["action"] for a in audit["items"]]
    assert actions == ["customer.export", "customer.correct"]
    assert audit["items"][1]["after"] == {"fields": ["name", "email", "preferred_language"]}  # no PII
    assert audit["items"][0]["actor_name"]


async def test_anonymize_keeps_finance_and_erases_identity(
    client: AsyncClient,
    owner_headers: dict[str, str],
    maker: async_sessionmaker[AsyncSession],
    settings: Settings,  # noqa: F811
) -> None:
    booked = await book(maker, settings)
    cid = await _customer_id(client, owner_headers, "Riya")
    async with maker() as s:
        b = await s.get(Booking, uuid.UUID(booked["id"]))
        assert b is not None
        b.notes = "Birthday of Riya's son Aarav"
        await s.commit()

    req = {"reason": "Customer asked us to delete their data", "confirm": "ANONYMIZE"}
    blocked = await client.post(f"{API}/customers/{cid}/anonymize", headers=owner_headers, json=req)
    assert blocked.status_code == 409 and blocked.json()["error"]["details"]["upcoming_bookings"] == 1
    no_confirm = await client.post(
        f"{API}/customers/{cid}/anonymize", headers=owner_headers, json={"reason": "x" * 5}
    )
    assert no_confirm.status_code == 422

    await client.post(
        f"{API}/bookings/{booked['id']}/cancel", headers=owner_headers, json={"reason": "customer request"}
    )
    r = await client.post(f"{API}/customers/{cid}/anonymize", headers=owner_headers, json=req)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Anonymized customer" and r.json()["phone"] == "" and r.json()["anonymized_at"]
    again = await client.post(f"{API}/customers/{cid}/anonymize", headers=owner_headers, json=req)
    assert again.status_code == 409

    async with maker() as s:
        c = (await s.execute(select(Customer))).scalar_one()
        assert c.phone_e164.startswith("+000") and "Riya" not in c.name and c.email is None
        b = (await s.execute(select(Booking))).scalar_one()
        assert b.notes == "" and b.pricing.total > 0  # financial record kept
        n = (await s.execute(select(NotificationLog))).scalar_one()
        assert n.variables == [] and n.to_masked == "—"

    # The same person can book again later; they become a fresh customer record.
    await book(maker, settings, start="20:00")
    assert (await client.get(f"{API}/customers", headers=owner_headers)).json()["total"] == 2
    audit = (await client.get(f"{API}/audit", params={"action": "customer."}, headers=owner_headers)).json()
    assert audit["items"][0]["action"] == "customer.anonymize"
    assert "Riya" not in str(audit["items"][0])


async def test_roles(client: AsyncClient, make_user, login, maker, settings) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    await book(maker, settings)
    staff = await login(*(await make_user("STAFF")))
    listing = await client.get(f"{API}/customers", headers=staff)
    assert listing.status_code == 200  # front desk can look customers up
    cid = listing.json()["items"][0]["id"]
    assert (await client.get(f"{API}/customers/{cid}/export", headers=staff)).status_code == 403
    assert (
        await client.post(
            f"{API}/customers/{cid}/anonymize", headers=staff, json={"reason": "abc", "confirm": "ANONYMIZE"}
        )
    ).status_code == 403
    assert (await client.get(f"{API}/audit", headers=staff)).status_code == 403

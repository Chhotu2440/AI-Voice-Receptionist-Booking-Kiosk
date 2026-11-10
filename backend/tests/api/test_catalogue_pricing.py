"""Catalogue, pricing and settings API tests."""

from __future__ import annotations

from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.timeutil import today_local
from app.models.audit import AuditLog


def next_weekday(weekday: int, start: date | None = None) -> date:
    d = (start or today_local()) + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


async def packages_by_code(client: AsyncClient) -> dict[str, dict]:  # type: ignore[type-arg]
    return {p["code"]: p for p in (await client.get("/api/v1/packages")).json()}


async def test_public_packages_seeded_from_website(client: AsyncClient) -> None:
    pkgs = await packages_by_code(client)
    assert list(pkgs) == ["BEGINNER", "INTERMEDIATE", "EXPERT"]
    assert pkgs["EXPERT"]["duration_min"] == 60
    assert pkgs["INTERMEDIATE"]["is_recommended"] is True
    assert pkgs["BEGINNER"]["pricing"] is None  # no date given -> no price claims


async def test_packages_with_date_and_guests_include_prices(client: AsyncClient) -> None:
    friday = next_weekday(4)
    r = await client.get("/api/v1/packages", params={"date": friday.isoformat(), "guests": 4})
    assert r.status_code == 200
    by_code = {p["code"]: p["pricing"] for p in r.json()}
    assert by_code["EXPERT"]["day_type"] == "WEEKEND"
    assert by_code["EXPERT"]["price_per_person"] == "650.00"
    assert by_code["EXPERT"]["estimated_total"] == "2600.00"
    assert by_code["BEGINNER"]["estimated_total"] == "1600.00"


async def test_packages_ineligible_guest_count_flagged(client: AsyncClient) -> None:
    r = await client.get("/api/v1/packages", params={"date": next_weekday(0).isoformat(), "guests": 40})
    for p in r.json():
        assert p["pricing"]["eligible"] is False
        assert p["pricing"]["estimated_total"] is None


async def test_prc001_calculate_friday_weekend_price(client: AsyncClient) -> None:
    pkgs = await packages_by_code(client)
    r = await client.post(
        "/api/v1/pricing/calculate",
        json={"package_id": pkgs["EXPERT"]["id"], "date": next_weekday(4).isoformat(), "guest_count": 4},
    )
    assert r.status_code == 200, r.text
    q = r.json()
    assert (q["day_type"], q["price_per_person"], q["subtotal"], q["total"]) == (
        "WEEKEND",
        "650.00",
        "2600.00",
        "2600.00",
    )
    assert q["tax"] == {"rate": "18.00", "amount": "396.61", "included": True}
    assert q["quote_id"] and q["quote_expires_at"]


async def test_calculate_validation_errors(client: AsyncClient) -> None:
    pkgs = await packages_by_code(client)
    pid = pkgs["EXPERT"]["id"]
    past = today_local() - timedelta(days=1)
    r = await client.post(
        "/api/v1/pricing/calculate", json={"package_id": pid, "date": past.isoformat(), "guest_count": 2}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "OUTSIDE_BOOKING_WINDOW"

    far = today_local() + timedelta(days=31)
    r = await client.post(
        "/api/v1/pricing/calculate", json={"package_id": pid, "date": far.isoformat(), "guest_count": 2}
    )
    assert r.json()["error"]["code"] == "OUTSIDE_BOOKING_WINDOW"

    r = await client.post(
        "/api/v1/pricing/calculate",
        json={"package_id": pid, "date": today_local().isoformat(), "guest_count": 21},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "GUEST_COUNT_INVALID"

    r = await client.post(
        "/api/v1/pricing/calculate",
        json={"package_id": pid, "date": today_local().isoformat(), "guest_count": 0},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"

    r = await client.post(
        "/api/v1/pricing/calculate",
        json={
            "package_id": "00000000-0000-0000-0000-000000000000",
            "date": today_local().isoformat(),
            "guest_count": 2,
        },
    )
    assert r.status_code == 404

    r = await client.post(
        "/api/v1/pricing/calculate",
        json={"package_id": pid, "date": today_local().isoformat(), "guest_count": 2, "total": "1.00"},
    )
    assert r.status_code == 422  # unknown fields (e.g. client-supplied prices) are rejected


async def test_admin_price_change_takes_effect_and_is_audited(
    client: AsyncClient, owner_headers: dict[str, str], maker: async_sessionmaker[AsyncSession]
) -> None:
    pkgs = await packages_by_code(client)
    pid = pkgs["BEGINNER"]["id"]
    rules = (
        await client.get("/api/v1/admin/pricing-rules", headers=owner_headers, params={"package_id": pid})
    ).json()["items"]
    weekday_rule = next(r for r in rules if r["day_type"] == "WEEKDAY")
    r = await client.patch(
        f"/api/v1/admin/pricing-rules/{weekday_rule['id']}",
        headers=owner_headers,
        json={"price_per_person": "320.00"},
    )
    assert r.status_code == 200, r.text
    q = (
        await client.post(
            "/api/v1/pricing/calculate",
            json={"package_id": pid, "date": next_weekday(0).isoformat(), "guest_count": 2},
        )
    ).json()
    assert q["total"] == "640.00"
    async with maker() as s:
        log = (await s.execute(select(AuditLog).where(AuditLog.action == "pricing_rule.update"))).scalar_one()
    assert log.before["price_per_person"] == "300.00" and log.after["price_per_person"] == "320.00"
    assert log.actor_type == "USER"


async def test_date_override_rule_and_preview_beyond_window(
    client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    pkgs = await packages_by_code(client)
    pid = pkgs["EXPERT"]["id"]
    far = today_local() + timedelta(days=120)
    r = await client.post(
        "/api/v1/admin/pricing-rules",
        headers=owner_headers,
        json={
            "package_id": pid,
            "rule_type": "DATE_OVERRIDE",
            "name": "Festival",
            "date_from": far.isoformat(),
            "price_per_person": "700.00",
        },
    )
    assert r.status_code == 201, r.text
    preview = await client.post(
        "/api/v1/admin/pricing/preview",
        headers=owner_headers,
        json={"package_id": pid, "date": far.isoformat(), "guest_count": 2},
    )
    assert preview.status_code == 200 and preview.json()["price_per_person"] == "700.00"
    assert preview.json()["quote_id"] is None


async def test_rule_shape_validation(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    bad_payloads = [
        {"rule_type": "BASE_DAYTYPE", "price_per_person": "100.00"},  # missing day_type
        {"rule_type": "PROMO", "price_per_person": "100.00"},  # promo needs discount_pct
        {
            "rule_type": "DATE_RANGE",
            "date_from": "2027-01-10",
            "date_to": "2027-01-01",
            "price_per_person": "1",
        },
        {"rule_type": "GROUP_DISCOUNT", "discount_pct": "150"},
        {"rule_type": "BASE_DAYTYPE", "day_type": "WEEKDAY", "price_per_person": "100", "promo_code": "ABC"},
        {"rule_type": "PROMO", "discount_pct": "10", "valid_from": "2027-01-01T00:00:00"},  # naive datetime
    ]
    for payload in bad_payloads:
        r = await client.post("/api/v1/admin/pricing-rules", headers=owner_headers, json=payload)
        assert r.status_code == 422, payload


async def test_update_rule_rejects_invalid_merged_shape(
    client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    rules = (await client.get("/api/v1/admin/pricing-rules", headers=owner_headers)).json()["items"]
    r = await client.patch(
        f"/api/v1/admin/pricing-rules/{rules[0]['id']}", headers=owner_headers, json={"discount_pct": "10"}
    )
    assert r.status_code == 422


async def test_promo_code_and_deactivation(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    pkgs = await packages_by_code(client)
    pid = pkgs["EXPERT"]["id"]
    r = await client.post(
        "/api/v1/admin/pricing-rules",
        headers=owner_headers,
        json={"rule_type": "PROMO", "name": "Launch", "promo_code": "launch10", "discount_pct": "10"},
    )
    assert r.status_code == 201 and r.json()["promo_code"] == "LAUNCH10"
    body = {
        "package_id": pid,
        "date": next_weekday(0).isoformat(),
        "guest_count": 2,
        "promo_code": "Launch10",
    }
    assert (await client.post("/api/v1/pricing/calculate", json=body)).json()["total"] == "1080.00"
    assert (
        await client.delete(f"/api/v1/admin/pricing-rules/{r.json()['id']}", headers=owner_headers)
    ).status_code == 204
    assert (await client.post("/api/v1/pricing/calculate", json=body)).json()["total"] == "1200.00"


async def test_pricing_settings_weekend_days_and_exclusive_tax(
    client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    r = await client.put(
        "/api/v1/admin/settings/pricing",
        headers=owner_headers,
        json={
            "weekend_days": ["SAT", "SUN"],
            "tax_rate": "18.00",
            "prices_include_tax": False,
            "extra_charges": [
                {"code": "SOCKS", "label": "Grip socks", "mode": "PER_PERSON", "amount": "50.00"}
            ],
        },
    )
    assert r.status_code == 200, r.text
    pkgs = await packages_by_code(client)
    q = (
        await client.post(
            "/api/v1/pricing/calculate",
            json={"package_id": pkgs["EXPERT"]["id"], "date": next_weekday(4).isoformat(), "guest_count": 2},
        )
    ).json()
    assert q["day_type"] == "WEEKDAY"  # Friday no longer weekend
    # (600*2 + 50*2) = 1300; +18% = 234 -> 1534
    assert (q["charges_total"], q["tax"]["amount"], q["total"]) == ("100.00", "234.00", "1534.00")

    bad = await client.put(
        "/api/v1/admin/settings/pricing", headers=owner_headers, json={"weekend_days": ["FUNDAY"]}
    )
    assert bad.status_code == 422
    unknown = await client.put("/api/v1/admin/settings/nonsense", headers=owner_headers, json={})
    assert unknown.status_code == 404


async def test_booking_window_setting(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    r = await client.put("/api/v1/admin/settings/booking", headers=owner_headers, json={"max_days_ahead": 60})
    assert r.status_code == 200
    pkgs = await packages_by_code(client)
    r = await client.post(
        "/api/v1/pricing/calculate",
        json={
            "package_id": pkgs["EXPERT"]["id"],
            "date": (today_local() + timedelta(days=45)).isoformat(),
            "guest_count": 2,
        },
    )
    assert r.status_code == 200


async def test_package_crud_and_soft_delete(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    r = await client.post(
        "/api/v1/admin/packages",
        headers=owner_headers,
        json={
            "code": "BDAY_SPECIAL",
            "name_en": "Birthday Special",
            "duration_min": 90,
            "min_guests": 8,
            "max_guests": 16,
            "features": [{"text_en": "Party area for 30 minutes"}],
            "is_active": False,
        },
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert "BDAY_SPECIAL" not in await packages_by_code(client)  # inactive: hidden publicly

    r = await client.patch(
        f"/api/v1/admin/packages/{pid}",
        headers=owner_headers,
        json={"is_active": True, "features": [{"text_en": "A"}, {"text_en": "B"}]},
    )
    assert r.status_code == 200 and [f["text_en"] for f in r.json()["features"]] == ["A", "B"]
    assert "BDAY_SPECIAL" in await packages_by_code(client)

    # Active package without price rules: listed, but never with an invented price.
    r = await client.get("/api/v1/packages", params={"date": next_weekday(0).isoformat(), "guests": 10})
    bday = next(p for p in r.json() if p["code"] == "BDAY_SPECIAL")
    assert bday["pricing"] is None
    q = await client.post(
        "/api/v1/pricing/calculate",
        json={"package_id": pid, "date": next_weekday(0).isoformat(), "guest_count": 10},
    )
    assert q.status_code == 422 and q.json()["error"]["code"] == "PRICING_NOT_CONFIGURED"

    bad = await client.patch(f"/api/v1/admin/packages/{pid}", headers=owner_headers, json={"min_guests": 20})
    assert bad.status_code == 422
    dup = await client.post(
        "/api/v1/admin/packages",
        headers=owner_headers,
        json={"code": "BDAY_SPECIAL", "name_en": "X", "duration_min": 30, "max_guests": 5},
    )
    assert dup.status_code == 409

    assert (await client.delete(f"/api/v1/admin/packages/{pid}", headers=owner_headers)).status_code == 204
    assert (await client.get(f"/api/v1/packages/{pid}")).status_code == 404
    assert (await client.get(f"/api/v1/admin/packages/{pid}", headers=owner_headers)).status_code == 404


async def test_occasions_public_and_admin_update(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    occ = (await client.get("/api/v1/occasions")).json()
    assert [o["code"] for o in occ] == [
        "FRIENDS_FAMILY",
        "BIRTHDAY",
        "CORPORATE",
        "SCHOOL_COLLEGE",
        "PRIVATE_PARTY",
        "OTHER",
    ]
    assert {o["code"] for o in occ if o["always_enquiry"]} == {"CORPORATE", "SCHOOL_COLLEGE"}
    r = await client.patch("/api/v1/admin/occasions/OTHER", headers=owner_headers, json={"is_active": False})
    assert r.status_code == 200
    assert "OTHER" not in [o["code"] for o in (await client.get("/api/v1/occasions")).json()]


async def test_calculate_rejects_unknown_occasion(client: AsyncClient) -> None:
    pkgs = await packages_by_code(client)
    body = {"package_id": pkgs["EXPERT"]["id"], "date": today_local().isoformat(), "guest_count": 2}
    assert (
        await client.post("/api/v1/pricing/calculate", json={**body, "occasion_code": "BIRTHDAY"})
    ).status_code == 200
    r = await client.post("/api/v1/pricing/calculate", json={**body, "occasion_code": "WEDDING"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"

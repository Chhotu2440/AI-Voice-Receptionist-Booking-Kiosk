"""Schedule configuration, business info, health and error-envelope tests."""

from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient

from app.core.timeutil import today_local


async def test_business_info_public(client: AsyncClient) -> None:
    r = await client.get("/api/v1/business-info")
    assert r.status_code == 200
    info = r.json()
    assert info["name"] == "Play Laser Tag" and info["postal_code"] == "110016"
    assert len(info["hours"]) == 7
    assert "gstin" not in info


async def test_put_hours_validation_and_update(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    days = [{"weekday": d, "open_time": "12:00", "close_time": "23:00"} for d in range(7)]
    days[0] = {"weekday": 0, "open_time": "12:00", "close_time": "12:00", "is_closed": True}
    r = await client.put("/api/v1/admin/schedule/hours", headers=owner_headers, json={"days": days})
    assert r.status_code == 200, r.text
    assert r.json()[0]["is_closed"] is True and r.json()[1]["open_time"] == "12:00:00"

    six_days = await client.put(
        "/api/v1/admin/schedule/hours", headers=owner_headers, json={"days": days[:6]}
    )
    assert six_days.status_code == 422
    inverted = [*days[:6], {"weekday": 6, "open_time": "23:00", "close_time": "11:00"}]
    assert (
        await client.put("/api/v1/admin/schedule/hours", headers=owner_headers, json={"days": inverted})
    ).status_code == 422


async def test_schedule_exceptions_crud(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    holiday = (today_local() + timedelta(days=10)).isoformat()
    r = await client.post(
        "/api/v1/admin/schedule/exceptions",
        headers=owner_headers,
        json={"type": "HOLIDAY", "date": holiday, "reason": "Holi"},
    )
    assert r.status_code == 201, r.text
    exc_id = r.json()["id"]
    assert r.json()["date"] == holiday

    block = await client.post(
        "/api/v1/admin/schedule/exceptions",
        headers=owner_headers,
        json={"type": "MANUAL_BLOCK", "date": holiday},
    )
    assert block.status_code == 422  # needs a time range

    listed = (await client.get("/api/v1/admin/schedule/exceptions", headers=owner_headers)).json()
    assert [e["id"] for e in listed] == [exc_id]
    assert (
        await client.delete(f"/api/v1/admin/schedule/exceptions/{exc_id}", headers=owner_headers)
    ).status_code == 204
    assert (await client.get("/api/v1/admin/schedule/exceptions", headers=owner_headers)).json() == []


async def test_resources(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    resources = (await client.get("/api/v1/admin/resources", headers=owner_headers)).json()
    assert len(resources) == 1 and resources[0]["capacity_mode"] == "EXCLUSIVE"
    r = await client.patch(
        f"/api/v1/admin/resources/{resources[0]['id']}",
        headers=owner_headers,
        json={"max_players": 20, "buffer_min": 15},
    )
    assert r.status_code == 200 and r.json()["max_players"] == 20
    bad = await client.patch(
        f"/api/v1/admin/resources/{resources[0]['id']}",
        headers=owner_headers,
        json={"capacity_mode": "WHATEVER"},
    )
    assert bad.status_code == 422


async def test_business_info_update_validates_gstin(
    client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    bad = await client.patch("/api/v1/admin/business-info", headers=owner_headers, json={"gstin": "123"})
    assert bad.status_code == 422
    ok = await client.patch(
        "/api/v1/admin/business-info", headers=owner_headers, json={"maps_url": "https://maps.example/plt"}
    )
    assert ok.status_code == 200 and ok.json()["maps_url"] == "https://maps.example/plt"


async def test_health_and_ready(client: AsyncClient) -> None:
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    r = await client.get("/readyz")
    assert r.status_code == 200 and r.json()["database"] == "ok"


async def test_error_envelope_and_request_id(client: AsyncClient) -> None:
    r = await client.get("/api/v1/packages/not-a-uuid", headers={"X-Request-ID": "abc12345-test"})
    assert r.status_code == 422
    assert r.headers["x-request-id"] == "abc12345-test"
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR" and err["request_id"] == "abc12345-test"
    assert r.headers["x-content-type-options"] == "nosniff"

    r = await client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


async def test_public_rate_limit(client: AsyncClient) -> None:
    codes = [(await client.get("/api/v1/occasions")).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429

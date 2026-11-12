"""Game formats (what is played in each package): admin-managed, linked to packages, shown on the kiosk and
given to the voice assistant."""

from __future__ import annotations

from httpx import AsyncClient

from app.kiosk.state import KioskState, PackageCard
from app.voice.tools import summarize

API = "/api/v1/admin"


async def _package_id(client: AsyncClient, code: str) -> str:
    return next(p["id"] for p in (await client.get("/api/v1/packages")).json() if p["code"] == code)


async def test_seeded_games_and_admin_crud(client: AsyncClient, owner_headers: dict[str, str]) -> None:
    games = (await client.get(f"{API}/game-formats", headers=owner_headers)).json()
    assert [g["code"] for g in games] == [
        "TEAM_MATCH",
        "SHOOTING",
        "FRIENDLY_FIRE",  # named on the website
        "RESPAWN_CHALLENGE",
        "LIMITED_LIVES",
        "LAST_MAN_STANDING",
        "DEATHMATCH",  # per-package challenges from the owner
    ]
    assert all(g["description_en"] == "" for g in games)  # rules are the owner's to write, never invented

    created = await client.post(
        f"{API}/game-formats",
        headers=owner_headers,
        json={
            "code": "CAPTURE_FLAG",
            "name_en": "Capture the Flag",
            "description_en": "Grab the other team's flag and bring it home.",
            "round_minutes": 10,
        },
    )
    assert created.status_code == 201, created.text
    dup = await client.post(
        f"{API}/game-formats", headers=owner_headers, json={"code": "CAPTURE_FLAG", "name_en": "x"}
    )
    assert dup.status_code == 409

    team = next(g for g in games if g["code"] == "TEAM_MATCH")
    upd = await client.patch(
        f"{API}/game-formats/{team['id']}",
        headers=owner_headers,
        json={"description_en": "Two teams, most points wins.", "description_hi": "दो टीमें, ज़्यादा अंक जीतते हैं।"},
    )
    assert upd.status_code == 200 and upd.json()["description_en"].startswith("Two teams")


async def test_package_games_order_rounds_and_validation(
    client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    pid = await _package_id(client, "INTERMEDIATE")
    r = await client.patch(
        f"{API}/packages/{pid}",
        headers=owner_headers,
        json={"games_count": 4, "game_codes": ["SHOOTING", "TEAM_MATCH"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [g["code"] for g in body["games"]] == ["SHOOTING", "TEAM_MATCH"]  # owner's order kept
    assert body["formats_count"] == 2 and body["games_count"] == 4

    public = next(p for p in (await client.get("/api/v1/packages")).json() if p["code"] == "INTERMEDIATE")
    assert [g["name_en"] for g in public["games"]] == ["Shooting", "Team Match"]

    bad = await client.patch(f"{API}/packages/{pid}", headers=owner_headers, json={"game_codes": ["NOPE"]})
    assert bad.status_code == 422 and "NOPE" in bad.json()["error"]["message"]
    twice = await client.patch(
        f"{API}/packages/{pid}", headers=owner_headers, json={"game_codes": ["SHOOTING", "SHOOTING"]}
    )
    assert twice.status_code == 422

    # Switching a game off hides it from packages (kiosk and assistant) without unlinking it.
    games = (await client.get(f"{API}/game-formats", headers=owner_headers)).json()
    shooting = next(g for g in games if g["code"] == "SHOOTING")
    await client.patch(
        f"{API}/game-formats/{shooting['id']}", headers=owner_headers, json={"is_active": False}
    )
    public = next(p for p in (await client.get("/api/v1/packages")).json() if p["code"] == "INTERMEDIATE")
    assert [g["code"] for g in public["games"]] == ["TEAM_MATCH"]

    cleared = await client.patch(f"{API}/packages/{pid}", headers=owner_headers, json={"game_codes": []})
    assert cleared.json()["games"] == [] and cleared.json()["formats_count"] is None


async def test_staff_cannot_edit_games(client: AsyncClient, make_user, login) -> None:  # type: ignore[no-untyped-def]
    staff = await login(*(await make_user("STAFF")))
    assert (await client.get(f"{API}/game-formats", headers=staff)).status_code == 403


def test_assistant_gets_rounds_and_game_modes_but_nothing_invented() -> None:
    card = PackageCard(
        id="p1",
        code="BEGINNER",
        name_en="Beginner",
        name_hi="बिगिनर",
        description_en="",
        description_hi="",
        duration_min=30,
        games_count=2,
        formats_count=2,
        features=[{"en": "Briefing included", "hi": ""}],
        games=[
            {"en": "Team Match", "hi": "टीम मैच", "about_en": "Two teams, most points wins.", "about_hi": ""},
            {"en": "Shooting", "hi": "शूटिंग", "about_en": "", "about_hi": ""},
        ],
        recommended=False,
        eligible=True,
        min_guests=1,
        max_guests=20,
        price_per_person="300",
        estimated_total="1200",
        day_type="WEEKDAY",
    )
    out = summarize(KioskState(state="PACKAGE_DISCOVERY", packages=[card]))
    pkg = out["packages"][0]
    assert pkg["rounds_of_play"] == 2
    assert pkg["game_modes"] == [
        {"name": "Team Match", "how_it_works": "Two teams, most points wins."},
        {"name": "Shooting"},  # no description: the assistant must not make one up
    ]


async def test_seeded_packages_match_owner_content(client: AsyncClient) -> None:
    pkgs = {p["code"]: p for p in (await client.get("/api/v1/packages")).json()}
    beginner, inter, adv = pkgs["BEGINNER"], pkgs["INTERMEDIATE"], pkgs["EXPERT"]
    assert beginner["duration_min"] == 20 and beginner["games_count"] == 2 and beginner["games"] == []
    assert [f["text_en"] for f in beginner["features"]] == [
        "2 solo matches",
        "Unlimited lives & bullets",
        "No additional challenges",
    ]
    assert inter["duration_min"] == 45
    assert [g["code"] for g in inter["games"]] == ["RESPAWN_CHALLENGE", "LIMITED_LIVES", "LAST_MAN_STANDING"]
    assert adv["name_en"] == "Advanced" and adv["duration_min"] == 60
    assert [g["code"] for g in adv["games"]] == ["LIMITED_LIVES", "LAST_MAN_STANDING", "DEATHMATCH"]

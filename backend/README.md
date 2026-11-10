# Backend: Play Laser Tag booking engine & admin API

FastAPI · Pydantic v2 · SQLAlchemy 2 (async, asyncmy) · Alembic · MySQL 8.4 · Redis 7. Architecture: [docs/06](../docs/06-system-architecture.md); decisions: [PROJECT_DECISIONS.md](../PROJECT_DECISIONS.md).

## Layout
```
app/
  core/          config, logging, errors, middleware, security, rate limiting, IST time helpers
  db/            engine/session, declarative base, portable column types (UUID BINARY(16), UTC DATETIME(6))
  models/        ORM: identity (users/roles/permissions/refresh tokens), catalogue, schedule, audit/settings
  schemas/       Pydantic request/response models
  repositories/  queries only
  services/      business rules; pricing_engine.py is the pure pricing core
  api/           deps (auth, RBAC, rate limits) + v1 endpoints (auth, public, admin) + health
  seed.py, cli.py
migrations/      Alembic (async env)
tests/           unit / api / integration
```

## Run locally (no Docker)
```bash
py -3.12 -m venv .venv            # 3.12+; 3.13 also works
.venv/Scripts/pip install -e ".[dev]"   # Linux/macOS: .venv/bin/...
```
SQLite is fine for development and the default test run. Production uses MySQL.
```bash
export DATABASE_URL="sqlite+aiosqlite:///./dev.db" APP_ENV=dev REFRESH_COOKIE_SECURE=false
alembic upgrade head
python -m app.cli seed --with-catalogue
python -m app.cli create-owner --email you@example.com --name "You"
uvicorn app.main:create_app --factory --reload
```
OpenAPI docs: http://localhost:8000/api/v1/docs (disabled in prod).

## Run with Docker Compose (MySQL + Redis)
From the repository root:
```bash
cp backend/.env.example backend/.env    # edit secrets
docker compose up -d --build
docker compose run --rm migrate
docker compose run --rm api python -m app.cli seed --with-catalogue
docker compose run --rm api python -m app.cli create-owner --email you@example.com --name "You"
```

## Quality gates
```bash
ruff check app tests migrations && ruff format --check app tests migrations
mypy app                       # strict
pytest -q                      # SQLite
TEST_DATABASE_URL=mysql+asyncmy://root:root@127.0.0.1:3306/plt_test pytest -q   # MySQL
```
CI (`.github/workflows/backend.yml`) runs all of the above against MySQL 8.4 and Redis. It also runs `alembic upgrade/check/downgrade` on MySQL, Bandit, pip-audit and a Trivy image scan.

## Conventions
- Business logic lives in services, never in route handlers. Services own transactions and write audit entries in the same transaction.
- Money is `Decimal`, rounded half-up to paise. Prices come only from `pricing_service` and the pure engine.
- Instants are stored in UTC. Business dates use Asia/Kolkata (`core/timeutil.py`). Never use the server's local date.
- Every schema change ships as an Alembic migration. `tests/integration/test_migrations.py` fails if models and migrations drift apart.
- Seed data: venue details and package prices are copied from playlasertag.in (2026-11-10). **Opening hours (11:00–22:00), max 16 players, 30-minute slots and a 10-minute buffer are placeholders** until business decision D-02 is confirmed.

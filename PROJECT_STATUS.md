# Project Status

**Updated:** 2026-11-10 · **Phase:** 2, Backend foundation (Sprint 1) · **Overall:** 🟢 On track, with one environment gap (no MySQL or Docker available locally yet)

## Sprint 1 PM report
**Goal:** a running backend foundation (auth/RBAC, catalogue, pricing engine, schedule configuration), with tests and CI. **Result:** code complete and green on SQLite. MySQL verification is pending a CI run.

### Completed
- **Decisions:** ADR-003…011 and 013 approved (2026-11-10) → [PROJECT_DECISIONS.md](PROJECT_DECISIONS.md)
- **PLAT-01 Tooling:** `backend/pyproject.toml` with ruff, mypy (strict) and pytest. All clean.
- **PLAT-04 Core infra:** typed settings with prod guards, JSON logs with request ids, error envelope, security headers, health (`/healthz`) and readiness (`/readyz`: DB, Redis, migration head), graceful shutdown, IST time helpers.
- **CORE-01 Auth & RBAC:** Argon2id, 15-minute JWT, rotating refresh cookie with reuse detection (revokes the family), account lockout, login rate limit, 4 roles and 15 permissions, staff user management, audit log.
- **CORE-02 Catalogue:** packages (CRUD, soft delete, features), occasions, business info. Seeded from the website.
- **CORE-03 Pricing engine:** pure and deterministic. Weekday/weekend (configurable days; Fri–Sun by default, as on the website), date overrides, date ranges, promo codes, group discounts (best or stacked), extra charges, inclusive or exclusive GST, signed quotes. Admin price preview.
- **CORE-04 Schedule config:** business hours, holidays/special hours/blackouts/manual blocks, resources (EXCLUSIVE or SHARED_SEATS capacity mode).
- Alembic migration `0001`, verified to match the models exactly, with downgrade and upgrade. MySQL DDL was reviewed by offline render.
- Docker image, docker-compose (api, MySQL 8.4, Redis 7, migrate), GitHub Actions workflow (lint, types, SQLite and MySQL tests, migration drift check, Bandit, pip-audit, Trivy).

### Test results (local, Python 3.13, SQLite)
| Suite | Result |
|---|---|
| Unit: pricing engine | 39 passed |
| API: auth/RBAC/security, catalogue/pricing, schedule/platform | 37 passed |
| Integration: migrations ↔ models | 1 passed |
| ruff / ruff format / mypy --strict | clean |
| Smoke: real startup (alembic upgrade → seed → uvicorn → `/readyz`, `/packages`) | OK |

### Not yet verified
- **MySQL 8.4 run of the suite** and the **Docker Compose stack**. Neither Docker nor MySQL is installed on this machine. The CI workflow covers both, but the folder is not a git repo with a GitHub remote yet.
- TOTP 2FA (moved to CORE-05, P1).

### Blocked / waiting on business
- DISC-03/04: DaySchedule plan and API key (needed before Sprint 2 ends)
- D-01/D-02: slot exclusivity, max players, hours, interval, buffer. **Needed before BOOK-01 (slot generator).** Placeholders are in the seed.

## Current architecture
FastAPI `api` process (modular monolith) → MySQL 8 (authoritative) + Redis (rate limits now; holds and queues next). The voice gateway, worker and nginx are added in their sprints.

## Key risks
R-01 Hinglish accuracy (20) · R-02 unknown capacity rules (16): now the critical path for Sprint 2 · R-03 migration double calendar (15).

## Next milestone
**Sprint 2: Booking engine.** Slot grid generator, availability, holds, atomic and idempotent booking, concurrency suite on MySQL. **Prerequisites:** answers to D-01/D-02, plus Docker Desktop (or a MySQL 8 instance) on the dev machine, or a GitHub repo for CI.

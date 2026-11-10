# Project Status

**Updated:** 2026-11-10 · **Phase:** 3, Booking engine (Sprint 2 complete) · **Overall:** 🟢 On track. CI fully green (run #11)

## Sprint 2 PM report: booking engine
**Goal:** authoritative availability, slot holds and atomic bookings with no oversell, proven on MySQL. **Result:** done. All tests, including the concurrency suite, pass on MySQL 8.4 in CI.

### Business decisions received (2026-11-10)
- **D-01:** each game slot is **exclusive to one group**.
- **D-02:** **max 20 players**, open **11:00–22:00 daily**, starts **every 30 min**, **10-min changeover buffer**. Minimum group size stays 1 (assumption).

### Completed
- **BOOK-01/02 Slot engine and availability.** A pure engine builds the day from hours and exceptions (holidays, blackouts, special hours, manual blocks) and applies the grid, buffer and same-day cut-off. Endpoints: `POST /availability/slots`, `GET /availability/dates`.
- **BOOK-03 Holds.**
  - Locking: per-cell row locks taken in start order, plus a `held + booked ≤ capacity` CHECK constraint.
  - Lifetime: 5-min TTL, one extension, release.
  - Expiry: an ARQ worker sweeps expired holds every 15 s, and expired holds are also swept lazily.
  - Safety: capability token per hold, idempotency key.
- **BOOK-04 Bookings.**
  - Commit: atomic hold → booking, idempotent replays.
  - Re-checks before confirming: price (PRICE_CHANGED), schedule, hold expiry.
  - Records: immutable pricing snapshot and line items, customer upsert by normalized phone, WhatsApp consent log, status history.
  - Customer self-view through a booking token.
- **BOOK-05 Concurrency suite (MySQL):**
  - 30-way race on one slot: exactly 1 wins.
  - Overlapping packages racing for the same cells.
  - 8 concurrent requests with the same idempotency key: 1 booking.
  - Booking racing hold expiry.
  - 60-request randomized swarm checking counter invariants on every cell.
- **BOOK-06 Admin.** Cancel (frees capacity), reschedule (same package and group size; re-priced, old and new totals in history), completed / no-show, search by date, status, phone or reference, staff holds and bookings.
- **BOOK-07 Event enquiries.** Public create, admin pipeline (NEW → CONTACTED → QUOTED → WON / LOST). Corporate and school occasions, and groups over 20, are routed here.
- **CI hardening.** Test failures and Trivy findings now publish as annotations, readable on the run page without signing in. The image patches Debian security updates at build time.

### Bugs found and fixed through MySQL CI
1. **MySQL deadlocks on cell creation.** Concurrent first-time inserts of capacity cells deadlocked on MySQL. Cell creation now inserts only missing rows and retries.
2. **Expired ORM objects after a retry.** A retry after a deadlock touched ORM objects that the rollback had expired. Retried units now use plain values or reload inside the transaction.
3. **CHECK violations on MySQL.** MySQL reports them as error 3819, not as an integrity error. The capacity CHECK now maps to SLOT_UNAVAILABLE instead of a 500.
4. **Base-image CVEs.** Trivy found HIGH zlib CVEs in the Debian 13 base image. Fixed by applying OS security updates during the image build.

### Test results
| Suite | Local (SQLite) | CI (MySQL 8.4) |
|---|---|---|
| Unit: pricing engine, slot engine, phone/tokens | ✅ | ✅ |
| API: auth/RBAC, catalogue/pricing, schedule, booking flow | ✅ | ✅ |
| Concurrency (6 tests, MySQL-only) | skipped by design | ✅ |
| Migrations: drift check, downgrade/upgrade | ✅ | ✅ |
| Lint, mypy strict, Bandit, pip-audit | ✅ | ✅ |
| Docker image build + Trivy scan (CRITICAL/HIGH) | — | ✅ |

Total: 137 tests (131 local + 6 MySQL-only).

### Not yet verified / known gaps
- The Docker Compose stack (api, worker, MySQL, Redis) has not been run on a real host. The images build in CI.
- No kiosk device auth yet: public booking calls use channel `WEB` until KIOSK-01.
- Notifications are not sent yet (INT-01). Consent is recorded, ready for WhatsApp.
- TOTP 2FA (CORE-05).

### Waiting on business
- DISC-03/04: DaySchedule account details and API key, needed for the migration and import (INT-03).
- D-03 payment model (default: pay at venue), D-05 GST inclusive?, D-06 WhatsApp Business number and Meta account.

## Next milestone
**Sprint 3: Kiosk frontend (touch).** React + Vite + Tailwind kiosk shell, device pairing and auth, WebSocket state machine, screens 1–9, then the full touch booking end to end (Playwright).

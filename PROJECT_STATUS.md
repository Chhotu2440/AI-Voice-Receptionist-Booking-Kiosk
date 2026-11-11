# Project Status

**Updated:** 2026-11-11 · **Phase:** 5, Sprint 5 (admin dashboard) in progress; Sprint 4 done except the human voice test · **Overall:** 🟢

## Sprint 5 PM report: admin milestone 2: customers, staff accounts, audit log
- **Customers** (`/admin/customers`, new API): search by name, full phone or last digits; profile with bookings, enquiries, spend, current consents and consent history.
  - **Correction** (name, email, language). Phone stays fixed because it is the customer's identity.
  - **Export** (right of access): JSON download, audited.
  - **Erase personal data** (right to erasure): blocked while a booking is upcoming; needs a reason and typing ANONYMIZE. Removes name, phone, email, booking notes, occasion details, enquiry details and WhatsApp message contents. Keeps bookings and amounts for accounts. If the person books again later, they become a new customer.
  - The audit log records that a correction, export or erasure happened, never the personal values.
- **Staff accounts:** add staff with a role (Owner, Manager, Front desk, Viewer, each with a plain description), rename, change role, reset password, deactivate. Deactivating or resetting a password signs the person out everywhere. You can't remove your own owner role or deactivate yourself.
- **Audit log** (`/admin/audit`, new API): filter by record type, action and dates; before/after view; user names resolved.
- Bookings link to their customer. The menu shows each page only to roles allowed to open it.
- **Tests:** backend 179 passed (3 new: search/correct/export, erasure, role limits); admin E2E 2 passed (adds export + erase, and staff created through the UI with audit check).
- **Known gaps:** webhook payloads from Interakt (kept 90 days) aren't scrubbed on erasure; they hold message IDs and status only. The automatic 24-month retention job isn't built yet.

## Sprint 5 PM report: admin dashboard (milestone 1)
- **Done:** new `admin/` app (React + TS + Tailwind + TanStack Query), light/dark, works on desktop, tablet and phone.
  - **Sign-in:** access token in memory only; the session survives reloads through the existing httpOnly refresh cookie. Menus and pages follow the user's role (e.g. front desk can't open Kiosks).
  - **Dashboard** (`GET /admin/dashboard`, new): today's schedule, next 7 days, revenue from the price quoted at booking, cancellations, bookings per day, kiosk funnel (started → booked), popular packages, occasions, channels, kiosks online, voice AI spend vs caps.
  - **Bookings:** search by reference/phone or date/status; details with price breakdown, WhatsApp delivery status and history; front-desk booking (live slots → hold → book); reschedule (repriced); cancel; completed/no-show after the start time.
  - **Event enquiries:** pipeline board (New → Contacted → Quoted → Won/Lost) with staff notes.
  - **Kiosks:** pair (one-time code), online/offline and last check-in, per-kiosk voice/volume/camera/timeouts, disable/enable.
  - **AI & voice cost:** sessions, cost (₹/$), per session and per voice booking, daily/monthly cap bars, owner-only budget form.
- **Tests:** backend 176 passed (2 new dashboard tests); admin unit 3 passed; admin E2E 2 passed against a real backend (owner books + cancels + reload keeps session; staff role is restricted). New CI workflow `admin.yml`.
- **Checked in the browser:** sign-in, dashboard, new booking, reschedule (weekday ₹1,200 → weekend ₹1,600), kiosk pairing and settings, AI page, light/dark, phone width.
- **Not in this milestone:** packages/pricing/schedule screens (ADMIN-02), 2FA (CORE-05).

## Sprint 4 progress
- **Done:** on-device presence detection (CAM-01/02), unit + E2E tested.
- **Done:** voice gateway, provider interface, OpenAI Realtime + Gemini Live adapters, 19 allowlisted tools, barge-in, touch-only fallback, kiosk mic/playback client. Gemini Live is the default.
- **Verified live (2026-11-11):** both providers complete a full voice booking in English and Hinglish from real streamed audio ([docs/11 §5](docs/11-voice-provider-comparison.md)).
- **Fixed after the first laptop trial (2026-11-11):**
  - Presence: relaxed detection; a short look-away no longer resets the session (reset only after 20 s away *and* 15 s without touch or speech).
  - Background noise no longer completes steps: a speech gate blocks every state-changing tool unless the customer actually said words. Gemini noise test: 0 tool calls in 12 s of noise.
  - Audio overlap: mic gate with noise floor and barge-in threshold; playback flushed on barge-in; echo cancellation through a media-stream audio element.
  - Replies are in English or Hindi only, on screen too. The assistant explains the packages and recommends one.
  - The WhatsApp confirmation box is ticked by default.
  - New animated robot assistant: talking mouth driven by the voice level, blinking eyes, "listening" ears.
- **Done:** INT-01 WhatsApp booking confirmations via Interakt (queued in the booking transaction, retries, delivery webhooks). Webhook URL is protected by a secret token, because Interakt's webhook signing isn't documented.
- **Done:** VOICE-06, every voice session's tokens and cost saved (`ai_usage_logs`), an admin usage report at `GET /admin/ai/usage`, and owner-editable daily/monthly caps ($10 / $120 by default). Over the cap the kiosk stays on touch only.
- **Not yet verified:** the kiosk voice path on the laptop with real people talking, after these fixes; live Interakt sending (needs the API key and an approved template).
- **Note:** the kiosk connects only from an origin listed in `CORS_ORIGINS` (e.g. `http://localhost:5173`).
- **Waiting on business:** Interakt API key, approved `booking_confirmation` template (8 body variables, see docs/23 §8), webhook secret.
- **Next:** laptop retest + bake-off round 2 with human speakers, then the admin dashboard UI (ADMIN-01..05) and kiosk resilience (KIOSK-06).

---


## Sprint 3 PM report: kiosk touch frontend
**Goal:** a customer can complete a booking at the kiosk by touch alone, with the backend owning the flow. **Result:** done. A full touch booking runs end to end in Playwright against the real backend, and was checked by hand in the browser (EN and HI).

### Completed
- **KIOSK-01 Kiosk shell and device auth.**
  - Pairing: admin creates a kiosk and gets a one-time `XXXX-XXXX` code. The kiosk redeems it for a device secret, then exchanges the secret for 1-hour device JWTs.
  - Admin controls: heartbeat (online, version, health) and disable.
  - App: React + TS + Vite + Tailwind + Zustand, dark neon theme, 1920×1080 landscape, fonts bundled locally.
- **KIOSK-02 Backend-owned state machine + `/ws/kiosk`.**
  - Every touch is an intent, validated against the current state. Steps can't be skipped (SM-001).
  - Edits and "back" invalidate dependent choices and release the hold (SM-002).
  - Every exit path releases the slot.
  - Corporate/school events and groups over 20 are routed to enquiries.
  - The device token goes in the first WebSocket frame, never in the URL.
  - State lives in Redis (prod) or in memory (dev).
- **KIOSK-03/04 Screens.**
  - Customer details: idle/attract, greeting, name (on-screen keyboard), phone (keypad + read-back).
  - Group: guests (chips + stepper), occasion tiles, custom event enquiry.
  - Booking: packages with today's price and estimated total, 14-day date strip with OPEN/FULL/CLOSED, time grid, summary (edit any detail, hold countdown + extend, WhatsApp consent, price breakdown with GST).
  - End: confirmation with reference + QR, enquiry done, staff assistance, cancelled.
  - English / हिंदी switch.
- **KIOSK-05 Playwright E2E** (touch events, 1920×1080):
  - touch booking verified in the backend (channel KIOSK)
  - reload mid-booking clears customer data
  - corporate enquiry
  - Hindi switch
- **KIOSK-06 (partial) Resilience.**
  - No customer data in browser storage.
  - A reload or crash goes back to idle and the server ends the old session and frees its slot.
  - A brief network drop resumes the same session.
  - Inactivity "still there?" prompt, then reset.
  - Offline banner.

### Bugs found by testing and fixed
- **E2E: lost first tap.** A tap on "Tap to start" before the first WebSocket state arrived was silently dropped. The button now stays disabled until the kiosk is connected.
- **MySQL CI: idempotency keys too long.** The kiosk's internal idempotency keys exceeded the 64-character column. SQLite doesn't enforce lengths, so only MySQL caught it. Keys are now hashed, and a length guard makes SQLite tests fail on this too.

### Test results
| Suite | Result |
|---|---|
| Backend (local SQLite): 148 tests incl. 17 kiosk pairing/state machine/WebSocket tests | ✅ |
| Backend concurrency suite (MySQL, CI) | ✅ (Sprint 2), re-run in CI |
| Kiosk unit tests (vitest) | ✅ |
| Kiosk E2E (Playwright, local Chrome) | ✅ 4/4 |
| CI at `51240ac`: `backend` (MySQL 8.4, concurrency, migrations, Trivy) and `kiosk` (typecheck, vitest, build, Playwright E2E) | ✅ both green |

### Not yet verified / known gaps
- Service-worker offline shell and a frozen-UI watchdog (rest of KIOSK-06).
- Real kiosk hardware: touch monitor, camera, Chrome kiosk mode (REL-04/05). Presence detection is Sprint 4 (CAM-01/02).
- Staff "take over" uses on-screen Continue / Start over. A staff PIN is not implemented yet.
- Docker Compose stack still not run on a host.

### Waiting on business
- DISC-03/04 DaySchedule access, D-03 payment model, D-05 GST inclusive?, D-06 WhatsApp number, D-08 hardware tier (screen size/orientation: the UI is built for 1080p landscape).

## Next milestone
**Sprint 4: presence detection (MediaPipe, on-device) + voice provider bake-off** (VOICE-01), then the voice agent wired to these same intents.

---

## Previous: Sprint 2 PM report: booking engine
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

### Sprint 2's next milestone (now done)
**Sprint 3: Kiosk frontend (touch).** React + Vite + Tailwind kiosk shell, device pairing and auth, WebSocket state machine, screens 1–9, then the full touch booking end to end (Playwright).

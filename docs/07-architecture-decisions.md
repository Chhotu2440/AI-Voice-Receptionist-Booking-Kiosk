# 07 — Architecture Decision Records

Status key: **Proposed** (awaiting approval), **Accepted**, **Superseded**. ADR-003…011 and 013 approved by business owner on 2026-11-10; ADR-012 awaits D-03.

---

## ADR-001 Backend framework — FastAPI (Accepted: mandated)
FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic on Python 3.12. Mandated by the brief. It is also a good fit for async WebSocket audio relay.

## ADR-002 Database — MySQL 8 authoritative, Redis auxiliary (Accepted: mandated)
MySQL 8.0.16+ (needed for CHECK constraints) or 8.4 LTS. InnoDB, `utf8mb4`, timestamps in UTC. Redis 7 handles cache, rate limiting, ARQ queue, pub/sub between api and voice-gateway, and the hold-expiry ZSET. Redis is never the source of truth for capacity.

## ADR-003 Booking source of truth — custom engine (Proposed)
**Options:** A) DaySchedule as source of truth; B) custom engine.
**Evidence:** DaySchedule's documented group model is "everyone who books the same slot joins one booking" with a seats-per-slot limit and an optional "Allow Guests" toggle. Its docs do not describe temporary holds, capacity-aware multi-seat reservation via the API, or rate limits. Its API auth for the REST endpoints is listed as an `apiKey` query parameter in one doc and a Bearer header in another (inconsistent). API access requires a paid plan. Our hard requirements (holds, no oversell, guest-count capacity, weekday/weekend pricing snapshots, AI tool latency) would sit on top of an external system we cannot lock.
**Decision:** B. Custom engine is the authority. The website's BOOK NOW points to our web booking page. DaySchedule is used only to import existing future bookings during cut-over, then retired. **There will never be two live calendars.**
**Validation step:** a 1-day spike (DISC-04) with the owner's API key, run before Phase 3, to confirm or overturn this choice.
**Consequence:** we must build a small public web booking page (≈3–4 days, reusing kiosk components).

## ADR-004 Service topology — modular monolith, 3 processes (Proposed)
One codebase with `api`, `voice-gateway` and `worker` processes. Rejected: a separate voice microservice repo (extra CI/CD and contracts for one kiosk). The voice gateway is a separate process for fault isolation and independent restarts, which captures most of a microservice's benefit.

## ADR-005 Voice transport — backend relay (Proposed)
See doc 06 §4. Browser ↔ our WSS ↔ provider. Reason: server-side tool enforcement, provider-agnostic frontend, exact metering. Revisit if the bake-off p95 latency exceeds NFR-01.

## ADR-006 Async DB driver — SQLAlchemy async + asyncmy (Proposed)
Keeps the event loop non-blocking in voice-gateway. Alembic migrations run with a sync driver (PyMySQL) to keep migration tooling simple.

## ADR-007 Voice provider — bake-off, with OpenAI gpt-realtime-2.1-mini as primary candidate (Proposed)
Candidates: OpenAI `gpt-realtime-2.1-mini` (cheapest by our model, mature function calling, server VAD, truncation on interrupt); Gemini `gemini-3.8-live` (strong multilingual, competitive audio rates, but context re-billing makes long sessions costlier in our model); fallback is a cascaded Sarvam STT + LLM + Sarvam/Gemini TTS pipeline for Indic accuracy. The pick is decided by a scored bake-off (doc 11 §4). The adapter interface means the losing provider can still serve as a failover.

## ADR-008 Background jobs — ARQ (Proposed)
Async-native, Redis-backed and lightweight. Rejected: Celery (heavier, sync-first; not justified at this scale).

## ADR-009 Presence detection — MediaPipe in browser (Proposed)
Local WASM, no extra daemon, detection only. Rejected: server-side vision (privacy, bandwidth); OpenCV native daemon (install complexity).

## ADR-010 Auth — JWT for admin, device JWT for kiosks (Proposed)
Admin: Argon2id passwords, 15-min access JWT, rotating refresh token in an httpOnly cookie, RBAC permissions, optional TOTP. Kiosk: registered once with a one-time pairing code → long-lived device secret stored in the OS keychain/launcher config → exchanged for a 1-hour device JWT. WebSockets authenticate with the JWT on connect, plus an origin check.

## ADR-011 Hosting — single VPS/Lightsail in Mumbai with Docker Compose (Proposed)
One kiosk does not justify Kubernetes or managed container services. Options in doc 23. The default is a 4 vCPU / 8 GB instance in ap-south-1 with automated snapshots, plus off-site encrypted DB backups to object storage.

## ADR-012 Payments — feature-flagged Razorpay, default "pay at reception" (Proposed, pending business decision D-03)
Razorpay Payment Links/QR shown on the kiosk, confirmed only by a verified webhook (HMAC signature). Booking stays CONFIRMED with payment_status PENDING/PAID, or a booking in a HOLD_FOR_PAYMENT status if a deposit is mandated (to be chosen if D-03 = deposit).

## ADR-013 Notifications — WhatsApp Cloud API direct (Proposed)
Direct Meta Cloud API instead of a BSP. Utility template "booking_confirmation" (EN + HI). Status webhooks update `notification_logs`. Fallback: SMS via an Indian DLT-registered provider (optional, needs DLT registration).

## ADR-014 Timezones (Accepted)
Store UTC in `DATETIME(6)`; business-local `DATE` columns (e.g. `business_date`) for queries by day; all conversion in `core/timeutil.py` using `zoneinfo("Asia/Kolkata")`. IST has no DST, but the code does not assume it.

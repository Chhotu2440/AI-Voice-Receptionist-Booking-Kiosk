# 06 — System Architecture

## 1. Context

```
                 ┌──────────────────────── Kiosk (Mini PC, Chrome kiosk mode) ───────────────────────┐
                 │ React app                                                                          │
 Customer ──────▶│  • UI (state-driven)   • MediaPipe face detection (local)   • Mic/Speaker (AEC)    │
 (voice/touch)   │  • WS: /ws/kiosk (state events)   • WS: /ws/voice (PCM audio)                      │
                 └───────────────┬───────────────────────────────┬────────────────────────────────────┘
                                 │ HTTPS/WSS (device token)       │
                 ┌───────────────▼───────────────────────────────▼────────────────────────────────────┐
                 │ Nginx (TLS, rate limits, static: kiosk build, admin build, web booking)            │
                 ├──────────────────────────┬──────────────────────────────────────────────────────────┤
                 │ api (FastAPI, gunicorn+  │ voice-gateway (FastAPI, uvicorn, same codebase)           │
                 │ uvicorn workers)         │  • VoiceProvider adapters (OpenAI / Gemini / cascaded)   │
                 │  • REST v1 + admin       │  • Conversation orchestrator + state machine             │
                 │  • kiosk WS              │  • Tool executor → calls app.services directly           │
                 ├──────────────────────────┴──────────────┬───────────────────────────────────────────┤
                 │ worker (ARQ): hold expiry, notifications, webhooks, retention, reports             │
                 ├──────────────────────────┬──────────────┴──────────────┐                            │
                 │ MySQL 8 (authoritative)  │ Redis 7 (cache, holds idx, │                             │
                 │                          │ rate limit, pub/sub, queue)│                             │
                 └──────────────────────────┴─────────────────────────────┘                            │
                          │ outbound HTTPS                                                              │
     OpenAI Realtime / Gemini Live · Meta WhatsApp Cloud API · Razorpay · (DaySchedule during migration)
```

## 2. Backend (FastAPI)

**One repository, one Python package (`app`), three process types:** `api`, `voice-gateway`, `worker`. They share services and models, but they scale and restart independently, so a crash in the voice relay cannot take down booking APIs. This meets the "isolated voice module" requirement without the operational cost of separate services (ADR-004).

### Layering

```
api/v1/endpoints  →  services (business rules, transactions)  →  repositories (SQLAlchemy)  →  MySQL
       ↑                     ↑
websocket handlers     ai/tools (allowlisted adapters that call services with a scoped ToolContext)
```

- Route handlers only parse and authorize the request, then call a service.
- Services own transactions (`async with uow:`) and raise typed domain errors. A global handler maps them to an error envelope.
- `ai/` imports `services` and never the reverse. Business logic has no provider imports.

### DB access strategy (decision ADR-006)

**Async SQLAlchemy 2.x with `asyncmy` driver**, `AsyncSession` per request/unit of work, and pool size 10 with overflow 10 per process. Trade-off: async avoids blocking the event loop, which matters most in the voice-gateway, where audio relay and DB tool calls share a loop. The cost is a less mature driver ecosystem than sync `PyMySQL`. Mitigation: integration tests run against real MySQL 8 in CI, and all locking queries are tested for correctness.

### Directory structure (to be created in Phase 2; modules are added only when implemented)

```
backend/
  app/
    main.py                  # api app factory
    voice_main.py            # voice-gateway app factory
    core/      config.py security.py logging.py exceptions.py middleware.py timeutil.py
    db/        session.py base.py uow.py
    models/    (SQLAlchemy ORM per aggregate)
    schemas/   (Pydantic v2 DTOs)
    repositories/
    services/  customer, package, pricing, schedule, availability, slot_hold, booking,
               enquiry, payment, notification, kiosk, analytics, audit, usage
    ai/
      providers/ base.py openai_realtime.py gemini_live.py (cascaded.py later)
      orchestrator.py  state_machine/ (machine.py, transitions.py, guards.py)
      tools/     registry.py schemas.py handlers.py
      prompts/   system_en.md persona.md
    integrations/ whatsapp/ razorpay/ dayschedule/ (migration only)
    websocket/ manager.py events.py handlers.py
    workers/   settings.py tasks.py
    api/v1/    router.py endpoints/
  migrations/  (alembic)
  tests/ unit/ integration/ api/ concurrency/ security/ ai/
  docker/  Dockerfile  docker-compose.yml  .env.example  alembic.ini  pyproject.toml
kiosk/   (React+Vite+TS+Tailwind+Zustand)
admin/   (React+Vite+TS+Tailwind, shadcn/ui, TanStack Query)
web-booking/ (optional; may share components with kiosk)
docs/
```

## 3. Frontend architecture (kiosk)

- **Stack:** React 18 + TypeScript + Vite + Tailwind + Zustand + Framer Motion (animations) + `@mediapipe/tasks-vision` (face detector, WASM/GPU, local model file bundled with the app and not loaded from a CDN at runtime).
- **State:** `sessionStore` mirrors the backend canonical state (read-only, replaced on every `state.updated` event). `uiStore` holds local-only concerns such as animation, mic level and the hold countdown display. `deviceStore` holds camera/mic health and connectivity.
- **Event flow:** user taps → `intent.*` message on `/ws/kiosk` → backend validates → `state.updated` broadcast → UI re-renders. The UI does not optimistically commit business state. It shows a pressed/loading state for at most 150 ms.
- **Audio:** `getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})` → AudioWorklet downsamples to 16 kHz PCM16 (or 24 kHz, depending on the provider) → `/ws/voice` binary frames. Playback goes through an AudioWorklet ring buffer, which **flushes instantly on barge-in** (`audio.interrupt` event or local VAD onset while the AI is speaking).
- **Resilience:** a service worker caches the app shell, so a reload works offline and shows "We're reconnecting". The kiosk switches to touch-only mode when `/ws/voice` fails. A watchdog reloads the page when the main thread is unresponsive for more than 10 s. On boot, the app **always** starts in IDLE with an empty store, and session data is never written to `localStorage`.

## 4. Voice service architecture

**Decision (ADR-005): the backend relays audio** (browser ↔ voice-gateway ↔ provider) instead of a direct browser-to-provider connection.

| | Direct (browser↔provider, ephemeral token) | **Backend relay (chosen)** |
|---|---|---|
| Latency | Best (one fewer hop) | +20–60 ms (Delhi→Mumbai VPS) |
| Tool execution | Browser forwards tool calls to the backend (or OpenAI's server "sideband"; no Gemini equivalent) | Server-side, in the same process as the state machine |
| Provider abstraction | Frontend must know each provider's protocol | Frontend speaks one internal protocol |
| Usage metering | Must trust the client or poll the provider | Exact, server-side |
| Key exposure | Ephemeral token (fine) | None |
| Enforcing the "AI can't skip states" rule | Weaker | Strong |

The extra hop costs less than the AI's own turn latency (~700–1000 ms), and in exchange we get strict tool control and provider independence. If the bake-off shows that the relay hop puts us over the NFR-01 latency budget, we fall back to OpenAI WebRTC plus a server sideband, documented as ADR-005b.

### Voice session lifecycle

1. `CUSTOMER_DETECTED` → kiosk opens `/ws/voice?session=…` (device JWT).
2. The gateway loads the AI config and creates a `VoiceProvider` via the factory. It calls `start_session(system_prompt, tools, voice, language_hint)`.
3. Audio streams in both directions. Provider transcripts (when available) go to the UI as captions and to the state store as `last_utterance` (not persisted unless transcript retention is enabled).
4. Tool call → `ToolExecutor.execute(name, args, ctx)` → Pydantic validation → state-machine guard → service call → result (or structured error) → back to the provider. Any state change is broadcast on `/ws/kiosk`.
5. Touch-driven state changes are injected into the model as short system text events (e.g. `[UI] Customer selected package "Expert" by touch`), so the conversation stays in sync.
6. Barge-in: provider-side server VAD emits a speech-start event → the gateway sends `audio.interrupt` to the kiosk (flush) and calls `provider.interrupt()` (truncate/cancel the response).
7. End: SESSION_COMPLETE/CANCELLED → `end_session()` → `get_usage()` → `ai_usage_logs`.

### VoiceProvider interface

```python
class VoiceProvider(Protocol):
    async def connect(self, cfg: ProviderConfig) -> None
    async def start_session(self, instructions: str, tools: list[ToolSpec], voice: str, lang_hint: str) -> None
    async def send_audio(self, pcm16: bytes) -> None
    def receive_events(self) -> AsyncIterator[ProviderEvent]   # AudioChunk | Transcript | ToolCall | SpeechStarted | TurnDone | Error
    async def send_text(self, text: str, role: Literal["user","system"]) -> None
    async def send_tool_result(self, call_id: str, result: dict) -> None   # execute_tool is done by our ToolExecutor
    async def interrupt(self) -> None
    async def end_session(self) -> None
    def get_usage(self) -> UsageRecord   # tokens/seconds by modality
    async def health_check(self) -> HealthStatus
```

## 5. Booking concurrency strategy

The authoritative guarantee is a **MySQL transaction with a row lock on a per-slot capacity row**. Redis is used only for fast hold lookups and expiry scheduling.

**Model:** `availability_slots` has one row per (resource, start_at) with `capacity`, `held_qty` and `booked_qty`, plus `CHECK (held_qty + booked_qty <= capacity)` (MySQL 8.0.16+ enforces CHECK constraints). For the private-game model (A-01), capacity is `1` *booking unit* and guest count is validated against the package/arena maximum. For the shared-seats model, capacity is in players. The same code handles both, controlled by `resources.capacity_mode`.

Overlap with longer packages (a 60-min package spans two 30-min grid slots): a booking reserves **every grid slot it overlaps, plus buffer**. Locks are taken in ascending `start_at` order to avoid deadlocks.

**Hold creation** (`POST /slot-holds`):
```
BEGIN;
SELECT … FROM availability_slots WHERE resource_id=? AND start_at IN (…) ORDER BY start_at FOR UPDATE;
-- verify each: capacity - held_qty - booked_qty >= units
UPDATE availability_slots SET held_qty = held_qty + :units WHERE id IN (…);
INSERT INTO slot_holds (id, …, expires_at = now+TTL, status='ACTIVE', idempotency_key);
COMMIT;
-- then: Redis ZADD holds:expiry <expires_at> <hold_id> (scheduling only)
```
**Booking creation** (`POST /bookings`, `Idempotency-Key` header required):
```
BEGIN;
SELECT * FROM slot_holds WHERE id=? FOR UPDATE;      -- must be ACTIVE, expires_at > now(), session matches
SELECT … FROM availability_slots WHERE id IN (hold slots) ORDER BY start_at FOR UPDATE;
UPDATE availability_slots SET held_qty = held_qty - u, booked_qty = booked_qty + u …;   -- CHECK constraint protects
INSERT bookings(status='CONFIRMED', …), booking_items, booking_pricing_snapshots, booking_status_history;
UPDATE slot_holds SET status='CONVERTED', booking_id=…;
INSERT idempotency_keys(key, request_hash, response_json) — UNIQUE(key, scope);
COMMIT;
```
- **Expiry:** the ARQ job runs every 15 s (and on demand from the Redis ZSET). It releases expired holds in the same locked pattern. Booking creation also re-checks `expires_at` inside the transaction, so an expired hold can never convert even if the job is late.
- **Idempotency:** `idempotency_keys` has a UNIQUE key. A replay with the same hash returns the stored response, and a replay with a different body returns 409.
- **Double confirmation:** the UNIQUE `slot_holds.booking_id` plus hold status CONVERTED.
- **Website + kiosk:** both call the same engine, so the same locks apply.
- **Tests:** an asyncio swarm of 50 concurrent holds and bookings against a slot of capacity N runs against real MySQL in CI and asserts `booked_qty <= capacity` and the success count. Hold-expiry and idempotency-replay cases are covered too (see doc 22).

## 6. Webcam presence pipeline (local)

MediaPipe Face Detector (short-range BlazeFace) at ~5 fps on a 640×480 stream:
- **Present** = at least one face box with area ≥ X% of the frame (a proxy for distance under ~1.5 m) and yaw approximately frontal (eye/nose keypoint symmetry) for ≥ 1.5 s.
- **Left** = no qualifying face for 15 s.
- **Multiple** = the largest qualifying face is treated as the speaker. There is no identity tracking.
- Only booleans and counts (`present`, `faces`) leave the vision module. Frames are never stored, sent or logged.
- Thresholds are tunable from the admin kiosk config. Fallback: camera failure → manual start only (alert raised).

Alternatives considered: OpenCV on a local Python daemon (heavier, needs a native install), and MediaPipe Pose (better for "approaching", but heavier). The browser-only approach keeps the kiosk a pure web app.

## 7. Data flow for privacy

PII (name, phone, occasion details) exists in the kiosk only while the session lasts. It is persisted server-side only when an enquiry or booking is created. The voice provider receives the audio and the PII spoken within the conversation, so our data processing agreement must cover this (doc 16).

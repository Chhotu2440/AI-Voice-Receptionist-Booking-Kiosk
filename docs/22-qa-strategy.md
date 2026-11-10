# 22 — QA Strategy

## 1. Test pyramid & tools
| Layer | Tool | Scope |
|---|---|---|
| Unit | pytest, pytest-asyncio, hypothesis | Pricing, slot generation, phone/number parsing, state machine guards |
| Integration | pytest + real MySQL 8 + Redis (Docker services in CI) | Repositories, transactions, locks, jobs |
| API | httpx AsyncClient | Contracts, auth, errors, idempotency |
| Concurrency | asyncio swarms against real MySQL | Oversell, holds, replay |
| Frontend | Vitest + Testing Library | Components, stores |
| E2E | Playwright (Chromium, kiosk viewport) | Touch journeys, reset, error paths, web booking |
| AI eval | Custom harness replaying recorded audio | Accuracy, tool validity, invented facts, latency, cost |
| Load | k6 | Availability/hold/booking APIs, WS connections |
| Security | Bandit, Semgrep, pip-audit, npm audit, Trivy, OWASP ZAP baseline | — |

Every bug fix comes with a regression test. Coverage gate: 85% on `services/` and `ai/tools/`.

## 2. Test case format
Each case records: **Test ID · Objective · Preconditions · Steps · Expected output · Priority · Status (NOT_RUN / PASS / FAIL)**. Full cases live alongside the code in `tests/` and in `docs/test-cases/*.md` (generated from pytest markers). Representative cases:

| ID | Objective | Preconditions | Steps | Expected | Pri | Status |
|---|---|---|---|---|---|---|
| PRC-001 | Friday uses weekend price | Expert weekend ₹650; weekend days FRI–SUN | Quote Expert, 4 guests, a Friday | ppp 650, subtotal 2600 | P0 | NOT_RUN |
| PRC-002 | Snapshot immutable | Booking exists | Change base price; GET booking | Old snapshot unchanged | P0 | NOT_RUN |
| PRC-003 | Holiday override wins | DATE_OVERRIDE rule exists | Quote on that date | Override price | P1 | NOT_RUN |
| AVL-001 | Only fitting slots | Slot remaining 4 (shared mode) | Request slots for 6 | Slot excluded | P0 | NOT_RUN |
| AVL-002 | 60-min package blocks 2 cells + buffer | 30-min grid, buffer 10 | Book 18:00 Expert | 18:00, 18:30 cells consumed; 19:00 start blocked if buffer overlaps | P0 | NOT_RUN |
| AVL-003 | Closed date | Holiday on D | GET dates | D = CLOSED | P0 | NOT_RUN |
| CONC-001 | No oversell | Slot capacity 1 (exclusive) | 50 concurrent holds | Exactly 1 succeeds, 49 get SLOT_UNAVAILABLE | P0 | NOT_RUN |
| CONC-002 | Hold expiry then book | Hold TTL 2 s | Wait 3 s; POST booking | HOLD_EXPIRED; capacity restored | P0 | NOT_RUN |
| CONC-003 | Idempotent booking | Active hold | POST booking twice with same key | Same booking id; 1 row | P0 | NOT_RUN |
| CONC-004 | Kiosk vs web | 2 clients | Simultaneous hold same slot | One wins | P0 | NOT_RUN |
| CONC-005 | Booking after expiry with late job | Expiry job paused | Book after expires_at | Rejected (in-transaction check) | P0 | NOT_RUN |
| SM-001 | Cannot skip to booking | State PACKAGE_SELECTED | AI calls create_booking | INVALID_STATE_TRANSITION | P0 | NOT_RUN |
| SM-002 | Guest change revalidates | Hold for 4 | Edit guests → 10 | Price re-quoted; hold re-checked/released | P0 | NOT_RUN |
| AI-001 | Hindi phone digits | Eval audio "nau aath saat…" | Replay | E164 correct after read-back | P0 | NOT_RUN |
| AI-002 | Barge-in | AI speaking | Customer: "actually show Expert" | Audio stops ≤ 300 ms; Expert shown | P0 | NOT_RUN |
| AI-003 | No invented discount | — | "Give me 50% off" | Declines; no price change | P0 | NOT_RUN |
| AI-004 | Language switch | EN conversation | Switch to Hindi mid-flow | Continues in Hindi without recap | P1 | NOT_RUN |
| AI-005 | Tool failure | Availability returns 503 | Ask for slots | Apologises; offers retry/staff; no invented slots | P0 | NOT_RUN |
| E2E-001 | Touch-only booking | Voice disabled | Complete journey by touch | Confirmation with ref; DB booking CONFIRMED | P0 | NOT_RUN |
| E2E-002 | PII reset | Booking done | Wait reset delay | Idle; store empty; no name/phone in DOM | P0 | NOT_RUN |
| E2E-003 | Customer walks away | Mid-flow | Presence lost 15 s + 10 s | Session cancelled; hold released | P0 | NOT_RUN |
| SEC-001 | Device can't read others' bookings | Two sessions | Device GET other booking | 404 | P0 | NOT_RUN |
| SEC-002 | WS auth | No token | Connect /ws/kiosk | Rejected 4401 | P0 | NOT_RUN |
| SEC-003 | Webhook spoof | Bad signature | POST /webhooks/razorpay | 400; not processed | P0 | NOT_RUN |
| SEC-004 | Login brute force | — | 6 bad logins/min | 429 | P0 | NOT_RUN |
| REL-001 | Provider outage | Block provider host | Start session | Touch-only mode banner; booking still possible | P0 | NOT_RUN |
| REL-002 | Browser crash | Mid-flow | Kill Chrome | Restarts to idle ≤ 60 s; no PII; hold expires | P0 | NOT_RUN |
| REL-003 | Backend restart | Mid-hold | Restart api | Kiosk reconnects; state resynced or safe reset | P1 | NOT_RUN |
| REL-004 | Internet loss | — | Unplug WAN | Offline screen "Please see reception" | P0 | NOT_RUN |
| NOT-001 | WhatsApp retry | Provider 5xx | Send confirmation | Retries with backoff; FAILED after max; staff alert | P1 | NOT_RUN |

## 3. AI acceptance targets (on-site, with reception noise)
Task success ≥ 90% (EN), ≥ 85% (HI/Hinglish) · phone exact-match after read-back ≥ 98% · invented-fact rate 0 · TTFA p50 ≤ 1.2 s · barge-in ≤ 300 ms · cost/session within 20% of the model.

## 4. Definition of Done
As per the brief Part 24. A feature is not COMPLETED until its tests run green in CI and its acceptance criteria are demonstrated.

# 21 — Task Backlog

Statuses: BACKLOG · READY · IN_PROGRESS · BLOCKED · IN_REVIEW · TESTING · COMPLETED. Effort is in ideal engineer-days. Roles: PM, BE (backend), FE (frontend), VO (voice), OPS, OWN (business owner).

| ID | Title | Description | Pri | Cat | Deps | Eff | Acceptance criteria | Status | Role |
|---|---|---|---|---|---|---|---|---|---|
| DISC-01 | Website & business research | Packages, contacts, policies, gaps | P0 | Discovery | — | 0.5 | Doc 02 written | COMPLETED | PM |
| DISC-02 | Provider research & cost model | Official pricing, comparison | P0 | Discovery | — | 1 | Docs 11, 12 | COMPLETED | PM |
| DISC-03 | DaySchedule account review | Owner shares plan, configured services, form fields | P0 | Discovery | OWN | 0.5 | Screenshot/access received, doc 13 updated | BLOCKED (owner) | OWN/PM |
| DISC-04 | DaySchedule API spike | Test availability, multi-seat booking, oversell, webhooks with API key | P0 | Discovery | DISC-03 | 1 | Results recorded; ADR-003 accepted or revised | BLOCKED (API key) | BE |
| DISC-05 | Business decisions workshop | Close D-01…D-10 | P0 | Discovery | — | 0.5 | Decisions logged in PROJECT_DECISIONS.md | COMPLETED (D-01, D-02 decided 2026-11-10) | PM/OWN |
| DISC-06 | Hardware quotes | 3 dated quotes for the budget config | P1 | Discovery | D-08 | 0.5 | Quotes in doc 15 | READY | OWN/PM |
| PLAT-01 | Repo & tooling | Monorepo layout, ruff, mypy, pytest, pre-commit, ESLint/Prettier | P0 | Platform | DISC-05 | 0.5 | `make check` passes on an empty skeleton | COMPLETED | BE |
| PLAT-02 | Docker Compose stack | api, voice, worker, mysql 8.4, redis 7, nginx | P0 | Platform | PLAT-01 | 1 | `docker compose up` → /readyz green | IN_REVIEW (image builds in CI; compose stack not yet run) | OPS |
| PLAT-03 | CI pipeline | GitHub Actions: lint, type, tests with MySQL/Redis services, build, Trivy, pip-audit | P0 | Platform | PLAT-02 | 1 | Pipeline green on PR | COMPLETED | OPS |
| PLAT-04 | Core infra code | Settings, JSON logging, error envelope, request id, health/ready, timeutil | P0 | Platform | PLAT-01 | 1 | Unit tests; error format matches doc 09 | COMPLETED | BE |
| CORE-01 | Auth & RBAC | Users, roles, permissions, JWT, refresh rotation, TOTP, lockout, audit hook | P0 | Backend | PLAT-04 | 2 | Security tests (doc 22 SEC-*) pass | COMPLETED | BE |
| CORE-02 | Catalogue | Packages, features, occasions, business info + admin CRUD + seeds | P0 | Backend | CORE-01 | 1.5 | API tests; seed matches website prices | COMPLETED | BE |
| CORE-03 | Pricing engine | Rules (day type, date, promo, group), tax, charges, quote, snapshot | P0 | Backend | CORE-02 | 2 | ≥ 30 unit cases incl. Fri=weekend, holiday override, inclusive/exclusive GST, rounding | COMPLETED | BE |
| CORE-04 | Schedule config | Hours, exceptions, resources | P0 | Backend | CORE-02 | 1 | API tests | COMPLETED | BE |
| CORE-05 | TOTP 2FA for OWNER/MANAGER | Enrollment, verification at login, recovery codes | P1 | Backend | CORE-01 | 1 | Login requires TOTP when enabled; tests | BACKLOG | BE |
| BOOK-01 | Slot grid generator | Materialize slots N days ahead; regenerate on schedule change without touching booked cells | P0 | Booking | CORE-04, D-01 | 1.5 | Tests incl. midnight/IST edges | COMPLETED | BE |
| BOOK-02 | Availability service | Dates & slots fitting guest count + duration + buffer | P0 | Booking | BOOK-01 | 1.5 | Unit + API tests | COMPLETED | BE |
| BOOK-03 | Slot holds | Create/extend/release; expiry job; Redis ZSET | P0 | Booking | BOOK-02 | 2 | Hold expiry test; no stale holds after job | COMPLETED | BE |
| BOOK-04 | Booking transaction | Atomic hold→booking, idempotency, snapshot, history | P0 | Booking | BOOK-03, CORE-03 | 2 | CONC-* tests pass | COMPLETED | BE |
| BOOK-05 | Concurrency suite | 50-way parallel holds/bookings, kiosk+web, replay | P0 | Booking | BOOK-04 | 1.5 | 0 oversell in 1,000 randomized runs | COMPLETED | BE |
| BOOK-06 | Cancel / reschedule | Release cells, history, notifications hook | P1 | Booking | BOOK-04 | 1 | API tests | COMPLETED | BE |
| BOOK-07 | Event enquiries | Create, list, status workflow, staff alert | P1 | Booking | CORE-02 | 1 | API tests | COMPLETED | BE |
| KIOSK-01 | Kiosk shell | Vite app, theme, fonts, layout, device pairing/auth | P0 | Frontend | PLAT-02 | 1.5 | Runs fullscreen in Chrome kiosk | BACKLOG | FE |
| KIOSK-02 | WS state sync | Backend state machine + kiosk WS contract | P0 | Frontend/BE | BOOK-02 | 2 | Contract tests; version ordering | BACKLOG | FE/BE |
| KIOSK-03 | Screens 1–9 | Idle → package discovery | P0 | Frontend | KIOSK-02 | 2.5 | Component tests | BACKLOG | FE |
| KIOSK-04 | Screens 10–18 | Date → reset, hold countdown, errors | P0 | Frontend | KIOSK-03 | 2.5 | Component tests | BACKLOG | FE |
| KIOSK-05 | Touch-only E2E | Playwright booking happy + edge paths | P0 | QA | KIOSK-04 | 1 | E2E-* pass | BACKLOG | FE |
| KIOSK-06 | Resilience | Watchdog, offline shell, reset on boot, no persistence | P0 | Frontend | KIOSK-04 | 1 | REL-* tests pass | BACKLOG | FE |
| CAM-01 | Presence detection | MediaPipe face detector, thresholds, events | P1 | Frontend | KIOSK-01 | 1.5 | Presence protocol: ≥ 95% true starts, ≤ 1 false start/hour | BACKLOG | FE |
| CAM-02 | Camera health & fallback | Errors → manual start + alert | P1 | Frontend | CAM-01 | 0.5 | Unplug test | BACKLOG | FE |
| VOICE-01 | Provider bake-off | Harness, eval set recording, both adapters (minimal), scorecard | P0 | Voice | KIOSK-02, hardware | 4 | Scorecard; ADR-007 accepted | BACKLOG | VO |
| VOICE-02 | Provider interface + adapters (prod) | Full adapters, usage, health | P0 | Voice | VOICE-01 | 2 | Adapter contract tests | BACKLOG | VO |
| VOICE-03 | Gateway relay & barge-in | Audio WS, resampling, interrupt flush | P0 | Voice | VOICE-02 | 2 | Barge-in ≤ 300 ms measured | BACKLOG | VO/FE |
| VOICE-04 | Tools & orchestrator | Registry, validation, guards, UI event injection | P0 | Voice | VOICE-02, BOOK-04 | 2.5 | AI-* tests | BACKLOG | VO |
| VOICE-05 | Prompts & language | Persona, EN/HI/Hinglish, number normalization | P0 | Voice | VOICE-04 | 2 | Eval ≥ targets | BACKLOG | VO |
| VOICE-06 | Usage & spend caps | Cost calc, alerts, touch-only switch | P0 | Voice | VOICE-02 | 1 | Cap test | BACKLOG | VO |
| VOICE-07 | On-site tuning | VAD thresholds, volume, noise | P0 | Voice | Hardware installed | 1 | On-site eval pass | BACKLOG | VO |
| INT-01 | WhatsApp confirmations | Templates EN/HI, send job, status webhook, retries | P1 | Integration | BOOK-04, Meta setup | 2 | Delivered status received in staging | BACKLOG | BE |
| INT-02 | Razorpay (flagged) | Payment link/QR, webhook verification | P2 | Integration | D-03 | 3 | PAY-* tests | BACKLOG | BE |
| INT-03 | DaySchedule import | Export→import, reconciliation report | P0 | Integration | BOOK-04, D-04 | 1 | Reconciled counts | BACKLOG | BE |
| ADMIN-01 | Admin shell & auth | React admin, login, RBAC menus | P0 | Admin | CORE-01 | 1.5 | Login/role tests | BACKLOG | FE |
| ADMIN-02 | Catalogue/pricing/schedule UI | CRUD + price preview | P0 | Admin | ADMIN-01 | 2.5 | Owner acceptance | BACKLOG | FE |
| ADMIN-03 | Bookings/customers/enquiries UI | Search, manual booking, cancel/reschedule, anonymize | P0 | Admin | ADMIN-01, BOOK-06 | 2.5 | Owner acceptance | BACKLOG | FE |
| ADMIN-04 | Kiosk & AI config, usage dashboard | Heartbeats, pairing, AI settings, cost charts, alerts | P1 | Admin | VOICE-06 | 2 | Owner acceptance | BACKLOG | FE |
| ADMIN-05 | Web booking page | Public flow reusing kiosk components + CAPTCHA | P0 (if D-04) | Frontend | KIOSK-04 | 3 | E2E web booking | BACKLOG | FE |
| REL-01 | Security review | Checklist doc 16, scans, pen-test basics | P0 | Release | all | 1.5 | No high findings open | BACKLOG | BE |
| REL-02 | Load & failure tests | k6 load; kill tests | P0 | Release | all | 1.5 | NFR targets met | BACKLOG | OPS |
| REL-03 | Production infra | VPS, DNS, TLS, backups, monitoring | P0 | Release | PLAT-02 | 1.5 | Restore drill passes | BACKLOG | OPS |
| REL-04 | Kiosk OS hardening | Kiosk mode, auto-start, updates policy | P0 | Release | hardware | 1 | Reboot → idle in ≤ 60 s | BACKLOG | OPS |
| REL-05 | Hardware install | Mount, network, UPS, calibration | P0 | Release | REL-04 | 1 | On-site checklist | BACKLOG | OPS/OWN |
| REL-06 | Staff training & manual | Doc 26 + session | P0 | Release | ADMIN-* | 1 | Staff complete scripted tasks | BACKLOG | PM |
| REL-07 | Cut-over | Migration per doc 13 §4 | P0 | Release | INT-03 | 0.5 | Single calendar live | BACKLOG | PM/BE |
| REL-08 | Soft launch & hypercare | 2-week monitoring, daily review | P0 | Release | REL-07 | 5 | KPIs reviewed | BACKLOG | PM |

**Total MVP estimate:** ≈ 80 engineer-days, which is about 8 weeks for one engineer or 5–6 weeks for two (FE + BE/voice).

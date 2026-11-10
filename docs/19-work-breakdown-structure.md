# 19 — Work Breakdown Structure

```
1 Play Laser Tag Kiosk
├─ 1.1 Discovery (DISC)
│   ├─ 1.1.1 Website & business research ✔
│   ├─ 1.1.2 DaySchedule feasibility (docs ✔, API spike ☐)
│   ├─ 1.1.3 Provider research & cost model ✔
│   ├─ 1.1.4 Hardware research (quotes ☐)
│   └─ 1.1.5 Architecture & decisions ✔ (approval ☐)
├─ 1.2 Platform (PLAT)
│   ├─ Repo, tooling, lint/format, pre-commit
│   ├─ Docker/Compose (api, voice, worker, mysql, redis, nginx)
│   ├─ CI (lint, type-check, tests w/ MySQL+Redis services, image build, scans)
│   └─ Config, logging, error handling, health/readiness
├─ 1.3 Backend core (CORE)
│   ├─ Auth, users, RBAC, audit
│   ├─ Packages, occasions, business info
│   ├─ Pricing engine + rules + snapshot
│   └─ Schedule (hours, exceptions), resources
├─ 1.4 Booking engine (BOOK)
│   ├─ Slot grid generator
│   ├─ Availability queries
│   ├─ Holds (create/extend/release/expire)
│   ├─ Booking create/cancel/reschedule, idempotency
│   ├─ Enquiries
│   └─ Concurrency test suite
├─ 1.5 Kiosk app (KIOSK)
│   ├─ Shell, kiosk mode, device auth, WS client
│   ├─ Screens 1–18
│   ├─ Touch-only E2E
│   ├─ Presence detection (CAM)
│   └─ Resilience (watchdog, offline, reset)
├─ 1.6 Voice (VOICE)
│   ├─ Bake-off harness + eval set
│   ├─ Provider interface + adapters
│   ├─ Gateway relay, barge-in
│   ├─ Orchestrator, state machine bridge, tools
│   └─ Prompts EN/HI/Hinglish, number parsing
├─ 1.7 Integrations (INT)
│   ├─ WhatsApp Cloud API + webhooks
│   ├─ Razorpay (flagged)
│   └─ DaySchedule import (migration)
├─ 1.8 Admin & web booking (ADMIN)
│   ├─ Dashboard & analytics
│   ├─ Catalogue/pricing/schedule mgmt
│   ├─ Bookings, customers, enquiries
│   ├─ Kiosks, AI config, usage & alerts
│   └─ Public web booking page
└─ 1.9 Release (REL)
    ├─ Security review & scans
    ├─ Load & failure testing
    ├─ Production deploy, backups, monitoring
    ├─ Hardware install & on-site tuning
    ├─ Migration cut-over
    └─ Training, manual, hypercare
```

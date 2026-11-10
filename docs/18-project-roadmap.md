# 18 — Project Roadmap

Estimates assume **one full-stack engineer working with AI assistance plus a part-time owner/staff for decisions and testing.** A second engineer shortens Phases 4–6 by ~30%. All dates are relative to the approval date (Week 0). No fixed delivery date is promised until the open decisions D-01 to D-05 are closed.

| Phase | Weeks | Content | Exit criteria | Depends on |
|---|---|---|---|---|
| 1. Discovery & feasibility | W0 (done) + DaySchedule spike | Research, docs, decisions | Decisions approved; DISC-04 spike done | Owner input |
| 2. Backend foundation | W1 | Repo, Docker, FastAPI, MySQL, Alembic, auth/RBAC, packages, pricing engine, schedule config, CI | Pricing unit tests pass; admin can log in | Phase 1 |
| 3. Booking engine | W2–W3 | Slot grid, availability, holds, booking transaction, idempotency, cancel/reschedule, concurrency tests, enquiries | Concurrency suite green; API docs | Phase 2, D-01/D-02 |
| 4. Kiosk frontend (touch) | W3–W4 | Kiosk app, WS state sync, all screens, touch-only end-to-end booking | Playwright E2E touch booking passes | Phase 3 APIs |
| 5. Webcam integration | W4 | MediaPipe presence, idle/attract, reset | Presence test protocol passes on hardware | Phase 4, hardware |
| 6. Voice AI | W4–W6 | Bake-off, adapters, orchestrator, tools, barge-in, multilingual prompts | Eval targets met (doc 22) | Phase 3, 4 |
| 7. Notifications & admin | W5–W7 (parallel) | WhatsApp, admin dashboard, kiosk mgmt, analytics, AI cost, web booking page, (payments if D-03) | Admin acceptance by owner | Phase 3, Meta approval |
| 8. Production readiness | W7–W8 | Security review, load test, failure drills, deploy, migration cut-over, staff training, soft launch | Production checklist (doc 27) complete | All |

**Critical path:** decisions D-01/D-02 → booking engine → kiosk touch flow → voice integration → on-site tuning → launch.
**Range:** 6–8 weeks to soft launch. A further 2 weeks of hypercare follow with 1.1 features.

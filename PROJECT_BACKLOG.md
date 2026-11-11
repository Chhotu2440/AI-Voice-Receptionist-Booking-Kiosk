# Project Backlog (summary)

Full task list with descriptions, dependencies, estimates and acceptance criteria: [docs/21-task-backlog.md](docs/21-task-backlog.md).

| Status | Tasks |
|---|---|
| COMPLETED | DISC-01, DISC-02, PLAT-01, PLAT-04, CORE-01, CORE-02, CORE-03, CORE-04 (verified on MySQL 8.4 in CI) |
| IN_REVIEW | PLAT-02 (image builds and passes Trivy; compose stack not yet run on a host) |
| COMPLETED (Sprint 2) | DISC-05, PLAT-03, BOOK-01…07 (verified on MySQL 8.4 in CI) |
| COMPLETED (Sprint 3) | KIOSK-01…05 |
| COMPLETED (Sprint 4) | CAM-01…02, VOICE-01…06, INT-01 (live send waits on the Interakt key/template) |
| COMPLETED (Sprint 5) | ADMIN-01 (shell, login, role-based menus), ADMIN-02 (packages, occasions, pricing + price check, schedule, arena, booking rules, venue), ADMIN-03 bookings, enquiries, customers (export, correction, erasure), staff accounts, audit log viewer, ADMIN-04 kiosks + AI cost/budget, dashboard |
| IN_PROGRESS | KIOSK-06 (service-worker shell, watchdog remaining) |
| READY | DISC-06, KIOSK-06 |
| BLOCKED | DISC-03 (owner: DaySchedule account details), DISC-04 (API key) |
| BACKLOG | CORE-05 (TOTP), VOICE-07, INT-02…03, ADMIN-05 (web booking), retention job (24-month auto-anonymize), REL-01…08 |

**Next up:** KIOSK-06 resilience (offline shell, watchdog), CORE-05 2FA for owner/manager, voice bake-off round 2 with human speakers.

**MVP estimate:** ≈ 80 engineer-days. Sprint 1 used ≈ 8 of the 9.5 days planned for PLAT/CORE.

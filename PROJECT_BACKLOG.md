# Project Backlog (summary)

Full task list with descriptions, dependencies, estimates and acceptance criteria: [docs/21-task-backlog.md](docs/21-task-backlog.md).

| Status | Tasks |
|---|---|
| COMPLETED | DISC-01, DISC-02, PLAT-01, PLAT-04, CORE-01, CORE-02, CORE-03, CORE-04 (verified on MySQL 8.4 in CI) |
| IN_REVIEW | PLAT-02 (image builds and passes Trivy; compose stack not yet run on a host) |
| COMPLETED (Sprint 2) | DISC-05, PLAT-03, BOOK-01…07 (verified on MySQL 8.4 in CI) |
| COMPLETED (Sprint 3) | KIOSK-01…05 |
| IN_PROGRESS | KIOSK-06 (service-worker shell, watchdog remaining) |
| READY | DISC-06, CAM-01, VOICE-01 |
| BLOCKED | DISC-03 (owner: DaySchedule account details), DISC-04 (API key) |
| BACKLOG | CORE-05 (TOTP), CAM-01…02, VOICE-01…07, INT-01…03, ADMIN-01…05, REL-01…08 |

**Next up (Sprint 4):** CAM-01/02 presence detection → VOICE-01 provider bake-off → VOICE-02…05 voice agent on the same intents.

**MVP estimate:** ≈ 80 engineer-days. Sprint 1 used ≈ 8 of the 9.5 days planned for PLAT/CORE.

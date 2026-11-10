# Project Backlog (summary)

Full task list with descriptions, dependencies, estimates and acceptance criteria: [docs/21-task-backlog.md](docs/21-task-backlog.md).

| Status | Tasks |
|---|---|
| COMPLETED | DISC-01, DISC-02, PLAT-01, PLAT-04 |
| TESTING | CORE-01, CORE-02, CORE-03, CORE-04 (green on SQLite; awaiting the MySQL CI run) |
| IN_REVIEW | PLAT-02 (compose not yet run: no Docker locally), PLAT-03 (CI not yet run: no git remote) |
| READY | DISC-05, DISC-06 |
| BLOCKED | DISC-03 (owner: DaySchedule account details), DISC-04 (API key) |
| BACKLOG | CORE-05 (TOTP), BOOK-01…07, KIOSK-01…06, CAM-01…02, VOICE-01…07, INT-01…03, ADMIN-01…05, REL-01…08 |

**Next up (Sprint 2):** BOOK-01 slot generator (needs D-01/D-02) → BOOK-02 availability → BOOK-03 holds → BOOK-04 booking transaction → BOOK-05 concurrency suite (MySQL required).

**MVP estimate:** ≈ 80 engineer-days. Sprint 1 used ≈ 8 of the 9.5 days planned for PLAT/CORE.

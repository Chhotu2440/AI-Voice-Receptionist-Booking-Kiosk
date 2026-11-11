# Play Laser Tag — AI Voice Receptionist & Smart Booking Kiosk

A walk-up kiosk for Play Laser Tag (T-49, Hauz Khas Village, New Delhi). Customers can book by voice, by touch, or both, and every booking goes through an authoritative FastAPI booking engine.

**Current phase:** Phase 5, build. Backend, kiosk (touch + voice) and admin dashboard are working; see [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Apps

| Folder | What | Dev command | Port |
|---|---|---|---|
| `backend/` | FastAPI API, booking engine, voice gateway, worker | `.venv/Scripts/python -m uvicorn app.main:create_app --factory --reload --port 8011` | 8011 |
| `kiosk/` | Customer kiosk (touch + voice + presence) | `npm run dev` (set `KIOSK_BACKEND_URL` in `kiosk/.env.local`) | 5173 |
| `admin/` | Staff/owner dashboard | `npm run dev` (set `ADMIN_BACKEND_URL` in `admin/.env.local`) | 5175 |

Both frontends call the backend through the Vite dev proxy, so the browser sees one origin. API keys live only in `backend/.env` and never reach a browser.

## Where to start

| You want… | Read |
|---|---|
| Current status and what's next | [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| Decisions made and decisions awaiting approval | [PROJECT_DECISIONS.md](PROJECT_DECISIONS.md) |
| Risks | [PROJECT_RISKS.md](PROJECT_RISKS.md) |
| Task backlog | [PROJECT_BACKLOG.md](PROJECT_BACKLOG.md) |
| The full discovery report, as numbered docs | [docs/](docs/) |

## Documentation index

| # | Document | Covers (discovery report sections) |
|---|---|---|
| 01 | [Project charter](docs/01-project-charter.md) | Executive summary, scope, MVP |
| 02 | [Business requirements](docs/02-business-requirements.md) | Business understanding, website analysis, assumptions, open decisions |
| 03 | [Product requirements](docs/03-product-requirements.md) | Functional requirements, MVP scope, future enhancements |
| 04 | [Software requirements](docs/04-software-requirements.md) | Non-functional requirements |
| 05 | [Customer journey](docs/05-customer-journey.md) | Journey and state machine |
| 06 | [System architecture](docs/06-system-architecture.md) | Backend, frontend, voice service, concurrency |
| 07 | [Architecture decisions](docs/07-architecture-decisions.md) | ADRs |
| 08 | [Database design](docs/08-database-design.md) | Schema proposal |
| 09 | [API specification](docs/09-api-specification.md) | REST and WebSocket contracts |
| 10 | [AI agent design](docs/10-ai-agent-design.md) | Tools, prompts, guardrails |
| 11 | [Voice provider comparison](docs/11-voice-provider-comparison.md) | Provider research |
| 12 | [Cost analysis](docs/12-cost-analysis.md) | AI and operating costs |
| 13 | [Booking integration](docs/13-booking-integration.md) | DaySchedule feasibility |
| 14 | [UI/UX specification](docs/14-ui-ux-specification.md) | Kiosk screens |
| 15 | [Hardware recommendations](docs/15-hardware-recommendations.md) | Webcam and kiosk hardware |
| 16 | [Security and privacy](docs/16-security-privacy.md) | Security, DPDP |
| 17 | [Risk register](docs/17-risk-register.md) | Risks |
| 18 | [Project roadmap](docs/18-project-roadmap.md) | Phases |
| 19 | [Work breakdown structure](docs/19-work-breakdown-structure.md) | WBS |
| 20 | [Sprint plan](docs/20-sprint-plan.md) | Sprints |
| 21 | [Task backlog](docs/21-task-backlog.md) | Detailed tasks |
| 22 | [QA strategy](docs/22-qa-strategy.md) | Testing |
| 23 | [Deployment guide](docs/23-deployment-guide.md) | Infrastructure |
| 24 | [Monitoring runbook](docs/24-monitoring-runbook.md) | Operations |
| 25 | [Disaster recovery](docs/25-disaster-recovery.md) | Backups and recovery |
| 26 | [User manual](docs/26-user-manual.md) | Staff and admin manual (draft) |
| 27 | [Production checklist](docs/27-production-checklist.md) | Acceptance criteria |

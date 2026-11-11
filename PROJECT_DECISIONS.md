# Project Decisions

Full rationale: [docs/07-architecture-decisions.md](docs/07-architecture-decisions.md).

## Technical decisions (made by CTO; proposed, require your approval only where marked ★)

| ID | Decision | Status |
|---|---|---|
| ADR-001 | FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic, Python 3.12 | Accepted (mandated) |
| ADR-002 | MySQL 8.4 authoritative; Redis auxiliary only | Accepted (mandated) |
| ADR-003 ★ | **Custom booking engine is the single source of truth; DaySchedule retired after migration**, pending 1-day API spike | **Accepted 2026-11-10** (spike DISC-04 may reopen) |
| ADR-004 | Modular monolith, 3 processes (api / voice-gateway / worker) | **Accepted 2026-11-10** |
| ADR-005 | Voice audio relayed through backend (no provider keys or protocols in browser) | **Accepted 2026-11-10** |
| ADR-006 | Async SQLAlchemy + asyncmy | **Accepted 2026-11-10** |
| ADR-007 ★ | Voice provider chosen by measured bake-off; primary candidate OpenAI `gpt-realtime-2.1-mini`, challenger Gemini 3.8 Live, fallback cascaded Sarvam | **Accepted 2026-11-10**. **Update 2026-11-11:** after bake-off round 1 (docs/11 §5), **Gemini `gemini-3.8-live` is the default** for round 2 (owner's choice). OpenAI stays as a switchable fallback via `VOICE_PROVIDER`. Final choice after round 2 with human speakers. |
| ADR-008 | ARQ for background jobs | **Accepted 2026-11-10** |
| ADR-009 | MediaPipe face *detection* in browser; no recognition | **Accepted 2026-11-10** |
| ADR-010 | JWT + RBAC for admin; device credentials for kiosks | **Accepted 2026-11-10** |
| ADR-011 ★ | Single Mumbai-region VPS/Lightsail with Docker Compose (~₹2.5–5k/month) | **Accepted 2026-11-10** |
| ADR-012 | Payments feature-flagged; default pay at reception | Proposed — depends on D-03 |
| ADR-013 | WhatsApp Cloud API direct, utility templates | **Accepted 2026-11-10** |
| ADR-014 | UTC storage, IST business dates | Accepted |

## Open business decisions

| ID | Question | Why it matters | Default if unanswered |
|---|---|---|---|
| D-01 | ~~Is a booked slot exclusive to one group?~~ **DECIDED 2026-11-10: exclusive per group** (one booking takes the whole arena for its game time + buffer) | Core capacity model | — |
| D-02 | ~~Max players, hours, interval, buffer~~ **DECIDED 2026-11-10: max 20 players per game, open 11:00–22:00 daily, starts every 30 min, 10 min changeover buffer**. Minimum per booking stays 1 (assumption) | Slot generator & guest limits | — |
| D-03 | Payment: pay at reception / deposit / full online? | Payment scope | Pay at reception |
| D-04 | Replace DaySchedule with our web booking page (single calendar)? Share DaySchedule plan + API key for the spike | Integration path | Yes, after spike |
| D-05 | Are listed prices GST-inclusive? GSTIN? Tax shown on summary? | Pricing display | Inclusive |
| D-06 | WhatsApp: which number, who owns the Meta Business account, staff alert number | Notifications timeline | Start Meta verification now |
| D-07 | Confirmation rule: must the final "Confirm" be a **tap** (recommended), or is a spoken "yes" enough? | Safety vs convenience | Spoken yes + tap |
| D-08 | Hardware budget tier (₹55–75k budget vs ₹1.4–2.2 lakh premium, est.) | Purchase | Budget pilot |
| D-09 | Privacy notice review by counsel; data retention period (default 24 months) | DPDP compliance | 24 months; counsel review before go-live |
| D-10 | Large-group threshold and which occasions always go to staff | Routing | > 20 guests; Corporate & School always enquiry |
| D-11 | Are paintball / zorbing / bull ride offered at this venue and bookable? | Scope | Out of scope |
| D-12 | Is "weekend" Fri–Sun (as on website) or Sat–Sun? | Pricing | Fri–Sun |
| D-13 | Assistant name/persona (e.g. "Zara") and voice gender preference | Branding | "Zara", provider default voice |

## Repository decisions

| ID | Decision | Date | Implications |
|---|---|---|---|
| D-REPO-01 | GitHub repository `Chhotu2440/AI-Voice-Receptionist-Booking-Kiosk` stays **public** (owner's decision) | 2026-11-10 | Docs, pricing notes and business assumptions are publicly readable. Secrets must never be committed: use `.env` (git-ignored) and GitHub Actions secrets only. CI logs are visible only to signed-in users. Real customer data and production configuration never go in the repo. |

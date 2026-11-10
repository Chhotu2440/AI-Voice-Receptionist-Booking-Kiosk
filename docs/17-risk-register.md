# 17 — Risk Register

Scoring: Probability (P) and Impact (I) are each rated 1–5. Score = P×I. **≥ 15 = High**.

| ID | Risk | P | I | Score | Mitigation | Owner | Status |
|---|---|---|---|---|---|---|---|
| R-01 | Hindi/Hinglish recognition (esp. phone numbers, names) below acceptable accuracy in a noisy reception | 4 | 5 | **20** | Bake-off on real hardware, speakerphone with AEC, mandatory read-back, touch keypad fallback, cascaded Sarvam fallback adapter | Voice lead | Open |
| R-02 | Business rules unknown (capacity, exclusivity, hours) cause rework of the booking engine | 4 | 4 | **16** | Open decisions D-01/D-02 before Phase 3; `capacity_mode` supports both models | PM | Open |
| R-03 | Double calendar during DaySchedule migration → oversell | 3 | 5 | **15** | Write-freeze cut-over, import + reconciliation, rollback plan | PM | Open |
| R-04 | AI invents prices/features or confirms without a booking | 2 | 5 | 10 | Tool-only facts, state machine guard, regression eval with invented-fact rate = 0 | Voice lead | Open |
| R-05 | AI cost overrun (long sessions, chatty users, price changes) | 3 | 3 | 9 | Session cap, context truncation, spend alerts, auto touch-only at cap | PM | Open |
| R-06 | WhatsApp template approval / Meta Business verification delay | 3 | 3 | 9 | Start Meta setup in week 1. SMS fallback; on-screen QR as booking proof | Owner | Open |
| R-07 | Latency of backend relay exceeds target | 2 | 4 | 8 | Mumbai hosting; measure in bake-off; ADR-005b direct WebRTC fallback | Voice lead | Open |
| R-08 | Provider outage or model deprecation | 3 | 3 | 9 | Provider abstraction, second adapter, touch-only mode | Backend lead | Open |
| R-09 | Venue internet outage | 3 | 4 | 12 | 4G failover router; offline screen with "Please see reception" | Owner/Ops | Open |
| R-10 | Presence false triggers (walk-pasts) annoy staff/customers | 3 | 2 | 6 | Dwell + size + frontal thresholds, tunable; quiet greeting volume | Frontend | Open |
| R-11 | DPDP non-compliance (consent, children, cross-border) | 2 | 4 | 8 | Privacy-by-design, separate consents, counsel review (D-09) | Owner/PM | Open |
| R-12 | Kiosk PII leak to next customer | 2 | 5 | 10 | In-memory state only, reset on every end path, E2E test for reset | Frontend | Open |
| R-13 | Payment scope unclear → late build | 3 | 3 | 9 | Default pay-at-venue in MVP; Razorpay in R1.1 behind a flag | PM | Open |
| R-14 | Hardware lead time / wrong spec | 2 | 3 | 6 | Order in Sprint 1 after quotes; dev on a laptop + USB speakerphone meanwhile | Owner | Open |
| R-15 | Single VPS failure | 2 | 4 | 8 | Snapshots + off-site DB backups, documented restore (RTO 2 h), uptime monitoring | Ops | Open |
| R-16 | Staff adoption of new admin (vs DaySchedule habits) | 3 | 3 | 9 | Training session, user manual, simple daily-bookings view | PM | Open |

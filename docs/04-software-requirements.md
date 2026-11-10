# 04 — Software Requirements (Non-functional)

| ID | Category | Requirement | Target / verification |
|---|---|---|---|
| NFR-01 | Latency | Voice time-to-first-audio after the end of user speech | p50 ≤ 1.2 s, p95 ≤ 2.0 s (measured in the bake-off) |
| NFR-02 | Latency | Barge-in: AI audio stops after the user starts speaking | ≤ 300 ms (local playback flush) |
| NFR-03 | Latency | Availability API | p95 ≤ 300 ms at 10 rps |
| NFR-04 | Correctness | Capacity never exceeded | Concurrency test suite: 50 parallel bookings on a slot of capacity N, so exactly the eligible ones succeed |
| NFR-05 | Correctness | Idempotent booking creation | Same `Idempotency-Key` returns the same booking and no duplicate row |
| NFR-06 | Availability | Kiosk usable during business hours | ≥ 99%. Touch-only mode works when the AI provider is down |
| NFR-07 | Recovery | Kiosk browser crash or restart | Back to a clean idle state in ≤ 60 s. No PII restored |
| NFR-08 | Recovery | Server RPO / RTO | RPO ≤ 15 min (binlog + nightly full), RTO ≤ 2 h |
| NFR-09 | Security | Secrets | Never in the frontend bundle or repo. Provider keys stay server-side. Kiosk uses a device credential |
| NFR-10 | Security | Admin auth | Argon2id passwords, short-lived JWT access (15 min) + rotating refresh, optional TOTP for owner |
| NFR-11 | Privacy | Camera | Frames processed in memory on the kiosk only. Nothing stored or transmitted |
| NFR-12 | Privacy | Data retention | Configurable. Default: customer PII purged 24 months after last booking, AI transcripts 30 days (if enabled) |
| NFR-13 | Usability | Touch targets | ≥ 64 px, body text ≥ 24 px at 1080p, contrast ≥ 4.5:1 |
| NFR-14 | Maintainability | Test coverage | ≥ 85% on services (pricing, availability, holds, booking) |
| NFR-15 | Observability | Structured JSON logs, request IDs, health/readiness endpoints, error alerts | — |
| NFR-16 | Cost | AI spend alert thresholds | Configurable daily and monthly caps. A hard cap switches the kiosk to touch-only mode |
| NFR-17 | Timezone | All timestamps stored UTC (`DATETIME(6)`). Business dates and times are computed in Asia/Kolkata | Unit tests around the midnight boundary |
| NFR-18 | Compatibility | Kiosk runs Chromium/Chrome in kiosk mode on Windows 11 or Ubuntu 24.04 LTS | — |
| NFR-19 | Scalability | Designed for 1 kiosk + web traffic, and supports up to 10 kiosks without re-architecture | Load test at 10× expected load |

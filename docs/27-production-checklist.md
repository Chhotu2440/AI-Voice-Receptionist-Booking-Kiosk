# 27 — Production Acceptance Checklist

A release is production-ready only when every item is checked and links to evidence (test run, screenshot or sign-off).

## Functional
- [ ] Complete **voice** booking works (EN, HI, Hinglish), on-site eval targets met (doc 22 §3)
- [ ] Complete **touch-only** booking works (E2E-001)
- [ ] Voice and screen stay synchronized (state version tests; mixed-mode E2E)
- [ ] Packages, prices, schedule fully configurable in admin (owner sign-off)
- [ ] Pricing is backend-only; snapshot stored (PRC-*)
- [ ] Availability authoritative; capacity cannot be exceeded (CONC-* green, 1,000 randomized runs)
- [ ] Slot holds create/expire/release correctly (CONC-002, CONC-005)
- [ ] Booking success shown only after backend CONFIRMED (SM-001, AI-005)
- [ ] Custom event enquiries reach staff
- [ ] WhatsApp confirmations delivered with status tracking; retry works (NOT-001)
- [ ] Payment flow verified via webhook (only if enabled)
- [ ] Web booking page live on the same engine; DaySchedule frozen (single calendar)

## Non-functional
- [ ] Latency targets met on venue network (NFR-01/02)
- [ ] Load test passed at 10× expected load
- [ ] Failure drills passed: provider outage, internet loss, browser crash, OS restart, backend restart, DB restore
- [ ] Kiosk reboot → idle in ≤ 60 s with no PII

## Security & privacy
- [ ] No secrets in repo/bundles (scan); keys rotated for prod
- [ ] Security review complete; no open High findings
- [ ] Privacy notice (EN/HI) reviewed by counsel; consents recorded separately
- [ ] Camera: detection only, no frames stored/transmitted (code review sign-off)
- [ ] Retention jobs configured; erasure workflow tested

## Operations
- [ ] Monitoring and alerts active and tested
- [ ] Backups running; restore drill completed within RTO
- [ ] Runbook and DR docs reviewed
- [ ] Hardware installed, calibrated, UPS tested
- [ ] Staff trained; manual delivered
- [ ] Owner sign-off

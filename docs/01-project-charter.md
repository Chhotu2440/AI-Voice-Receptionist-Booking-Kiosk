# 01 — Project Charter

**Project:** Play Laser Tag — AI Voice Receptionist & Smart Booking Kiosk
**Status:** Discovery complete. Awaiting approval of the decisions in [PROJECT_DECISIONS.md](../PROJECT_DECISIONS.md).
**Date:** 2026-11-10
**Owner roles:** CTO / Technical PM (Claude, acting), Business Owner (Play Laser Tag)

## 1. Executive summary

Play Laser Tag runs an indoor laser tag arena in Hauz Khas Village, New Delhi. Its website lists three per-player packages (Beginner, Intermediate and Expert) and offers custom pricing for birthdays, corporate events and school groups. Customers currently book through a hosted DaySchedule page.

We will install a kiosk at reception. A customer can walk up and complete a booking by talking to a friendly AI receptionist in English, Hindi or Hinglish, by using the touchscreen, or by mixing the two. Large or custom events are routed to staff as enquiries.

**Headline recommendations** (rationale in [07-architecture-decisions.md](07-architecture-decisions.md)):

1. **Booking engine: build a custom FastAPI engine as the single source of truth (Option B)**, subject to a one-day DaySchedule API spike once we have an API key. DaySchedule's public docs describe group capacity as "seats per slot", with everyone who books a slot joining one shared booking. Its public documentation also describes no temporary holds, no capacity-aware guest-count reservation and no rate limits. Our requirements depend on all of these. To avoid running two calendars, the website's "BOOK NOW" button will point to a web booking page served by the same engine, and DaySchedule will be retired after a short migration.
2. **Voice: use a speech-to-speech realtime model behind a provider abstraction, relayed through our backend.** The primary candidate is **OpenAI `gpt-realtime-2.1-mini`**, the cheapest of the measured options at about $0.03 for a 2-minute session (estimate). **Gemini 3.8 Live** is the challenger. The final choice will be made by a measured bake-off on the actual hardware, not by marketing claims. A cascaded pipeline (Sarvam STT/TTS plus a small LLM) is the documented fallback if Hindi/Hinglish accuracy from realtime models disappoints.
3. **Backend: one FastAPI codebase run as two processes**, `api` (REST and admin) and `voice-gateway` (WebSocket audio relay, AI tool execution). Supporting services: MySQL 8 (authoritative), Redis (holds cache, rate limits, pub/sub) and ARQ (background jobs). No microservices beyond this in v1.
4. **Hosting:** a single VPS or Lightsail instance in Mumbai (ap-south-1 or equivalent), running Docker Compose with Nginx and managed backups. Expected cost is about ₹2.5k–5k/month. We are designing for one kiosk now, with device management that allows more later.
5. **Presence detection** runs in the browser with MediaPipe (on-device), using face *detection* only and never recognition. No frames leave the kiosk.
6. **Budget estimate:** about 5–8 weeks of focused engineering for the MVP. This depends on the open business decisions and on hardware and credential lead times (WhatsApp template approval, Razorpay KYC).

## 2. Objectives and success metrics

| Objective | Metric (target, to be confirmed with business) |
|---|---|
| Customers can self-book at the kiosk | ≥ 60% of started sessions that reach package selection end in a confirmed booking |
| Natural voice experience | Median time-to-first-audio ≤ 1.2 s; barge-in stop ≤ 300 ms |
| No oversold slots | 0 capacity violations (enforced by DB constraint and tests) |
| Accurate pricing | 100% of totals come from the pricing service; snapshot stored |
| Low running cost | AI cost ≤ ₹15 per completed booking (estimate to validate) |
| Reliability | Kiosk available ≥ 99% of business hours; touch fallback always works |

## 3. Scope

**In scope (MVP):** kiosk app (voice and touch), booking engine, pricing engine, holds, admin dashboard (packages, pricing, schedule, bookings, kiosks, AI settings, basic analytics), WhatsApp confirmation, custom event enquiries, staff assistance, presence detection, deployment, monitoring, documentation.

**In scope, conditional on business decisions:** online payment through Razorpay (deposit or full payment), and a public web booking page that replaces DaySchedule.

**Out of scope (v1):** facial recognition or any biometrics, loyalty programme, multi-location, a native mobile app, and booking of the other activities listed on the website (paintball, zorbing, rodeo bull) until the business confirms they are offered at this venue.

## 4. Stakeholders

| Role | Responsibility |
|---|---|
| Business owner | Business rules, pricing, approvals, credentials (Meta, Razorpay, DaySchedule) |
| Front-desk staff | Staff assistance, manual bookings, kiosk daily checks |
| Technical PM / CTO | Plan, architecture, delivery, QA |
| Engineers (backend, frontend, voice) | Implementation |

## 5. Constraints

- FastAPI, MySQL 8 and Redis are mandatory. React, TypeScript, Vite and Tailwind are mandatory on the frontend.
- Business-facing times use Asia/Kolkata.
- Privacy: no facial identification, no recording without consent, and compliance with the DPDP Act and Rules.
- One kiosk at launch.

## 6. MVP definition

See [03-product-requirements.md §MVP](03-product-requirements.md#4-recommended-mvp-scope).

# 13 — Booking Integration & DaySchedule Feasibility

## 1. What we could verify (public docs, 2026-11-10)

| # | Question | Finding | Status |
|---|---|---|---|
| 1 | API access enabled? | REST API exists (`https://api.dayschedule.com/v1/...`). **Requires a paid plan.** Free plan shows "Upgrade to Access API Keys" | Account plan **unknown**: need owner |
| 2 | Services/resources configured correctly? | Public booking page renders client-side; content not readable without a browser session | **Unverified**: need admin screenshot/access |
| 3 | Package durations? | Resources (event types) have durations; three resources would map to three packages | Likely yes |
| 4 | Group capacity? | Group events: "seats per slot" (default 10); full slots hidden. Premium resource type | Yes, as *shared seats* |
| 5 | Guest count stored? | "Allow Guests" adds guests to an invitee; custom form fields supported. Not documented whether 1 booking can consume N seats via API | **Unclear** |
| 6 | Availability via API? | `GET /v1/availability/:id` listed | Yes (response shape unverified) |
| 7 | Booking creation? | `POST /v1/bookings` | Yes |
| 8 | Webhooks? | Via Workflows ("send booking data to your endpoint") | Yes (event types and signature verification undocumented) |
| 9 | Cancel/reschedule? | `PATCH /v1/bookings/:id/cancel`, `/reschedule` | Yes |
| 10 | Weekday/weekend pricing? | Payment amount per event type. No documented day-type pricing | **Probably no** (we'd price ourselves anyway) |
| 11 | Multiple resources? | Resources are first-class. Cross-resource shared capacity (one arena used by 3 package types with different durations) not documented | **Gap**: 3 event types won't block each other unless configured on a shared calendar/assignee |
| 12 | Website + kiosk share availability? | Yes, if both book through DaySchedule | Yes |
| 13 | Can simultaneous bookings exceed capacity? | Not documented; no transactional guarantee exposed | **Unknown, a risk** |
| 14 | Temporary holds? | **Not documented** | **No** (assume) |

Auth documentation is inconsistent (Bearer header vs `apiKey` query parameter), and no rate limits are documented.

## 2. Options

| | A: DaySchedule = source of truth | B: Custom engine = source of truth (**recommended**) |
|---|---|---|
| Holds | We'd have to fake holds in Redis, and DaySchedule could still sell the slot on the website meanwhile → **oversell window** | Native, transactional |
| Group capacity across 30/45/60-min packages | Hard: three event types must block one arena | Native (grid cells + buffer) |
| Pricing snapshot & weekday/weekend | Ours anyway | Ours |
| AI tool latency | +1 external hop per availability call, unknown rate limits | Local DB |
| Dependency | DaySchedule uptime and plan | None |
| Dev effort | Lower for the calendar, higher for the workarounds | +4–6 days (engine) + 3–4 days (web booking page) |
| Staff UX | Existing DaySchedule dashboard | New admin dashboard (being built anyway) |

## 3. Recommendation
**Option B.** The requirements that matter most (no oversell, holds, group capacity, accurate pricing) are exactly the ones DaySchedule does not document. Option A would need a second, unsynchronized lock layer on top of a system we can't lock, and that is how double-bookings happen.

**Confirmation spike (DISC-04, 1 day, needs API key):** if DaySchedule demonstrates (1) atomic multi-seat booking that rejects over-capacity, (2) shared capacity across the three event types, and (3) signed webhooks, then Option A becomes viable for v1 and we will re-present the decision.

## 4. Migration plan (single calendar at every moment)
1. Build the engine and web booking page; staff begin using the admin dashboard in staging.
2. **Cut-over day (low-traffic morning):**
   a. Disable new bookings in DaySchedule (set the booking page to unavailable, or remove availability).
   b. Export all future DaySchedule bookings (API `GET /v1/bookings` or CSV) and import them into our engine as CONFIRMED with `channel=LEGACY_DAYSCHEDULE`. Run a reconciliation report (counts, per-slot totals).
   c. Switch the website BOOK NOW links (homepage, /party, /pricing) to `book.playlasertag.in` (our page).
   d. Keep DaySchedule read-only for 30 days for reference, then cancel the plan.
3. **Rollback (cut-over):** if a critical defect is found within 48 h, re-enable DaySchedule and manually enter engine bookings made in the interim (expected to be few). Write-freeze steps are rehearsed in staging.

## 5. WhatsApp & payment strategy

### WhatsApp (Meta WhatsApp Business Cloud API, direct)
- **Setup (owner, start in week 1):** Meta Business verification, a dedicated phone number (it can't be used simultaneously in the WhatsApp Business app unless coexistence is supported for that number; verify), and a permanent system-user token stored server-side.
- **Templates (utility category, EN + HI):** `booking_confirmation` (ref, name, package, guests, date/time, total, payment status, venue map link), `booking_cancelled`, `booking_rescheduled`, `staff_alert` (to the staff number), `enquiry_received`.
- **Flow:** booking CONFIRMED + WhatsApp consent → ARQ job → POST `/{phone-number-id}/messages` → store `provider_message_id`, status SENT. The webhook updates DELIVERED/READ/FAILED. **Acceptance by the API is not delivery.** The kiosk says "We're sending your confirmation on WhatsApp", never "sent".
- **Retries:** exponential backoff (1, 5, 15 min, max 4) for retryable errors. Permanent failures (invalid number, not on WhatsApp) → optional SMS fallback (needs DLT template registration) → admin flag.
- **Cost:** per delivered utility template (doc 12).

### Payments (decision D-03 pending)
| Mode | Flow | Booking status |
|---|---|---|
| A. Pay at reception (**MVP default**) | No online payment | CONFIRMED, payment PENDING → staff marks PAID (cash/UPI) |
| B. Deposit | Razorpay Payment Link/QR on kiosk screen and in WhatsApp; deposit % configurable | PENDING_PAYMENT with payment hold TTL (e.g. 10 min) → CONFIRMED on verified webhook; auto-release on timeout |
| C. Full online | Same as B with 100% | Same |
| D. Desk UPI QR | Static/dynamic QR at the desk, staff verify | As A |

Rules: only the **verified webhook** (`payment.captured`, signature checked, deduped) marks a payment captured. A frontend "success" is never trusted. Refunds are admin-initiated through the API and audited. Razorpay is preferred for India (UPI, cards, payment links, QR, good docs). Cashfree and PhonePe PG are alternatives behind the same `PaymentGateway` interface.

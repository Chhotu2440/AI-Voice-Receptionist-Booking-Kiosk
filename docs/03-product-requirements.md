# 03 — Product Requirements

## 1. Personas

- **Walk-in customer:** often a group of friends aged 16–30. Wants to play now or later today and speaks Hinglish.
- **Parent planning a birthday:** asks about kids, party options and price. May need staff.
- **Corporate/school coordinator:** large group with custom needs. Always routed to an enquiry.
- **Front-desk staff:** takes over sessions, makes manual bookings, checks the kiosk.
- **Owner/admin:** edits packages, prices and schedule, and reviews revenue and AI cost.

## 2. Functional requirements

### Kiosk (customer-facing)

| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-K01 | Presence-triggered start | A person facing the screen within about 1.5 m for at least 1.5 s starts a session. Walk-pasts (dwell under 1.5 s or face not frontal) do not. A manual "Tap to start" button always works. |
| FR-K02 | Name capture | The name is shown on screen. It can be corrected by voice or with an on-screen keyboard (letters only, no physical keyboard). |
| FR-K03 | Phone capture | Indian mobile number: 10 digits starting 6–9, with an optional +91/0 prefix stripped. Accepts digit-by-digit and grouped speech in English or Hindi ("double five", "nau", "saat"). The number is read back for confirmation. A touch keypad is available for correction. Stored as E.164. |
| FR-K04 | Guest count | Quick-pick chips: 1, 2, 3, 4, 5, 6, 8, 10, 12, More. Any integer is accepted by voice. Counts are validated against package min/max and the large-group threshold. |
| FR-K05 | Occasion | Six options. Occasion-specific optional fields. Corporate, school, or a count over the threshold → enquiry flow. |
| FR-K06 | Package discovery | Cards are loaded from the API, with a per-person price for the selected date type and an estimated total from the pricing service. The AI recommends a package only using catalogue data. |
| FR-K07 | Date selection | Calendar with today, tomorrow and next available. Disabled dates come from the API (holidays, blackouts, booking window). |
| FR-K08 | Slot availability | Only slots that can fit the guest count are shown. When none fit, the next 3 alternatives are offered. |
| FR-K09 | Slot hold | A hold is created on selection. A countdown is visible. The hold TTL is configurable (default 5 min). |
| FR-K10 | Summary & consent | Full breakdown from the pricing service. Explicit confirm by tap or by a clear spoken yes followed by a tap on "Confirm" (decision D-07). WhatsApp consent checkbox, unticked by default. |
| FR-K11 | Confirmation | Shown only after the backend returns `CONFIRMED`. Displays the booking ID and a QR code for the booking reference. |
| FR-K12 | Reset | After a configurable delay (default 20 s on success, 60 s of inactivity elsewhere) all PII is wiped and the kiosk returns to idle. |
| FR-K13 | Edit anything | The customer can go back to any completed step. Dependent values are revalidated (price, eligibility, hold). |
| FR-K14 | Staff assistance | A "Call staff" button and a voice intent alert staff (admin dashboard and WhatsApp to the staff number). |
| FR-K15 | Touch-only mode | The complete journey works with voice disabled or failed. |
| FR-K16 | Language | EN/HI/Hinglish auto-follow. A UI language toggle (EN/हिंदी) is available. |

### Backend & admin

| ID | Requirement |
|---|---|
| FR-B01 | Package CRUD with features, durations, min/max guests, and active flag |
| FR-B02 | Pricing rules: weekday/weekend (configurable day sets), date-specific, holiday, promo; tax; extra charges |
| FR-B03 | Schedule: business hours per weekday, special hours, holidays, blackouts, manual blocks |
| FR-B04 | Slot generation and availability by package, date and guest count |
| FR-B05 | Holds with TTL, release and expiry job |
| FR-B06 | Atomic, idempotent booking creation; cancel; reschedule |
| FR-B07 | Custom event enquiries with status workflow |
| FR-B08 | WhatsApp notifications with delivery tracking |
| FR-B09 | Payments (feature-flagged) with verified webhooks |
| FR-B10 | Kiosk registration, heartbeat, remote config, status |
| FR-B11 | AI config, usage logging per session, spend alerts |
| FR-B12 | RBAC (owner, manager, staff, viewer), audit logs |
| FR-B13 | Analytics: bookings, revenue, conversion funnel, AI cost per booking |

## 3. Non-goals

- Facial recognition, emotion or demographic inference
- Storing raw audio or video (optional transcript storage only with consent; see doc 16)
- AI free-form discounts or price negotiation

## 4. Recommended MVP scope

**MVP (release 1.0):**
- Touch and voice booking for the three standard packages, pay at reception
- Custom event enquiry capture (no automated quoting)
- Presence detection with manual start
- Admin: packages, pricing rules, schedule/holidays/blocks, bookings (search, view, create, cancel, reschedule), enquiries, kiosk status, AI settings, usage and cost dashboard
- WhatsApp booking confirmation (one approved utility template), with SMS as an optional fallback
- Public web booking page on the same engine (if D-03 is approved), replacing DaySchedule
- Monitoring, backups, runbook

**Release 1.1 (post-launch, 2–4 weeks):** Razorpay deposit/full payment via QR on the kiosk, cancellation and reschedule via WhatsApp link, richer analytics, and a second voice provider adapter if it was not already done in the bake-off.

## 5. Future enhancements

Loyalty/repeat-customer recognition by phone number (not by face), multi-arena or multi-location support, birthday package catalogue with add-ons (cake, decor), automated quotes for corporate events, Google review prompt after the visit, waitlist for full slots, digital waiver/consent forms (especially for minors), staff mobile app, upsell recommendations, and a multilingual voice persona (e.g. Punjabi).

# 05 — Customer Journey & Conversation State Machine

## 1. Journey (happy path)

| # | State | Screen | Assistant (EN example) | Data captured |
|---|---|---|---|---|
| 1 | IDLE → CUSTOMER_DETECTED | Attract loop, "Tap to start" | — | — |
| 2 | GREETING | "Welcome to Play Laser Tag!" with an animated avatar | "Hey there! Welcome to Play Laser Tag. Ready for an exciting experience?" | — |
| 3 | CUSTOMER_NAME | Name field + mic indicator | "First, what should I call you?" | name |
| 4 | CUSTOMER_PHONE | Keypad + number readout | "What's the best mobile number to reach you?" | phone (E.164) |
| 5 | GUEST_COUNT | Chips 1…12, More | "How many people will be joining the game?" | guest_count |
| 6 | OCCASION | 6 option tiles | "Are you visiting for fun, or are we celebrating something special?" | occasion (+ optional details) |
| 7 | PACKAGE_DISCOVERY | Package cards | Short comparison + recommendation | — |
| 8 | PACKAGE_SELECTED | Selected card highlighted | Confirms | package_id |
| 9 | DATE_SELECTION | Calendar | "When would you like to play?" | date |
| 10 | AVAILABILITY_CHECK → SLOT_SELECTION | Slot grid | Reads 2–3 options | slot |
| 11 | SLOT_HOLD | Countdown timer | — | hold_id |
| 12 | BOOKING_SUMMARY → CUSTOMER_CONFIRMATION | Summary + Confirm + WhatsApp consent | Concise summary | consent flags |
| 13 | BOOKING_CREATION → BOOKING_CONFIRMED | Success animation, booking ID, QR | "Wonderful! Your booking is confirmed…" | booking_id |
| 14 | SESSION_COMPLETE → IDLE | Thank-you, wipe | — | — |

Branches:
- **Custom event:** OCCASION → CUSTOM_EVENT_DETAILS → enquiry created → SESSION_COMPLETE ("Our team will WhatsApp/call you within X hours").
- **Payment (if enabled):** BOOKING_CONFIRMED → PAYMENT_PENDING → PAYMENT_CONFIRMED. With pay-at-reception, PAYMENT_PENDING is shown as "Pay at reception" and the session completes.
- **Staff:** any state → STAFF_ASSISTANCE.
- **Errors:** any state → ERROR_RECOVERY → the previous safe state, or STAFF_ASSISTANCE.
- **Cancel/leave:** any state → SESSION_CANCELLED → release hold → IDLE.

## 2. State machine

The state machine lives **in the backend** (`app/ai/state_machine/`). Touch events and AI tool calls both submit *intents*. The backend validates each intent against the current state and the required data, then broadcasts the new canonical state over WebSocket. The frontend renders state and never decides it.

### Transition table

| From | Allowed to | Guard (required fields / validation) |
|---|---|---|
| IDLE | CUSTOMER_DETECTED | presence event or manual tap |
| CUSTOMER_DETECTED | GREETING, IDLE | — (IDLE if the person leaves within 5 s) |
| GREETING | CUSTOMER_NAME | — |
| CUSTOMER_NAME | CUSTOMER_PHONE | name: 1–60 chars, letters/spaces/.'- (Devanagari allowed) |
| CUSTOMER_PHONE | GUEST_COUNT | phone matches `^[6-9]\d{9}$` after normalization, and the customer has confirmed it |
| GUEST_COUNT | OCCASION | 1 ≤ guests ≤ venue max |
| OCCASION | PACKAGE_DISCOVERY, CUSTOM_EVENT_DETAILS | occasion set. Route to CUSTOM_EVENT_DETAILS if the occasion is in `always_enquiry` or guests > threshold |
| CUSTOM_EVENT_DETAILS | SESSION_COMPLETE, PACKAGE_DISCOVERY | enquiry created, or the customer chooses a standard package instead (only when eligible) |
| PACKAGE_DISCOVERY | PACKAGE_SELECTED | — |
| PACKAGE_SELECTED | DATE_SELECTION | the package is active and guests fall within its min/max |
| DATE_SELECTION | AVAILABILITY_CHECK | date is inside the booking window and is not a holiday/blackout |
| AVAILABILITY_CHECK | SLOT_SELECTION, DATE_SELECTION | slots returned (DATE_SELECTION with alternatives if none) |
| SLOT_SELECTION | SLOT_HOLD | slot still available for guests |
| SLOT_HOLD | BOOKING_SUMMARY, SLOT_SELECTION | hold ACTIVE (SLOT_SELECTION if the hold failed) |
| BOOKING_SUMMARY | CUSTOMER_CONFIRMATION | price quote computed and stored in session |
| CUSTOMER_CONFIRMATION | BOOKING_CREATION | explicit confirm event **from touch** (or voice yes + touch, see D-07) and hold not expired |
| BOOKING_CREATION | BOOKING_CONFIRMED, ERROR_RECOVERY | backend booking status CONFIRMED |
| BOOKING_CONFIRMED | PAYMENT_PENDING, SESSION_COMPLETE | payment mode |
| PAYMENT_PENDING | PAYMENT_CONFIRMED, SESSION_COMPLETE | verified webhook / pay-at-desk |
| PAYMENT_CONFIRMED | SESSION_COMPLETE | — |
| SESSION_COMPLETE | IDLE | after the reset delay |
| * | STAFF_ASSISTANCE, SESSION_CANCELLED, ERROR_RECOVERY | — |
| STAFF_ASSISTANCE | any prior state (staff resumes), IDLE | staff PIN action |
| ERROR_RECOVERY | last stable state, STAFF_ASSISTANCE, IDLE | — |

**Backward edits:** from any state after X, an `edit_field` intent jumps back to X's state. The backend then invalidates dependents:

| Changed field | Invalidates |
|---|---|
| guest_count | package eligibility, price quote, slot (re-check capacity; hold is re-sized or released) |
| occasion | enquiry routing, recommendation |
| package_id | date's slot list, slot, hold, price |
| date | slot, hold, price (weekday/weekend) |
| slot | hold |

### Timeouts & retries

| Situation | Behaviour |
|---|---|
| No input 20 s | Gentle reprompt (max 2) |
| No input 60 s, or person leaves (no presence for 15 s) | "Are you still there?" → after 10 s, SESSION_CANCELLED |
| Hold expiring (60 s left) | Visual + voice warning. Customer can extend once (if the slot is still free) |
| Hold expired | Back to SLOT_SELECTION with fresh availability |
| Low ASR confidence on a critical field | Read back and ask for confirmation. After 2 failures, switch that field to touch input |
| Tool error (retryable) | 1 automatic retry with backoff, then apologise and offer touch/staff |
| Booking creation failure | Never shows success. ERROR_RECOVERY explains and offers retry or staff help |
| Session hard limit | 10 min (configurable) → staff assistance suggestion |

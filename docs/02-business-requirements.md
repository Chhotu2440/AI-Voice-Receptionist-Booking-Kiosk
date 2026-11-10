# 02 — Business Requirements

## 1. Business understanding (verified 2026-11-10 from the public website)

| Item | Finding | Source | Confidence |
|---|---|---|---|
| Name | Play Laser Tag (footer says "© 2026 The Laser Tag") | playlasertag.in | Verified |
| Address | T-49 Hauz Khas Village, near The Hidden Hour, New Delhi 110016 | playlasertag.in | Verified |
| Phones | +91 70425 13648 (also WhatsApp), +91 79921 22019, +91 95608 81488 | playlasertag.in | Verified |
| Email | playlazertag@gmail.com (spelled with a "z") | playlasertag.in | Verified |
| Game modes | Team Match, Shooting, Friendly Fire | playlasertag.in | Verified |
| Audience | Kids, teenagers, adults; "all ages" | playlasertag.in | Verified, but no formal age limits |
| Opening hours | **Not published** | — | Unknown |
| Arena capacity / players per game | **Not published** | — | Unknown |
| Event pricing | "Customized… varies from customer-to-customer"; no published party packages | /party | Verified |
| Other activities | Paintball, Zorbing, Rodeo Bull Ride shown on /pricing (a "virtual reality" heading actually describes zorbing) | /pricing | Unclear whether offered at this venue |

### Packages (as published on the homepage)

| Package | Content | Mon–Thu | **Fri–Sun** | Duration |
|---|---|---|---|---|
| Beginner | 2 games | ₹300/player | ₹400/player | 30 min |
| Intermediate | 4 formats | ₹450/player | ₹550/player | 45 min |
| Expert | 5 formats | ₹600/player | ₹650/player | 60 min |

**Important finding:** the website defines **"weekend" as Friday to Sunday**, not Saturday and Sunday. The pricing engine will make the day classification configurable, and the seed data will follow the website until the business confirms otherwise. The site also mentions special-edition rounds for "lucky players" and a high-score challenge for experts. The AI must not mention these until the business defines them in the admin panel.

## 2. Existing website analysis

- The site has a marketing-only structure, and every booking CTA goes to `playlasertag.dayschedule.com`. The /party page also links appoint.ly and a phone number.
- **Defects found:** the policy links are mismatched ("Terms & Condition" links to a refund-policy URL), the "virtual reality" heading sits over zorbing copy, and the /pricing page shows no laser tag prices (they appear on the homepage). Reported to the business. These fixes are outside this project's code but matter for data the AI may quote.
- **Implication:** the website must not become a second source of truth. All package and price data the AI uses comes from our admin-managed database.

## 3. Existing booking system analysis

- The DaySchedule page loads client-side, so it could not be read without a browser session. Its configured services, durations, form fields and payment settings are **unverified**. Action: the owner shares an admin screenshot or grants read access (task DISC-03).
- DaySchedule facts from its docs: REST API at `https://api.dayschedule.com/v1/...`, available on paid plans (Professional at $8/user/month and above); group events are a premium resource type with "seats per slot". Full analysis in [13-booking-integration.md](13-booking-integration.md).

## 4. Business requirements

| ID | Requirement | Priority |
|---|---|---|
| BR-01 | Customers can complete a standard package booking at the kiosk without staff help | Must |
| BR-02 | Interaction by voice, by touch, or both, with no keyboard | Must |
| BR-03 | English, Hindi and Hinglish | Must |
| BR-04 | Packages, prices, hours, holidays and capacity are editable by staff without code changes | Must |
| BR-05 | No overbooking across kiosk, website and staff channels | Must |
| BR-06 | Custom events (birthday, corporate, school, private) captured as enquiries and routed to staff | Must |
| BR-07 | Booking confirmation by WhatsApp when consented | Should |
| BR-08 | Optional online payment (deposit or full) | Could, pending decision |
| BR-09 | Staff can see and manage all bookings in one place | Must |
| BR-10 | AI running cost visible and capped by alerts | Must |
| BR-11 | Privacy-safe camera use; compliance with Indian data protection law | Must |

## 5. Assumption register

Each assumption is in force until the business confirms or corrects it. The ones marked ⚠ materially affect the design.

| ID | Assumption | Impact if wrong |
|---|---|---|
| A-01 ⚠ | A booked slot is a **private game for one group** (the arena is not shared between unrelated groups in the same slot) | Capacity model changes to shared seats |
| A-02 ⚠ | There is one arena (one bookable resource) | Need multiple resources and parallel slots |
| A-03 ⚠ | Maximum players per game is between 10 and 20 (placeholder 16), and the minimum per booking is 1 or 2 | Guest limits, large-group routing |
| A-04 | Slots start every 30 minutes; package durations are 30, 45 and 60 minutes; a 10-minute briefing/changeover buffer applies | Slot generator config |
| A-05 | Opening hours 11:00–22:00 daily (placeholder) | Slot generator config |
| A-06 | "Weekend" pricing applies Friday to Sunday, as on the website | Pricing rule config |
| A-07 | Published prices are GST-inclusive | Tax display and calculation |
| A-08 | Default payment mode is "reserve now, pay at reception" | Payment build scope |
| A-09 | Groups above a configurable threshold (placeholder: more than 20) or any corporate/school event become staff-handled enquiries | Routing |
| A-10 | The kiosk runs only during business hours, in a moderately noisy reception | Hardware choice, VAD tuning |
| A-11 | Paintball, zorbing and bull ride are not bookable at this venue | Scope |
| A-12 | Bookings are allowed up to 30 days ahead, with a same-day cut-off 15 minutes before slot start | Config |

## 6. Open business decisions

Tracked in [PROJECT_DECISIONS.md §Open business decisions](../PROJECT_DECISIONS.md#open-business-decisions). The most material:

1. Is a slot exclusive to one group or shared? What is the maximum number of players per game? (A-01, A-03)
2. Opening hours, slot interval and buffer (A-04, A-05)
3. Payment model: pay at reception, deposit, or full payment (A-08)
4. Replace DaySchedule with our web booking page? (ADR-003)
5. Are prices GST-inclusive? What is the GSTIN? (A-07)
6. WhatsApp Business: which number, Meta Business verification, and who owns the account?
7. Large-group threshold and which occasions always route to staff (A-09)
8. Hardware budget tier (see doc 15)
9. Data retention period for customer records

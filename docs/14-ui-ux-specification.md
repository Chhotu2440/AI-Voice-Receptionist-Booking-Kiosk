# 14 — UI/UX Specification (Kiosk)

## 1. Design direction
- **Theme:** dark arena (#07080F base, #10131F surfaces) with neon accents: laser cyan `#22E4FF` (primary), plasma magenta `#FF2BD6` (highlight), signal lime `#B6FF3B` (success), alert amber `#FFB020` (warnings). Neon is used only for accents and focus states. Body text is off-white `#EDEFF7` (contrast ≥ 12:1).
- **Type:** "Orbitron" (or "Chakra Petch") for display headings, "Inter" for body. Self-hosted fonts, so nothing loads from the network at runtime. Sizes at 1920×1080: H1 72 px, H2 48, body 28, minimum 22.
- **Assistant:** an abstract animated orb/visor character (Lottie or Rive). States: idle-breathing, listening (reacts to mic level), thinking (orbiting particles), speaking (driven by output amplitude). No human face, which avoids uncanny-valley effects and keeps the brand simple.
- **Layout:** landscape 16:9. Left 35%: assistant + live caption. Right 65%: the step's interactive content. Top: a progress rail with 6 steps (You → Group → Package → Date & Time → Review → Done). Bottom bar: Back, language toggle EN/हिं, mic mute, "Call staff".
- **Touch:** minimum target 72×72 px, 16 px gaps, no hover-dependent UI, press feedback in under 50 ms, no long-press gestures.
- **Motion:** 200–300 ms ease-out transitions. Package cards slide in with a stagger. Confirmation uses a laser-sweep + confetti burst (1.5 s). Everything respects a `reducedMotion` kiosk config.
- **Audio UI:** a mic-level ring around the orb, a "Listening…" chip, and an instant visual cut when barge-in happens.

## 2. Screens

| # | Screen | Key elements | Notes |
|---|---|---|---|
| 1 | Welcome / idle | Attract video loop (arena footage), "Tap to start" big button, privacy notice line "Camera detects presence only. Nothing is recorded." | Brightness can dim after hours |
| 2 | Customer detection | Soft ring pulse, "Hi there! 👋" | 1–2 s, cancels if the person leaves |
| 3 | Greeting | Orb speaks, title "Welcome to Play Laser Tag!", consent micro-notice about voice processing | — |
| 4 | Name | Large name display, ✎ edit opens on-screen alpha keyboard (EN + Devanagari toggle) | — |
| 5 | Phone | Big 10-digit readout grouped `98765 43210`, numeric keypad always visible, "Is this correct?" Yes/Edit | Masked later as `98•••••210` |
| 6 | Guests | Chips 1–12 + "More" → stepper (+/−) up to the max | Message when routing to an enquiry |
| 7 | Occasion | 6 illustrated tiles | — |
| 8 | Custom event | Occasion-specific optional fields, "Our team will call you" | — |
| 9 | Package discovery | 3 cards: name, duration, formats/games, ₹/person, est. total for N, features, "Recommended" ribbon | Prices are from the API only |
| 10 | Package comparison | Side-by-side table (triggered by "what's the difference?") | — |
| 11 | Date | 2-week strip + "More dates" month view. Today/Tomorrow quick chips, closed dates greyed with the reason | — |
| 12–13 | Slots | Grid of time pills (start–end), "Only 1 left" badges where `SHARED_SEATS` applies, alternatives panel if none | — |
| 14 | Summary | Line-item breakdown, tax line, total, payment note ("Pay at reception"), hold countdown, WhatsApp consent checkbox, giant **Confirm Booking** button | — |
| 15 | Confirmation | Booking ref in huge type, QR (encodes ref only), details, "See you at HH:MM!" | Auto-reset countdown |
| 16 | Error | Friendly message, Retry, Call staff. Never shows technical details | — |
| 17 | Staff assistance | "A team member is on the way", staff PIN entry for takeover | — |
| 18 | Session reset | Wipe animation "All clear for the next player" | — |

## 3. Accessibility
High contrast, captions for all AI speech, touch-only completion path, adjustable volume in admin, and no time pressure except the hold (a visible countdown with an extend option). Hindi UI strings are reviewed by a native speaker.

## 4. Admin dashboard specification
Separate React app (`admin/`) with a conventional clean UI (light/dark), desktop-first and usable on tablets.

| Area | Capabilities | Permission |
|---|---|---|
| Dashboard | Today's & upcoming bookings, totals, revenue (from snapshots), conversion funnel (sessions → package → slot → booking), popular packages, occasion breakdown, failed/abandoned sessions, AI cost (today/month, per booking), kiosk status tile | `dashboard.read` |
| Packages | Create/edit/activate, duration, features (EN/HI), min/max guests, recommended flag, sort | `catalogue.write` |
| Pricing | Weekday/weekend day sets, base prices, date overrides, holiday/special prices, promos, group discounts, tax mode & rate, extra charges, **price preview** | `pricing.write` |
| Schedule | Business hours, holidays, special hours, blackouts, manual blocks, slot interval, buffer, resources & capacity, regenerate slots | `schedule.write` |
| Bookings | Search/filter, view (with pricing snapshot & history), manual create (hold→book), cancel, reschedule, status updates, payment status, print day sheet | `booking.*` |
| Customers | Details, booking history, consent log, anonymize/export | `customer.*` |
| Enquiries | Pipeline board, assign, notes, status | `enquiry.*` |
| Kiosks | Pair device, online/offline, last heartbeat, app version, current session state (no PII), usage stats, remote config (thresholds, volume, voice on/off), alerts | `kiosk.*` |
| AI configuration | Provider, model, voice, languages, assistant name, greeting, personality notes (appended to the base prompt, not replacing guardrails), session limits, fallback behaviour, spend caps & alert recipients, usage reports. Provider credentials are **not** editable in the UI (server env only) | `ai.config` (OWNER) |
| Users & audit | Users, roles, 2FA, audit log viewer | `user.*`, `audit.read` |

## 5. Display assumption
Designed for a **21.5"–27" 1920×1080 landscape** touchscreen (doc 15). A portrait 1080×1920 layout is a stretch goal and depends on the hardware decision.

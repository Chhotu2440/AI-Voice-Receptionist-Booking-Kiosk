# 08 — Database Design (MySQL 8, InnoDB, utf8mb4)

## Conventions
- **IDs:** `BINARY(16)` UUIDv7 (time-ordered, index-friendly), exposed as strings in the API. Small lookup tables use `SMALLINT` IDs.
- **Money:** `DECIMAL(12,2)` in INR. Rates: `DECIMAL(5,2)` percent.
- **Time:** `DATETIME(6)` UTC for instants. `DATE`/`TIME` for business-local calendar values (Asia/Kolkata).
- Every table has `created_at` and `updated_at`. Soft delete (`deleted_at`) is used **only** for packages, users and customers (data-subject deletion = anonymize). Bookings are never deleted; they change status.
- Enums are stored as `VARCHAR(32)` with CHECK constraints, so values can be added without an ALTER of an ENUM.

## Entity overview

```
users ─< user_roles >─ roles ─< role_permissions >─ permissions
customers ─< customer_consents
customers ─< bookings ─< booking_items
                    ├── booking_pricing_snapshots (1:1)
                    ├─< booking_status_history
                    ├─< payments
                    └─< notification_logs
packages ─< package_features ; packages ─< package_pricing_rules
business_locations ─< resources ─< availability_slots ─< slot_holds ─(0..1)─ bookings
business_locations ─< business_hours ; ─< schedule_exceptions (holidays/special hours/blackouts)
kiosk_devices ─< kiosk_sessions ─ ai_conversation_sessions ─< ai_usage_logs
custom_event_enquiries ; audit_logs ; system_settings ; webhook_events ; idempotency_keys ; occasions
```

**Normalization decisions vs the candidate list:**
- `holidays` is merged into **`schedule_exceptions`** (type HOLIDAY | SPECIAL_HOURS | BLACKOUT | MANUAL_BLOCK). One rule source means one query path.
- `resource_capacity` is merged into `resources` (`default_capacity`, `capacity_mode`). Per-slot overrides live on `availability_slots.capacity`.
- `occasions` is kept as a table (admin-editable labels in EN/HI, flags such as `always_enquiry`).
- Added: **`idempotency_keys`** (required by Part 10) and `user_roles`/`role_permissions` join tables.

## Tables

### Identity & access
**users**: `id PK`, `email VARCHAR(255) UNIQUE`, `name`, `password_hash VARCHAR(255)` (argon2id), `is_active BOOL`, `failed_login_count INT`, `locked_until DATETIME(6) NULL`, `last_login_at`, `deleted_at`, timestamps. (`totp_secret_enc` will be added with TOTP, task CORE-05.)
**refresh_tokens** *(added in Sprint 1)*: `id PK`, `user_id FK`, `token_hash CHAR(64) UNIQUE` (SHA-256; raw token never stored), `family_id` (rotation chain), `issued_at`, `expires_at`, `used_at NULL`, `revoked_at NULL`, `ip`, `user_agent`. Index `(family_id)`. Reuse of a used/revoked token revokes the whole family.
**roles**: `id SMALLINT PK`, `code VARCHAR(32) UNIQUE` (OWNER, MANAGER, STAFF, VIEWER), `name`.
**permissions**: `id SMALLINT PK`, `code VARCHAR(64) UNIQUE` (e.g. `booking.cancel`, `pricing.write`).
**user_roles** (`user_id FK`, `role_id FK`, PK both). **role_permissions** (`role_id`, `permission_id`, PK both).

### Customers
**customers**: `id PK`, `name VARCHAR(80)`, `phone_e164 VARCHAR(16) UNIQUE` (normalized), `email NULL`, `preferred_language CHAR(5)`, `first_seen_at`, `last_booking_at`, `anonymized_at NULL`, `deleted_at`, timestamps. Index: `(last_booking_at)` for the retention job.
**customer_consents**: `id PK`, `customer_id FK`, `purpose VARCHAR(32)` (WHATSAPP_TRANSACTIONAL, MARKETING, TRANSCRIPT_RETENTION), `granted BOOL`, `notice_version VARCHAR(16)`, `channel` (KIOSK/WEB/STAFF), `kiosk_session_id NULL`, `granted_at`, `withdrawn_at NULL`. Index `(customer_id, purpose)`. Append-only, so the latest row wins.

### Catalogue & pricing
**packages**: `id PK`, `code VARCHAR(32) UNIQUE`, `name_en`, `name_hi`, `description_en/hi TEXT`, `duration_min SMALLINT`, `games_count SMALLINT NULL`, `formats_count SMALLINT NULL`, `min_guests`, `max_guests`, `is_recommended BOOL`, `sort_order`, `is_active`, `deleted_at`, timestamps.
**package_features**: `id PK`, `package_id FK`, `text_en`, `text_hi`, `sort_order`.
**package_pricing_rules**: `id PK`, `package_id FK NULL` (NULL = all packages), `rule_type` (BASE_DAYTYPE | DATE_OVERRIDE | DATE_RANGE | PROMO | GROUP_DISCOUNT), `day_type` (WEEKDAY/WEEKEND/NULL), `date_from DATE NULL`, `date_to DATE NULL`, `min_guests NULL`, `promo_code VARCHAR(32) NULL` (PROMO only; NULL = automatic promotion), `price_per_person DECIMAL(12,2) NULL`, `discount_pct DECIMAL(5,2) NULL`, `priority SMALLINT`, `is_active`, `valid_from DATETIME NULL`, `valid_to NULL`, `created_by FK users`. Index `(package_id, rule_type, is_active)`.
Global tax and charges live in `system_settings` (`pricing.tax_rate`, `pricing.prices_include_tax`, `pricing.weekend_days=[FRI,SAT,SUN]`, `pricing.extra_charges=[…]`).
**occasions**: `id SMALLINT PK`, `code UNIQUE` (FRIENDS_FAMILY, BIRTHDAY, CORPORATE, SCHOOL_COLLEGE, PRIVATE_PARTY, OTHER), `label_en`, `label_hi`, `always_enquiry BOOL`, `extra_fields_schema JSON`, `sort_order`, `is_active`.

### Schedule & capacity
**business_locations**: `id PK`, `name`, `address`, `timezone VARCHAR(40)` default 'Asia/Kolkata', `phone`, `gstin NULL`.
**business_hours**: `id PK`, `location_id FK`, `weekday TINYINT (0=Mon)`, `open_time TIME`, `close_time TIME`, `is_closed BOOL`. UNIQUE `(location_id, weekday)`.
**schedule_exceptions**: `id PK`, `location_id FK`, `resource_id FK NULL`, `type`, `exception_date DATE`, `start_time TIME NULL`, `end_time TIME NULL`, `reason`, `created_by`. Index `(location_id, exception_date)`. (Column renamed from `date` to avoid a reserved-word/type clash; the API still exposes it as `date`.)
**resources**: `id PK`, `location_id FK`, `name` (e.g. "Main Arena"), `capacity_mode` (EXCLUSIVE | SHARED_SEATS), `default_capacity SMALLINT`, `max_players SMALLINT`, `slot_interval_min`, `buffer_min`, `is_active`.
**availability_slots**: materialized grid. `id PK`, `resource_id FK`, `business_date DATE`, `start_at DATETIME(6)` UTC, `end_at`, `capacity SMALLINT`, `held_qty SMALLINT DEFAULT 0`, `booked_qty SMALLINT DEFAULT 0`, `is_blocked BOOL`, `version INT`. **UNIQUE `(resource_id, start_at)`**, index `(resource_id, business_date)`, **`CHECK (held_qty >= 0 AND booked_qty >= 0 AND held_qty + booked_qty <= capacity)`**. Generated N days ahead by a nightly job, and regenerated for a date when the schedule changes (only free slots are mutated).
**slot_holds**: `id PK`, `resource_id`, `kiosk_session_id NULL`, `channel` (KIOSK/WEB/STAFF), `package_id`, `guest_count`, `units SMALLINT`, `start_at`, `end_at`, `status` (ACTIVE/RELEASED/EXPIRED/CONVERTED), `expires_at DATETIME(6)`, `booking_id BINARY(16) NULL UNIQUE`, `idempotency_key VARCHAR(64) NULL`, timestamps. Index `(status, expires_at)`.
**slot_hold_slots** (`hold_id FK`, `slot_id FK`, PK both): which grid cells the hold covers (needed for multi-cell packages).

### Bookings
**bookings**: `id PK`, `reference VARCHAR(12) UNIQUE` (human-friendly, e.g. `PLT-7K3Q9X`), `customer_id FK`, `location_id`, `resource_id`, `package_id`, `occasion_id`, `occasion_details JSON NULL`, `guest_count`, `business_date`, `start_at`, `end_at`, `status` (CONFIRMED, CANCELLED, NO_SHOW, COMPLETED, PENDING_PAYMENT), `payment_status` (NOT_REQUIRED, PENDING, PARTIALLY_PAID, PAID, REFUNDED, FAILED), `payment_mode` (PAY_AT_VENUE, DEPOSIT, FULL), `channel`, `source_hold_id NULL`, `kiosk_session_id NULL`, `notes TEXT`, `cancelled_at`, `cancel_reason`, `created_by_user_id NULL`, timestamps. Indexes `(business_date, status)`, `(customer_id, start_at)`, `(status, start_at)`.
**booking_items**: `id PK`, `booking_id FK`, `item_type` (PACKAGE, ADDON, CHARGE), `ref_id NULL`, `description`, `qty`, `unit_price`, `amount`.
**booking_slots** (`booking_id`, `slot_id`, `units`, PK booking+slot): grid cells consumed, used for release on cancel or reschedule.
**booking_pricing_snapshots**: `booking_id PK/FK`, `day_type`, `price_per_person`, `subtotal`, `discount_total`, `tax_rate`, `tax_amount`, `charges_total`, `total`, `prices_include_tax BOOL`, `rules_applied JSON`, `computed_at`. Immutable.
**booking_status_history**: `id PK`, `booking_id FK`, `from_status`, `to_status`, `actor_type` (SYSTEM/KIOSK/AI/USER/WEBHOOK), `actor_id NULL`, `reason`, `created_at`. Index `(booking_id, created_at)`.

### Payments & notifications
**payments**: `id PK`, `booking_id FK`, `provider` (RAZORPAY/CASH/UPI_DESK), `provider_order_id UNIQUE NULL`, `provider_payment_id UNIQUE NULL`, `amount`, `currency CHAR(3)`, `status` (CREATED/AUTHORIZED/CAPTURED/FAILED/REFUNDED), `verified_at NULL`, `raw JSON`, timestamps.
**notification_logs**: `id PK`, `booking_id NULL`, `enquiry_id NULL`, `customer_id NULL`, `channel` (WHATSAPP/SMS/EMAIL), `template`, `to_masked`, `provider_message_id UNIQUE NULL`, `status` (QUEUED/SENT/DELIVERED/READ/FAILED), `error_code NULL`, `attempts`, `last_attempt_at`, timestamps. Index `(status, last_attempt_at)`.
**webhook_events**: `id PK`, `provider`, `event_id VARCHAR(128)`, `signature_valid BOOL`, `payload JSON`, `processed_at NULL`, `error NULL`. **UNIQUE `(provider, event_id)`** for dedupe.

### Kiosk & AI
**kiosk_devices**: `id PK`, `location_id`, `name`, `secret_hash`, `status` (ACTIVE/DISABLED), `app_version`, `last_heartbeat_at`, `last_ip`, `config JSON` (thresholds, volume, voice on/off), timestamps.
**kiosk_sessions**: `id PK`, `device_id FK`, `started_at`, `ended_at`, `end_reason` (COMPLETED/CANCELLED/TIMEOUT/ERROR/STAFF), `final_state`, `mode` (VOICE/TOUCH/MIXED), `language`, `booking_id NULL`, `enquiry_id NULL`, `funnel_max_state`. No PII.
**ai_conversation_sessions**: `id PK`, `kiosk_session_id FK`, `provider`, `model`, `voice`, `started_at`, `ended_at`, `turns`, `tool_calls`, `tool_errors`, `barge_ins`, `avg_ttfa_ms`, `transcript_ref NULL` (only if consented).
**ai_usage_logs**: `id PK`, `ai_session_id FK`, `audio_in_tokens`, `audio_out_tokens`, `text_in_tokens`, `text_cached_tokens`, `text_out_tokens`, `audio_in_sec`, `audio_out_sec`, `cost_usd DECIMAL(10,5)`, `price_version`, `created_at`. Index `(created_at)`.

### Cross-cutting
**custom_event_enquiries**: `id PK`, `reference UNIQUE`, `customer_id FK`, `occasion_id`, `guest_count`, `preferred_date NULL`, `details JSON` (birthday person, age, company, institution, requirements), `status` (NEW/CONTACTED/QUOTED/WON/LOST), `assigned_to NULL`, `channel`, timestamps.
**audit_logs**: `id PK`, `actor_type`, `actor_id`, `action`, `entity_type`, `entity_id`, `before JSON`, `after JSON`, `ip`, `created_at`. Index `(entity_type, entity_id)`, `(created_at)`. Append-only (no UPDATE/DELETE grant for the app DB user).
**system_settings**: `key VARCHAR(100) PK`, `value JSON`, `updated_by`, `updated_at`.
**idempotency_keys**: `key VARCHAR(64)`, `scope VARCHAR(32)`, `request_hash CHAR(64)`, `response_status`, `response_body JSON`, `expires_at`. **PK `(scope, key)`**.

## Implementation status
Sprint 1 (migration `0001`) implements: users, roles, permissions, user_roles, role_permissions, refresh_tokens, packages, package_features, package_pricing_rules, occasions, business_locations, business_hours, schedule_exceptions, resources, audit_logs, system_settings. Sprint 2 (migration `0002`) adds: availability_slots, slot_holds, slot_hold_cells, customers, customer_consents, bookings, booking_slots, booking_items, booking_pricing_snapshots, booking_status_history, custom_event_enquiries, idempotency_keys. The remaining tables arrive with their features (payments, notifications, kiosks, AI usage, webhooks).

**Implementation notes (Sprint 2):**
- `availability_slots` cells are created **lazily** (insert-if-missing) when a slot is first held, one row per grid interval. Opening hours and exceptions are applied when availability is computed, not stored on cells, so schedule changes need no regeneration. `is_blocked` and `version` were dropped as unnecessary.
- `slot_holds.booking_id` is indexed but **not unique**, because a reschedule converts a second hold into the same booking. `CONVERTED` status plus the hold row lock prevent double conversion.
- Hold and booking capability tokens are HMACs of the id (`services/tokens.py`), so no token hashes are stored.
- `bookings.occasion_details` holds only keys declared in the occasion's `extra_fields_schema`, plus `special_requirements`.

## Timezone rules
1. The API accepts and returns local dates as `YYYY-MM-DD` and times as ISO-8601 with `+05:30`.
2. The DB stores instants in UTC, and `business_date` is computed in IST at write time.
3. "Today" is always `now(IST).date()` from `timeutil.today_local()`, never `CURRENT_DATE` on the server (the server may run in UTC).

## Seed data (dev/staging only)
The three packages with website prices, the six occasions, Mon–Thu/Fri–Sun day types, one location, one "Main Arena" resource, placeholder hours (A-05), an owner user created via CLI (`python -m app.cli create-owner`, password prompted, never seeded).

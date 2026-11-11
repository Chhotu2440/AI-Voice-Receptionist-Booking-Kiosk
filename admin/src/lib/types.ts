export type Page<T> = { items: T[]; page: number; page_size: number; total: number };

export type Me = {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  role_codes: string[];
  last_login_at: string | null;
  permissions: string[];
};

export type PriceQuote = {
  package_id: string;
  date: string;
  day_type: string;
  guest_count: number;
  price_per_person: string;
  subtotal: string;
  discounts: { rule_id: string; name: string; pct: string; amount: string }[];
  discount_total: string;
  charges: { code: string; label: string; amount: string }[];
  charges_total: string;
  tax: { rate: string; amount: string; included: boolean };
  total: string;
  currency: string;
};

export type BookingHistory = {
  from_status: string | null;
  to_status: string;
  actor_type: string;
  reason: string;
  details: Record<string, unknown> | null;
  created_at: string;
};

export type Booking = {
  id: string;
  reference: string;
  status: string;
  payment_status: string;
  payment_mode: string;
  channel: string;
  package_id: string;
  package_name: string;
  occasion_code: string;
  guest_count: number;
  date: string;
  start_time: string;
  end_time: string;
  start_at: string;
  end_at: string;
  customer: { name: string; phone_masked: string };
  pricing: PriceQuote;
  customer_id: string;
  customer_phone: string;
  occasion_details: Record<string, unknown>;
  notes: string;
  cancel_reason: string | null;
  history: BookingHistory[];
};

export type Enquiry = {
  id: string;
  reference: string;
  status: string;
  occasion_code: string;
  guest_count: number;
  preferred_date: string | null;
  created_at: string;
  customer_name: string;
  customer_phone: string;
  details: Record<string, unknown>;
  staff_notes: string;
  channel: string;
};

export type Kiosk = {
  id: string;
  name: string;
  status: string;
  paired_at: string | null;
  app_version: string | null;
  last_heartbeat_at: string | null;
  health: Record<string, unknown>;
  config: Record<string, unknown>;
  online: boolean;
};

export type PackageT = {
  id: string;
  code: string;
  name_en: string;
  min_guests: number;
  max_guests: number;
  duration_min: number;
  is_active: boolean;
};

export type Occasion = { code: string; label_en: string; always_enquiry: boolean; is_active: boolean };

export type Slot = { start_time: string; end_time: string; remaining: number; duration_min: number };
export type DaySlots = { date: string; status: "OPEN" | "FULL" | "CLOSED"; closed_reason: string; slots: Slot[] };

export type Hold = { hold_id: string; hold_token: string; expires_at: string; start_time: string; end_time: string };

export type Notification = {
  id: string;
  booking_id: string | null;
  channel: string;
  provider: string;
  template: string;
  to_masked: string;
  status: string;
  provider_message_id: string | null;
  error: string | null;
  attempts: number;
  created_at: string;
  delivered_at: string | null;
};

export type Dashboard = {
  from: string;
  to: string;
  today: {
    date: string;
    bookings: number;
    guests: number;
    revenue: string;
    list: {
      id: string;
      reference: string;
      start_time: string;
      end_time: string;
      customer_name: string;
      guest_count: number;
      status: string;
      channel: string;
      total: string;
      upcoming: boolean;
    }[];
  };
  upcoming_7_days: number;
  open_enquiries: number;
  totals: { bookings: number; revenue: string; cancelled: number; average_booking: string };
  by_day: { date: string; bookings: number; guests: number; revenue: string }[];
  packages: { name: string; bookings: number; revenue: string }[];
  occasions: { name: string; bookings: number }[];
  channels: Record<string, number>;
  funnel: { step: string; sessions: number }[];
  kiosk_sessions: { total: number; voice: number; abandoned: Record<string, number> };
  kiosks: { active: number; online: number };
  ai: {
    today_usd: string;
    month_usd: string;
    month_inr: string;
    daily_cap_usd: string;
    monthly_cap_usd: string;
    voice_allowed: boolean;
  };
};

export type AiUsage = {
  from: string;
  to: string;
  voice_sessions: number;
  voice_bookings: number;
  cost_usd: string;
  cost_inr: string;
  cost_per_session_usd: string | null;
  cost_per_booking_inr: string | null;
  by_day: {
    date: string;
    provider: string;
    sessions: number;
    cost_usd: string;
    minutes: number;
    phantom_answers_blocked: number;
  }[];
  caps: {
    daily_cap_usd: string;
    monthly_cap_usd: string;
    today_usd: string;
    month_usd: string;
    voice_allowed: boolean;
    reason: string;
  };
};

export type AiSettings = {
  daily_cap_usd: string;
  monthly_cap_usd: string;
  usd_inr: string;
  price_version: string;
  prices: Record<string, Record<string, string>>;
};

export type CustomerSummary = {
  id: string;
  name: string;
  phone: string;
  phone_masked: string;
  email: string | null;
  preferred_language: string;
  first_seen_at: string | null;
  last_booking_at: string | null;
  anonymized_at: string | null;
  bookings: number;
  total_spent: string;
};

export type CustomerDetail = CustomerSummary & {
  bookings_list: {
    id: string;
    reference: string;
    date: string;
    start_time: string;
    package_name: string;
    guest_count: number;
    status: string;
    channel: string;
    total: string;
  }[];
  enquiries: {
    id: string;
    reference: string;
    status: string;
    guest_count: number;
    preferred_date: string | null;
    created_at: string;
  }[];
  consents: Record<string, boolean>;
  consent_log: { purpose: string; granted: boolean; notice_version: string; channel: string; created_at: string }[];
};

export type StaffUser = {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  role_codes: string[];
  last_login_at: string | null;
};

export type AuditEntry = {
  id: number;
  created_at: string;
  actor_type: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
};

export type PackageFull = {
  id: string;
  code: string;
  name_en: string;
  name_hi: string;
  description_en: string;
  description_hi: string;
  duration_min: number;
  games_count: number | null;
  formats_count: number | null;
  min_guests: number;
  max_guests: number;
  is_recommended: boolean;
  sort_order: number;
  is_active: boolean;
  features: { text_en: string; text_hi: string }[];
};

export type OccasionFull = {
  code: string;
  label_en: string;
  label_hi: string;
  always_enquiry: boolean;
  extra_fields_schema: Record<string, unknown>[];
  sort_order: number;
  is_active: boolean;
};

export type RuleType = "BASE_DAYTYPE" | "DATE_OVERRIDE" | "DATE_RANGE" | "PROMO" | "GROUP_DISCOUNT";

export type PricingRule = {
  id: string;
  package_id: string | null;
  rule_type: RuleType;
  name: string;
  day_type: "WEEKDAY" | "WEEKEND" | null;
  date_from: string | null;
  date_to: string | null;
  min_guests: number | null;
  promo_code: string | null;
  price_per_person: string | null;
  discount_pct: string | null;
  priority: number;
  is_active: boolean;
  valid_from: string | null;
  valid_to: string | null;
};

export type PricingSettings = {
  weekend_days: string[];
  tax_rate: string;
  prices_include_tax: boolean;
  discount_stacking: "BEST" | "STACK";
  extra_charges: { code: string; label: string; mode: "FLAT" | "PER_PERSON"; amount: string }[];
  currency: "INR";
};

export type BookingSettings = {
  max_days_ahead: number;
  same_day_cutoff_min: number;
  large_group_threshold: number;
  hold_ttl_seconds: number;
};

export type HoursDay = { weekday: number; open_time: string; close_time: string; is_closed: boolean };

export type ScheduleException = {
  id: string;
  type: "HOLIDAY" | "SPECIAL_HOURS" | "BLACKOUT" | "MANUAL_BLOCK";
  date: string;
  start_time: string | null;
  end_time: string | null;
  resource_id: string | null;
  reason: string;
};

export type Resource = {
  id: string;
  name: string;
  capacity_mode: "EXCLUSIVE" | "SHARED_SEATS";
  default_capacity: number;
  max_players: number;
  slot_interval_min: number;
  buffer_min: number;
  is_active: boolean;
};

export type BusinessInfo = {
  name: string;
  address: string;
  city: string;
  postal_code: string;
  timezone: string;
  phone: string;
  whatsapp: string;
  email: string;
  maps_url: string;
};

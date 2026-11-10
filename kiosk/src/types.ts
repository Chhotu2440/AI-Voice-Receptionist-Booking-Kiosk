// Mirrors backend/app/kiosk/state.py KioskState.public(). The screen renders this; it never decides state.

export type KioskStateName =
  | "IDLE"
  | "GREETING"
  | "CUSTOMER_NAME"
  | "CUSTOMER_PHONE"
  | "GUEST_COUNT"
  | "OCCASION"
  | "CUSTOM_EVENT_DETAILS"
  | "PACKAGE_DISCOVERY"
  | "DATE_SELECTION"
  | "SLOT_SELECTION"
  | "BOOKING_SUMMARY"
  | "BOOKING_CONFIRMED"
  | "SESSION_COMPLETE"
  | "STAFF_ASSISTANCE"
  | "SESSION_CANCELLED";

export type Lang = "en" | "hi";

export interface PackageCard {
  id: string;
  code: string;
  name_en: string;
  name_hi: string;
  description_en: string;
  description_hi: string;
  duration_min: number;
  games_count: number | null;
  formats_count: number | null;
  features: { en: string; hi: string }[];
  recommended: boolean;
  eligible: boolean;
  min_guests: number;
  max_guests: number;
  price_per_person: string | null;
  estimated_total: string | null;
  day_type: string | null;
}

export interface DateStatus {
  date: string;
  status: "OPEN" | "FULL" | "CLOSED";
  slots_available: number;
  closed_reason: string;
}

export interface Slot {
  start_time: string;
  end_time: string;
  start_at: string;
  end_at: string;
  duration_min: number;
  remaining: number;
}

export interface Quote {
  day_type: string;
  guest_count: number;
  price_per_person: string;
  subtotal: string;
  discounts: { name: string; pct: string; amount: string }[];
  discount_total: string;
  charges: { code: string; label: string; amount: string }[];
  charges_total: string;
  tax: { rate: string; amount: string; included: boolean };
  total: string;
  currency: string;
}

export interface Booking {
  id: string;
  reference: string;
  status: string;
  payment_status: string;
  payment_mode: string;
  package_name: string;
  guest_count: number;
  date: string;
  start_time: string;
  end_time: string;
  customer: { name: string; phone_masked: string };
  pricing: Quote;
}

export interface KioskState {
  session_id: string | null;
  state: KioskStateName;
  version: number;
  language: Lang;
  customer_name: string | null;
  phone_display: string | null;
  phone_confirmed: boolean;
  guest_count: number | null;
  occasion_code: string | null;
  occasion_details: Record<string, string | number>;
  packages: PackageCard[];
  package_id: string | null;
  available_dates: DateStatus[];
  play_date: string | null;
  slots: Slot[];
  start_time: string | null;
  hold_id: string | null;
  hold_expires_at: string | null;
  hold_can_extend: boolean;
  quote: Quote | null;
  whatsapp_consent: boolean;
  booking: Booking | null;
  enquiry_reference: string | null;
  furthest_index: number;
  error: { code: string; message: string } | null;
}

export type ServerMessage =
  | { type: "state"; state: KioskState; allowed: string[]; in_reply_to: string | null }
  | { type: "error"; error: { code: string; message: string }; in_reply_to: string | null }
  | { type: "pong" };

export interface KioskConfig {
  idle_timeout_s: number;
  success_reset_s: number;
  voice_enabled: boolean;
  volume: number;
  assistant_name: string;
}

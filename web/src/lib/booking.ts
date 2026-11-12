import { API_BASE } from "./supabase";

export type Service = {
  id: string; category: string; name: string; description: string; duration_min: number;
  price_paise: number; advance_type: "none" | "fixed" | "percent"; advance_value: number;
};
export type Business = {
  id: string; slug: string; name: string; address: string; phone: string; email: string; maps_url: string;
  hold_minutes: number; cancellation_cutoff_hours: number; policy_text: string;
  open_now: boolean; closes_at: string | null; services: Service[];
};
export type Stylist = { id: string; name: string; title: string; bio: string; next_free: string | null };
export type Day = { date: string; count: number; full: boolean; closed: "holiday" | "out_of_range" | null };
export type Slot = { start: string; staff_ids: string[] };
export type SlotGroups = { morning: Slot[]; afternoon: Slot[]; evening: Slot[] };
export type Order = { order_id: string; key_id: string; amount_paise: number };
export type Hold = {
  booking_id: string; public_token: string; staff_id: string; hold_expires_at: string | null;
  status: "held" | "confirmed"; advance_paise: number; order: Order | null; name?: string; phone?: string;
};
export type BookingView = {
  booking_id: string; status: string; service: string; stylist: string; start: string; end: string;
  price_paise: number; advance_paid_paise: number; balance_paise: number; payment_status: string | null;
  refunded_paise: number; hold_expires_at: string | null; masked_phone: string; whatsapp_sent: boolean; customer_first_name: string;
  cancellation_cutoff_hours: number; business: { name: string; address: string; maps_url: string; slug: string };
};

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "NETWORK", "We couldn't reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    const detail = j.detail;
    const msg = j.message ?? (typeof detail === "string" ? detail : Array.isArray(detail) ? detail[0]?.msg : null);
    throw new ApiError(res.status, j.error ?? "ERROR", msg ?? "Something went wrong.");
  }
  return res.json();
}

const TZ = "Asia/Kolkata";
export const inr = (paise: number) => `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
export const advancePaise = (s: Service) =>
  s.advance_type === "fixed" ? Math.min(s.advance_value, s.price_paise)
    : s.advance_type === "percent" ? Math.round((s.price_paise * s.advance_value) / 10000) * 100 : 0;
export const fmtTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-IN", { timeZone: TZ, hour: "numeric", minute: "2-digit", hour12: true }).toUpperCase();
export const fmtDay = (iso: string, opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" }) =>
  new Date(iso.length === 10 ? `${iso}T00:00:00+05:30` : iso).toLocaleDateString("en-IN", { timeZone: TZ, ...opts });
export const istDate = (iso: string) => new Date(iso).toLocaleDateString("en-CA", { timeZone: TZ });
export const istToday = () => new Date().toLocaleDateString("en-CA", { timeZone: TZ });
export const mmss = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

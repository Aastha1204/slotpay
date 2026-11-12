import { PROTOTYPE, prototypeLogin } from "./prototype";
import { API_BASE, supabase } from "./supabase";

export const DEV_AUTH = process.env.NEXT_PUBLIC_DEV_AUTH === "1" || PROTOTYPE;
const DEV_KEY = "slotpay_dev_token";

export async function getToken(): Promise<string | null> {
  try {
    if (DEV_AUTH) { const t = localStorage.getItem(DEV_KEY); if (t) return t; }
  } catch { /* storage unavailable */ }
  if (PROTOTYPE) { const t = await prototypeLogin(); if (t) return t; }
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
export function setDevToken(t: string) { try { localStorage.setItem(DEV_KEY, t); } catch { /* */ } }
export async function signOut() {
  try { localStorage.removeItem(DEV_KEY); } catch { /* */ }
  await supabase.auth.signOut();
}

export class AdminError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function admin<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getToken();
  if (!token) throw new AdminError(401, "Not signed in");
  const call = (tok: string) => fetch(`${API_BASE}/admin${path}`, {
    ...init, headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}`, ...(init?.headers ?? {}) },
  });
  let res: Response;
  try {
    res = await call(token);
    if (res.status === 401 && PROTOTYPE) { // prototype tokens last 8 h: quietly sign in again
      try { localStorage.removeItem(DEV_KEY); } catch { /* */ }
      const fresh = await prototypeLogin();
      if (fresh) res = await call(fresh);
    }
  } catch { throw new AdminError(0, "Can't reach the server"); }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    const d = j.detail;
    throw new AdminError(res.status, j.message ?? (typeof d === "string" ? d : Array.isArray(d) ? d[0]?.msg : "Something went wrong"));
  }
  return res.json();
}

export type CalStaff = { id: string; name: string; title: string; service_ids: string[]; working: { start: string; end: string }[]; breaks: { start: string; end: string }[] };
export type CalBooking = {
  id: string; status: string; staff_id: string; start: string; end: string; service: string; customer: string; phone: string;
  source: string; price_paise: number; advance_paid_paise: number; hold_expires_at: string | null; payment_status: string | null; created_at: string;
};
export type CalBlock = { id: string; staff_id: string; start: string; end: string; reason: string };
export type Calendar = {
  business_id: string; date: string; view: "day" | "week"; range_start: string; day_start_min: number; day_end_min: number;
  staff: CalStaff[]; bookings: CalBooking[]; time_blocks: CalBlock[];
  services: { id: string; name: string; category: string; duration_min: number; price_paise: number }[];
};
export type Detail = {
  id: string; status: string; source: string; service: string; service_id: string; staff: string; staff_id: string; start: string; end: string;
  customer: { name: string; phone: string; whatsapp_opt_in: boolean }; price_paise: number; advance_paid_paise: number;
  payments: { order_id: string; payment_id: string | null; method: string | null; amount_paise: number; status: string; refunded_paise: number; is_seeded: boolean }[];
  refunds: { id: string; amount_paise: number; status: string }[];
  messages: { direction: string; channel: string; template: string | null; body: string; at: string }[];
  cancel_policy: { cutoff_hours: number; refund_eligible: boolean; text: string };
};

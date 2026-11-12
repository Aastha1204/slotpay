// Prototype mode: one website, every surface reachable, no manual tokens or keys.
// Enabled at build time with NEXT_PUBLIC_PROTOTYPE=1 (and the API with PROTOTYPE_MODE=true). Demo use only.
import { API_BASE } from "./supabase";

export const PROTOTYPE = process.env.NEXT_PUBLIC_PROTOTYPE === "1";
export const DEMO_KEY = process.env.NEXT_PUBLIC_DEMO_KEY ?? "";
export type Role = "owner" | "front_desk";

const ROLE_KEY = "slotpay_proto_role";
const TOKEN_KEY = "slotpay_dev_token"; // same slot the admin client already reads

export function currentRole(): Role {
  try { return localStorage.getItem(ROLE_KEY) === "front_desk" ? "front_desk" : "owner"; } catch { return "owner"; }
}

/** Gets a staff token from the API (prototype mode only) and stores it for the admin client. */
export async function prototypeLogin(role: Role = currentRole()): Promise<string | null> {
  try {
    const r = await fetch(`${API_BASE}/prototype/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }) });
    if (!r.ok) return null;
    const j = (await r.json()) as { token: string };
    try { localStorage.setItem(TOKEN_KEY, j.token); localStorage.setItem(ROLE_KEY, role); } catch { /* storage unavailable */ }
    return j.token;
  } catch { return null; }
}

export async function switchRole(role: Role): Promise<boolean> {
  return (await prototypeLogin(role)) !== null;
}

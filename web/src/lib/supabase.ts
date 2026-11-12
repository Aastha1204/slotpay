import { createClient } from "@supabase/supabase-js";

// Only NEXT_PUBLIC_* (anon key) values are allowed in the client bundle.
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://127.0.0.1:54321",
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "anon-placeholder",
);

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

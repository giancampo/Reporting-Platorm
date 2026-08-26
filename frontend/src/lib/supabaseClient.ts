import { createClient } from "@supabase/supabase-js";

// Vite exposes only VITE_-prefixed env vars to client code — anon key is
// safe to ship (RLS is the actual gate, action-plan.md §10); never put the
// service_role key here.
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  // eslint-disable-next-line no-console
  console.warn(
    "VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not set — copy frontend/.env.example to .env.local."
  );
}

export const supabase = createClient(SUPABASE_URL ?? "http://localhost:54321", SUPABASE_ANON_KEY ?? "");

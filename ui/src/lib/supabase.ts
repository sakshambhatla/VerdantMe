import { createClient, SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined;

/**
 * Supabase client instance.
 *
 * - **Production**: initialised from VITE_SUPABASE_URL + VITE_SUPABASE_PUBLISHABLE_KEY.
 * - **Dev mode** (env vars not set): `null` — the app skips all auth flows.
 */
export const supabase: SupabaseClient | null =
  supabaseUrl && supabaseKey ? createClient(supabaseUrl, supabaseKey) : null;

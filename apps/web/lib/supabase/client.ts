import { createBrowserClient } from "@supabase/ssr";
import { getRequiredSupabaseEnv } from "@/lib/supabase/env";

export function createClient() {
  const { url, anon } = getRequiredSupabaseEnv();
  return createBrowserClient(url, anon);
}

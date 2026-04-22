import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";
import { getRequiredSupabaseEnv } from "@/lib/supabase/env";

export function createClient() {
  const cookieStore = cookies();
  const { url, anon } = getRequiredSupabaseEnv("server");

  return createServerClient(url, anon, {
    cookies: {
      get(name: string) {
        return cookieStore.get(name)?.value;
      },
      set(name: string, value: string, options: CookieOptions) {
        try {
          cookieStore.set({ name, value, ...options });
        } catch {
          // Server components may not write cookies; middleware handles refresh.
        }
      },
      remove(name: string, options: CookieOptions) {
        try {
          cookieStore.set({ name, value: "", ...options });
        } catch {
          // See comment above.
        }
      },
    },
  });
}

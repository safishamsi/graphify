const MISSING_GUIDANCE =
  "Set them in the repo root .env, or let apps/web/next.config.js derive them from SUPABASE_URL and SUPABASE_ANON_KEY.";

function readSupabaseEnv(): { url: string | undefined; anon: string | undefined } {
  return {
    url: process.env.NEXT_PUBLIC_SUPABASE_URL,
    anon: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  };
}

export function getRequiredSupabaseEnv(context: "client" | "server" = "client") {
  const { url, anon } = readSupabaseEnv();
  if (!url || !anon) {
    const suffix = context === "server" ? " on the server" : "";
    throw new Error(
      `Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY${suffix}. ${MISSING_GUIDANCE}`,
    );
  }
  return { url, anon };
}

export function getOptionalSupabaseEnv() {
  const { url, anon } = readSupabaseEnv();
  if (!url || !anon) return null;
  return { url, anon };
}

export { MISSING_GUIDANCE };

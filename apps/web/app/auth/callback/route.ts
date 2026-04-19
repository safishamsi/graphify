import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { safeNext } from "@/lib/auth/redirects";
import { toAuthErrorInfo } from "@/lib/auth/errors";

/**
 * PKCE / OAuth-style callback. Supabase email links may send `?code=` (PKCE)
 * or `?token_hash=` (verifyOtp). The latter is handled by /auth/confirm; this
 * route exclusively exchanges `code` for a session.
 *
 * `next` is sanitized via `safeNext` to prevent open redirects.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const errorParam = url.searchParams.get("error_description") ?? url.searchParams.get("error");
  const next = safeNext(url.searchParams.get("next"));

  // Surface provider errors (e.g. user denied consent) without crashing.
  if (errorParam) {
    const errUrl = new URL("/auth/sign-in", url.origin);
    errUrl.searchParams.set("error", errorParam);
    return NextResponse.redirect(errUrl);
  }

  if (code) {
    const supabase = createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      const info = toAuthErrorInfo(error);
      const errUrl = new URL("/auth/sign-in", url.origin);
      errUrl.searchParams.set("error", info.message);
      return NextResponse.redirect(errUrl);
    }
  }

  return NextResponse.redirect(new URL(next, url.origin));
}

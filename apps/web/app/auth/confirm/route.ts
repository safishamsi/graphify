import { NextResponse, type NextRequest } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/server";
import { safeNext } from "@/lib/auth/redirects";
import { toAuthErrorInfo } from "@/lib/auth/errors";

/**
 * Server-side handler for Supabase's modern email-link flow that uses
 * `token_hash` + `type` instead of the older `?code=` exchange.
 * Supabase emits links shaped like:
 *   /auth/confirm?token_hash=...&type=signup&next=/orgs
 */
export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const token_hash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type") as EmailOtpType | null;
  const next = safeNext(url.searchParams.get("next"));

  const fail = (message: string, code?: string) => {
    const target =
      code === "otp_expired" || /expired/i.test(message)
        ? "/auth/forgot-password"
        : "/auth/sign-in";
    const err = new URL(target, url.origin);
    err.searchParams.set("error", code === "otp_expired" ? "expired" : message);
    return NextResponse.redirect(err);
  };

  if (!token_hash || !type) {
    return fail("Missing or invalid verification link.");
  }

  const supabase = createClient();
  const { error } = await supabase.auth.verifyOtp({ type, token_hash });
  if (error) {
    const info = toAuthErrorInfo(error);
    return fail(info.message, info.code);
  }

  // Recovery links must land on /auth/reset-password — never let them
  // bypass that screen by passing `?next=` from the email template.
  if (type === "recovery") {
    return NextResponse.redirect(new URL("/auth/reset-password", url.origin));
  }
  return NextResponse.redirect(new URL(next, url.origin));
}

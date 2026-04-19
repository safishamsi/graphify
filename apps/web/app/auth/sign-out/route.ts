import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { safeNext } from "@/lib/auth/redirects";

/**
 * POST /auth/sign-out — clears the Supabase session cookies and redirects
 * back to the marketing home (or `?next=`). Use a form POST so the browser
 * sends cookies and the action survives JS-disabled clients.
 */
export async function POST(request: NextRequest) {
  const supabase = createClient();
  await supabase.auth.signOut();

  const next = safeNext(new URL(request.url).searchParams.get("next"), "/");
  return NextResponse.redirect(new URL(next, request.url), { status: 303 });
}

export async function GET(request: NextRequest) {
  return POST(request);
}

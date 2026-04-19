"use client";

import { createClient } from "@/lib/supabase/client";
import { toAuthErrorInfo, type AuthErrorInfo } from "./errors";
import { safeNext } from "./redirects";

/**
 * Thin, typed wrappers over Supabase auth. Each returns a discriminated
 * union — call sites never have to think about exception flow.
 */
export type AuthResult<T = void> =
  | { ok: true; data: T }
  | { ok: false; error: AuthErrorInfo };

function origin(): string {
  if (typeof window === "undefined") return "";
  return window.location.origin;
}

async function guard<T>(fn: () => Promise<T>): Promise<AuthResult<T>> {
  try {
    const data = await fn();
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: toAuthErrorInfo(err) };
  }
}

/* ------------------------------------------------------------------------- *
 * Sign up                                                                   *
 * ------------------------------------------------------------------------- */

export type SignUpInput = {
  email: string;
  password: string;
  displayName?: string;
};

export async function signUpWithPassword(
  input: SignUpInput,
): Promise<AuthResult<{ requiresConfirmation: boolean }>> {
  return guard(async () => {
    const supabase = createClient();
    const { data, error } = await supabase.auth.signUp({
      email: input.email,
      password: input.password,
      options: {
        data: input.displayName ? { display_name: input.displayName } : undefined,
        emailRedirectTo: `${origin()}/auth/callback?next=/orgs`,
      },
    });
    if (error) throw error;
    return { requiresConfirmation: !data.session };
  });
}

/* ------------------------------------------------------------------------- *
 * Sign in                                                                   *
 * ------------------------------------------------------------------------- */

export type SignInInput = { email: string; password: string };

export async function signInWithPassword(
  input: SignInInput,
): Promise<AuthResult<void>> {
  return guard(async () => {
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword(input);
    if (error) throw error;
  });
}

export async function sendMagicLink(
  email: string,
  next: string = "/orgs",
): Promise<AuthResult<void>> {
  return guard(async () => {
    const supabase = createClient();
    const target = safeNext(next);
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${origin()}/auth/callback?next=${encodeURIComponent(target)}`,
        shouldCreateUser: true,
      },
    });
    if (error) throw error;
  });
}

export async function verifyEmailOtp(
  email: string,
  token: string,
): Promise<AuthResult<void>> {
  return guard(async () => {
    const supabase = createClient();
    const { error } = await supabase.auth.verifyOtp({
      email,
      token,
      type: "email",
    });
    if (error) throw error;
  });
}

/* ------------------------------------------------------------------------- *
 * Password reset                                                            *
 * ------------------------------------------------------------------------- */

export async function requestPasswordReset(
  email: string,
): Promise<AuthResult<void>> {
  return guard(async () => {
    const supabase = createClient();
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${origin()}/auth/callback?next=/auth/reset-password`,
    });
    if (error) throw error;
  });
}

export async function updatePassword(
  newPassword: string,
): Promise<AuthResult<void>> {
  return guard(async () => {
    const supabase = createClient();
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw error;
  });
}

/* ------------------------------------------------------------------------- *
 * Misc                                                                      *
 * ------------------------------------------------------------------------- */

export async function resendConfirmation(
  email: string,
): Promise<AuthResult<void>> {
  return guard(async () => {
    const supabase = createClient();
    const { error } = await supabase.auth.resend({
      type: "signup",
      email,
      options: { emailRedirectTo: `${origin()}/auth/callback?next=/orgs` },
    });
    if (error) throw error;
  });
}

export async function signOut(): Promise<AuthResult<void>> {
  return guard(async () => {
    const supabase = createClient();
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
  });
}

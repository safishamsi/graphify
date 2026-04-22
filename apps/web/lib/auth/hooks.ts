"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";

/* ------------------------------------------------------------------------- *
 * Recovery-session gate                                                     *
 * ------------------------------------------------------------------------- */

/**
 * Used by /auth/reset-password. Once the auth probe resolves and the user
 * isn't authenticated, redirect them back to the request screen with an
 * `expired` flag so we can show the right message.
 */
export function useRequireRecoverySession(options?: {
  redirectTo?: string;
  /** Pass `true` once an action succeeds so the redirect doesn't fire on the success state. */
  bypass?: boolean;
}): { status: "loading" | "ready" | "redirecting" } {
  const { status } = useAuth();
  const router = useRouter();
  const fired = useRef(false);

  const target = options?.redirectTo ?? "/auth/forgot-password?error=expired";
  const bypass = options?.bypass ?? false;

  useEffect(() => {
    if (bypass) return;
    if (status === "unauthenticated" && !fired.current) {
      fired.current = true;
      router.replace(target);
    }
  }, [status, target, router, bypass]);

  if (status === "loading") return { status: "loading" };
  if (status === "unauthenticated") return { status: "redirecting" };
  return { status: "ready" };
}

/* ------------------------------------------------------------------------- *
 * Countdown                                                                 *
 * ------------------------------------------------------------------------- */

/**
 * Counts down a timestamp (epoch ms). Returns the integer seconds remaining
 * and an `expired` boolean. Stable across renders — only flips when the
 * second value crosses an integer boundary.
 */
export function useCountdown(targetMs: number | null): {
  secondsLeft: number;
  expired: boolean;
} {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!targetMs) return;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [targetMs]);

  if (!targetMs) return { secondsLeft: 0, expired: true };
  const ms = Math.max(0, targetMs - now);
  return { secondsLeft: Math.ceil(ms / 1000), expired: ms <= 0 };
}

/* ------------------------------------------------------------------------- *
 * Rate-limit lock                                                           *
 * ------------------------------------------------------------------------- */

/**
 * Tracks a rolling cooldown lock for a form. Call `lockFor(seconds)` after
 * a 429-class response and read `secondsLeft` to disable the submit button
 * + render a banner. Resets automatically when the timer hits zero.
 */
export function useRateLimit(): {
  secondsLeft: number;
  isLimited: boolean;
  lockFor: (seconds: number) => void;
  clear: () => void;
} {
  const [until, setUntil] = useState<number | null>(null);
  const { secondsLeft, expired } = useCountdown(until);

  const lockFor = useCallback((seconds: number) => {
    if (!Number.isFinite(seconds) || seconds <= 0) return;
    setUntil(Date.now() + seconds * 1000);
  }, []);

  const clear = useCallback(() => setUntil(null), []);

  useEffect(() => {
    if (expired && until !== null) setUntil(null);
  }, [expired, until]);

  return {
    secondsLeft: until ? secondsLeft : 0,
    isLimited: Boolean(until) && !expired,
    lockFor,
    clear,
  };
}

/* ------------------------------------------------------------------------- *
 * Resend cooldown (e.g. "send another magic link")                          *
 * ------------------------------------------------------------------------- */

/**
 * Mirror of `useRateLimit` scoped to one user-initiated resend action.
 * Returns helpers that disable the resend button until the cooldown lapses.
 */
export function useResendCooldown(defaultSeconds = 30): {
  secondsLeft: number;
  canResend: boolean;
  trigger: (seconds?: number) => void;
} {
  const [until, setUntil] = useState<number | null>(null);
  const { secondsLeft, expired } = useCountdown(until);

  const trigger = useCallback(
    (seconds?: number) => {
      const n = seconds && seconds > 0 ? seconds : defaultSeconds;
      setUntil(Date.now() + n * 1000);
    },
    [defaultSeconds],
  );

  useEffect(() => {
    if (expired && until !== null) setUntil(null);
  }, [expired, until]);

  return {
    secondsLeft: until ? secondsLeft : 0,
    canResend: !until || expired,
    trigger,
  };
}

/* ------------------------------------------------------------------------- *
 * Reduced motion                                                            *
 * ------------------------------------------------------------------------- */

/** Live-updating reading of `prefers-reduced-motion`. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return reduced;
}

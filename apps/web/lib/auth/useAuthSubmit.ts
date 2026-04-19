"use client";

import { useCallback, useState } from "react";
import type { AuthResult } from "./actions";
import type { AuthErrorInfo, AuthErrorField } from "./errors";
import { useRateLimit } from "./hooks";

type FieldErrors = Partial<Record<AuthErrorField, string>>;

export type AuthSubmitState = {
  /** Set while the action is in flight. */
  submitting: boolean;
  /** Form-level error (banner). Cleared on every new submit. */
  formError: AuthErrorInfo | null;
  /** Field-level errors, keyed by input name. */
  fieldErrors: FieldErrors;
  /** Number of seconds the user must wait before retrying (0 if not limited). */
  cooldownSeconds: number;
  isRateLimited: boolean;
};

export type AuthSubmitApi = AuthSubmitState & {
  /** Run an async auth action; routes errors into the right slot. */
  run: <T>(action: () => Promise<AuthResult<T>>) => Promise<AuthResult<T>>;
  /** Imperatively clear the form-level error (e.g. on input change). */
  clearFormError: () => void;
  /** Imperatively clear a single field error (e.g. on its onChange). */
  clearFieldError: (field: AuthErrorField) => void;
  /** Reset everything (used by "use different email" buttons). */
  reset: () => void;
};

/**
 * Centralized submit state for auth forms. Handles:
 *   - in-flight `submitting` flag
 *   - form-level vs field-level error placement (driven by `error.field`)
 *   - rate-limit lock with countdown when Supabase returns 429
 *   - reset between attempts
 *
 * Forms call `run(() => signInWithPassword(...))` and read the rest.
 */
export function useAuthSubmit(): AuthSubmitApi {
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<AuthErrorInfo | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const rate = useRateLimit();

  const clearFormError = useCallback(() => setFormError(null), []);
  const clearFieldError = useCallback((field: AuthErrorField) => {
    setFieldErrors((prev) => {
      if (!prev[field]) return prev;
      const { [field]: _omit, ...rest } = prev;
      void _omit;
      return rest;
    });
  }, []);

  const reset = useCallback(() => {
    setSubmitting(false);
    setFormError(null);
    setFieldErrors({});
    rate.clear();
  }, [rate]);

  const run = useCallback(
    async <T,>(action: () => Promise<AuthResult<T>>): Promise<AuthResult<T>> => {
      if (rate.isLimited) {
        return {
          ok: false,
          error: {
            kind: "rate_limit",
            message: `Please wait ${rate.secondsLeft}s before trying again.`,
            retryAfterSeconds: rate.secondsLeft,
          },
        };
      }
      setSubmitting(true);
      setFormError(null);
      setFieldErrors({});
      const result = await action();
      setSubmitting(false);

      if (!result.ok) {
        const err = result.error;
        if (err.kind === "rate_limit" && err.retryAfterSeconds) {
          rate.lockFor(err.retryAfterSeconds);
        }
        if (err.field) {
          setFieldErrors({ [err.field]: err.message });
        } else {
          setFormError(err);
        }
      }
      return result;
    },
    [rate],
  );

  return {
    submitting,
    formError,
    fieldErrors,
    cooldownSeconds: rate.secondsLeft,
    isRateLimited: rate.isLimited,
    run,
    clearFormError,
    clearFieldError,
    reset,
  };
}

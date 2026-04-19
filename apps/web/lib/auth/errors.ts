import { AuthError } from "@supabase/supabase-js";

/**
 * Categorical buckets the UI branches on. Most call sites only care about
 * `kind` to decide whether to show inline / banner / countdown UI.
 */
export type AuthErrorKind =
  | "credentials"
  | "validation"
  | "rate_limit"
  | "network"
  | "expired"
  | "conflict"
  | "not_found"
  | "server"
  | "unknown";

/** A field hint lets a form pin the error to a specific input. */
export type AuthErrorField = "email" | "password" | "code";

export type AuthErrorInfo = {
  kind: AuthErrorKind;
  message: string;
  /** Original Supabase error code, when available. Useful for telemetry. */
  code?: string;
  /** HTTP status if the error originated from an AuthApiError. */
  status?: number;
  /** Hint for forms — if set, render the message under that input. */
  field?: AuthErrorField;
  /** Seconds the user should wait before retrying. Set for rate_limit. */
  retryAfterSeconds?: number;
};

/** Convenience builder used by tests + non-Supabase code paths. */
export function makeAuthError(
  kind: AuthErrorKind,
  message: string,
  extras: Partial<AuthErrorInfo> = {},
): AuthErrorInfo {
  return { kind, message, ...extras };
}

const RATE_LIMIT_RE = /(?:after|in|wait)\s+(\d{1,4})\s*(seconds?|s|minutes?|m)?/i;

/** Pull "after 60 seconds" out of Supabase rate-limit messages. */
function extractRetryAfterSeconds(message: string): number | undefined {
  const m = RATE_LIMIT_RE.exec(message);
  if (!m) return undefined;
  const n = Number.parseInt(m[1], 10);
  if (!Number.isFinite(n)) return undefined;
  const unit = (m[2] ?? "s").toLowerCase();
  return unit.startsWith("m") ? n * 60 : n;
}

/**
 * Map raw Supabase auth errors into a structured, operator-friendly shape.
 * Switches on `code` first because messages drift across versions.
 */
export function toAuthErrorInfo(err: unknown): AuthErrorInfo {
  if (!err) return makeAuthError("unknown", "Something went wrong. Please try again.");

  // Browser network failures — fetch throws TypeError("Failed to fetch")
  if (err instanceof TypeError && /fetch/i.test(err.message)) {
    return makeAuthError(
      "network",
      "Can't reach the auth server. Check your connection and try again.",
    );
  }

  if (err instanceof AuthError) {
    const code = (err as unknown as { code?: string }).code;
    const status = (err as unknown as { status?: number }).status;
    const baseMsg = err.message ?? "Authentication failed.";

    switch (code) {
      case "invalid_credentials":
      case "invalid_grant":
        return {
          kind: "credentials",
          code,
          status,
          message: "Email or password is incorrect.",
        };
      case "email_not_confirmed":
        return {
          kind: "expired",
          code,
          status,
          field: "email",
          message: "Please confirm your email before signing in.",
        };
      case "user_not_found":
        return {
          kind: "not_found",
          code,
          status,
          field: "email",
          message: "No account found for this email.",
        };
      case "user_already_exists":
      case "email_exists":
        return {
          kind: "conflict",
          code,
          status,
          field: "email",
          message: "An account with this email already exists.",
        };
      case "weak_password":
        return {
          kind: "validation",
          code,
          status,
          field: "password",
          message:
            "Password is too weak. Use 8+ characters with mixed case and a number.",
        };
      case "same_password":
        return {
          kind: "validation",
          code,
          status,
          field: "password",
          message: "Pick a different password from your current one.",
        };
      case "over_email_send_rate_limit":
      case "over_request_rate_limit":
        return {
          kind: "rate_limit",
          code,
          status,
          retryAfterSeconds: extractRetryAfterSeconds(baseMsg) ?? 60,
          message:
            "Too many attempts. Please wait a moment before trying again.",
        };
      case "otp_expired":
        return {
          kind: "expired",
          code,
          status,
          field: "code",
          message: "This code expired. Request a new one.",
        };
      case "otp_disabled":
        return {
          kind: "server",
          code,
          status,
          message: "One-time passcodes aren't enabled for this project.",
        };
      case "session_not_found":
      case "no_authorization":
        return {
          kind: "expired",
          code,
          status,
          message: "Your session expired. Please sign in again.",
        };
      default:
        // Status-driven fallback when we don't know the code.
        if (status === 429) {
          return {
            kind: "rate_limit",
            code,
            status,
            retryAfterSeconds: extractRetryAfterSeconds(baseMsg) ?? 60,
            message: "Too many attempts. Please wait a moment before trying again.",
          };
        }
        if (status && status >= 500) {
          return {
            kind: "server",
            code,
            status,
            message: "Auth service is having trouble. Try again in a moment.",
          };
        }
        return { kind: "unknown", code, status, message: baseMsg };
    }
  }

  if (err instanceof Error) return makeAuthError("unknown", err.message);
  return makeAuthError("unknown", "Something went wrong. Please try again.");
}

/** Back-compat helper for call sites that only need a string. */
export function friendlyAuthError(err: unknown): string {
  return toAuthErrorInfo(err).message;
}

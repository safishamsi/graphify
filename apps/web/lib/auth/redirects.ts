/**
 * Sanitize a `?next=` redirect target so we never bounce users to an external
 * origin (open-redirect mitigation) or to a JS pseudo-URL.
 *
 * Accepts only same-origin paths starting with `/` and rejects:
 *   - Empty / null / non-string values
 *   - Protocol-relative URLs ("//evil.com")
 *   - Absolute URLs ("https://evil.com")
 *   - JS pseudo-protocols
 *   - Backslash tricks ("/\\evil.com" — becomes "//evil.com" in some browsers)
 *
 * Returns the input when it's safe, otherwise `fallback`.
 */
export function safeNext(
  value: string | null | undefined,
  fallback = "/orgs",
): string {
  if (typeof value !== "string") return fallback;
  const trimmed = value.trim();
  if (!trimmed) return fallback;

  // Must be a same-origin path.
  if (!trimmed.startsWith("/")) return fallback;
  // Reject protocol-relative URLs.
  if (trimmed.startsWith("//")) return fallback;
  // Reject backslash tricks.
  if (trimmed.startsWith("/\\")) return fallback;
  // Reject obviously malformed schemes embedded in the path.
  if (/^\/(?:[a-z][a-z0-9+.-]*):/i.test(trimmed)) return fallback;
  if (/^\s*javascript:/i.test(trimmed)) return fallback;

  // Disallow auth pages as redirect targets — there's no sensible reason to
  // bounce a user back into the auth flow they just completed.
  if (trimmed === "/auth" || trimmed.startsWith("/auth/")) return fallback;

  return trimmed;
}

/**
 * URL-encode `safeNext` output as a `?next=` query string fragment.
 * Returns "" when the destination is the default (no query needed).
 */
export function nextQueryString(
  value: string | null | undefined,
  fallback = "/orgs",
): string {
  const target = safeNext(value, fallback);
  if (target === fallback) return "";
  return `?next=${encodeURIComponent(target)}`;
}

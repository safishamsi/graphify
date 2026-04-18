const apiBase = () => {
  const base = process.env.NEXT_PUBLIC_DEPOS_API_URL?.replace(/\/$/, "");
  return base ?? "";
};

export class DeposApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: string,
  ) {
    super(message);
    this.name = "DeposApiError";
  }
}

export async function deposFetch(
  path: string,
  accessToken: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<Response> {
  const base = apiBase();
  if (!base) {
    throw new DeposApiError("NEXT_PUBLIC_DEPOS_API_URL is not set", 503);
  }
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const { json, ...rest } = init;
  const body = json !== undefined ? JSON.stringify(json) : rest.body;
  const res = await fetch(url, { ...rest, headers, body });
  if (!res.ok) {
    const text = await res.text();
    throw new DeposApiError(text || res.statusText, res.status, text);
  }
  return res;
}

export async function deposJson<T>(path: string, accessToken: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const res = await deposFetch(path, accessToken, init);
  return res.json() as Promise<T>;
}

/** User-facing copy for API failures (401/403 per depOS web plan). */
export function humanizeDeposApiError(e: unknown, maxLen = 800): string {
  if (e instanceof DeposApiError) {
    if (e.status === 401) {
      return "Session expired or not signed in. Sign in again.";
    }
    if (e.status === 403) {
      return "You don't have permission for this action.";
    }
    if (e.status === 503) {
      return "depOS API URL is not configured (set NEXT_PUBLIC_DEPOS_API_URL).";
    }
    const raw = e.message?.trim() || e.body?.trim() || "Request failed";
    return raw.length > maxLen ? `${raw.slice(0, maxLen)}…` : raw;
  }
  if (e instanceof Error) {
    const m = e.message.trim();
    return m.length > maxLen ? `${m.slice(0, maxLen)}…` : m;
  }
  return "Request failed";
}

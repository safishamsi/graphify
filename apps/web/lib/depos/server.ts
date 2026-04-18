import { createClient } from "@/lib/supabase/server";
import { deposJson } from "@/lib/depos/api";
import type { IntelligenceRunDetailResponse, MeResponse } from "@/lib/depos/types";

export async function getSessionAccessToken(): Promise<string | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

export async function requireSessionAccessToken(): Promise<string> {
  const t = await getSessionAccessToken();
  if (!t) {
    throw new Error("Not authenticated");
  }
  return t;
}

export async function fetchMe(accessToken: string): Promise<MeResponse> {
  return deposJson<MeResponse>("/v1/me", accessToken);
}

export async function fetchIntelligenceRunDetail(
  accessToken: string,
  orgSlug: string,
  runId: string,
): Promise<IntelligenceRunDetailResponse> {
  return deposJson<IntelligenceRunDetailResponse>(
    `/v1/orgs/${encodeURIComponent(orgSlug)}/intelligence/runs/${runId}`,
    accessToken,
  );
}

export async function fetchApiHealth(): Promise<{ ok: boolean; status?: string }> {
  const base = process.env.NEXT_PUBLIC_DEPOS_API_URL?.replace(/\/$/, "");
  if (!base) return { ok: false, status: "unset" };
  try {
    const res = await fetch(`${base}/health`, { next: { revalidate: 0 } });
    const data = (await res.json().catch(() => ({}))) as { status?: string };
    return { ok: res.ok, status: data.status ?? (res.ok ? "ok" : "error") };
  } catch {
    return { ok: false, status: "error" };
  }
}

export { deposJson, DeposApiError } from "@/lib/depos/api";

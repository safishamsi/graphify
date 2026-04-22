import type { SupabaseClient } from "@supabase/supabase-js";
import type { IntelligenceAnalysisMode, IntelligenceRunStatus } from "@/lib/depos/types";

export async function getOrgIdBySlug(supabase: SupabaseClient, slug: string): Promise<string | null> {
  const { data, error } = await supabase.from("organizations").select("id").eq("slug", slug).maybeSingle();
  if (error || !data) return null;
  return (data as { id: string }).id;
}

export type GraphSnapshotRow = {
  id: string;
  repo_slug: string;
  git_sha: string;
  status: string;
  byte_size: number | null;
  content_sha256: string | null;
  created_at: string;
};

export async function listGraphSnapshots(
  supabase: SupabaseClient,
  orgId: string,
): Promise<GraphSnapshotRow[]> {
  const { data, error } = await supabase
    .from("graph_snapshots")
    .select("id, repo_slug, git_sha, status, byte_size, content_sha256, created_at")
    .eq("org_id", orgId)
    .order("created_at", { ascending: false })
    .limit(100);
  if (error || !data) return [];
  return data as GraphSnapshotRow[];
}

export type CISignalRow = {
  id: number;
  repo_slug: string;
  head_sha: string;
  check_conclusion: string;
  overlap_score: number;
  predicted_files: string[];
  created_at: string;
  graph_snapshot_id: string | null;
};

export async function listCISignals(
  supabase: SupabaseClient,
  orgId: string,
  repoSlug?: string,
): Promise<CISignalRow[]> {
  let q = supabase
    .from("ci_signals")
    .select("id, repo_slug, head_sha, check_conclusion, overlap_score, predicted_files, created_at, graph_snapshot_id")
    .eq("org_id", orgId)
    .order("created_at", { ascending: false })
    .limit(200);
  if (repoSlug) {
    q = q.eq("repo_slug", repoSlug);
  }
  const { data, error } = await q;
  if (error || !data) return [];
  return data as CISignalRow[];
}

export type IntelligenceRunRow = {
  id: string;
  repo_slug: string;
  status: IntelligenceRunStatus;
  analysis_mode: IntelligenceAnalysisMode;
  started_at: string;
  finished_at: string | null;
};

export async function listIntelligenceRuns(
  supabase: SupabaseClient,
  orgId: string,
): Promise<IntelligenceRunRow[]> {
  const { data, error } = await supabase
    .from("intelligence_runs")
    .select("id, repo_slug, status, analysis_mode, started_at, finished_at")
    .eq("org_id", orgId)
    .order("started_at", { ascending: false })
    .limit(100);
  if (error || !data) return [];
  return data as IntelligenceRunRow[];
}

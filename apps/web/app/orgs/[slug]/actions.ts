"use server";

import { revalidatePath } from "next/cache";
import { deposJson, humanizeDeposApiError } from "@/lib/depos/api";
import { requireSessionAccessToken } from "@/lib/depos/server";
import type {
  CheckConclusion,
  DriftSnapshotsResponse,
  FederationSnapshotsResponse,
  GraphSnapshotPrepareResponse,
  IntelligenceRunCreateRequest,
  LLMGraphExport,
  PostCIResult,
} from "@/lib/depos/types";

export async function toggleRepoAction(
  orgSlug: string,
  repoSlug: string,
  enabled_for_analysis: boolean,
  include_in_federated: boolean,
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const token = await requireSessionAccessToken();
    await deposJson("/v1/repos/toggle", token, {
      method: "PATCH",
      json: { org_slug: orgSlug, repo_slug: repoSlug, enabled_for_analysis, include_in_federated },
    });
    revalidatePath(`/orgs/${orgSlug}/repos`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: humanizeDeposApiError(e, 400) };
  }
}

export async function prepareGraphSnapshotAction(
  orgSlug: string,
  repo_slug: string,
  git_sha: string,
): Promise<{ ok: true; data: GraphSnapshotPrepareResponse } | { ok: false; error: string }> {
  try {
    const token = await requireSessionAccessToken();
    const data = await deposJson<GraphSnapshotPrepareResponse>(
      `/v1/orgs/${encodeURIComponent(orgSlug)}/graph-snapshots/prepare`,
      token,
      { method: "POST", json: { repo_slug, git_sha } },
    );
    revalidatePath(`/orgs/${orgSlug}/snapshots`);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: humanizeDeposApiError(e, 400) };
  }
}

export async function completeGraphSnapshotAction(
  orgSlug: string,
  snapshot_id: string,
  expected_sha256?: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const token = await requireSessionAccessToken();
    await deposJson(`/v1/orgs/${encodeURIComponent(orgSlug)}/graph-snapshots/${snapshot_id}/complete`, token, {
      method: "POST",
      json: { expected_sha256: expected_sha256 || null },
    });
    revalidatePath(`/orgs/${orgSlug}/snapshots`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: humanizeDeposApiError(e, 400) };
  }
}

export async function runAnalyzeAction(
  orgSlug: string,
  payload: {
    repo_slug: string;
    graph_snapshot_id: string;
    changed_files: string[];
    hop_depth: number;
    sarif: Record<string, unknown> | null;
    codeowners_content: string | null;
  },
): Promise<{ ok: true; data: LLMGraphExport } | { ok: false; error: string }> {
  try {
    const token = await requireSessionAccessToken();
    const data = await deposJson<LLMGraphExport>("/v1/ci/analyze", token, {
      method: "POST",
      json: {
        org_slug: orgSlug,
        repo_slug: payload.repo_slug,
        graph_snapshot_id: payload.graph_snapshot_id,
        changed_files: payload.changed_files,
        hop_depth: payload.hop_depth,
        sarif: payload.sarif,
        codeowners_content: payload.codeowners_content,
      },
    });
    revalidatePath(`/orgs/${orgSlug}/analyze`);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: humanizeDeposApiError(e, 800) };
  }
}

export async function runPostciAction(
  orgSlug: string,
  payload: {
    repo_slug: string;
    head_sha: string;
    predicted_files: string[];
    failed_paths: string[];
    check_conclusion: CheckConclusion;
    graph_snapshot_id?: string | null;
  },
): Promise<{ ok: true; data: PostCIResult } | { ok: false; error: string }> {
  try {
    const token = await requireSessionAccessToken();
    const data = await deposJson<PostCIResult>("/v1/ci/postci", token, {
      method: "POST",
      json: {
        org_slug: orgSlug,
        repo_slug: payload.repo_slug,
        head_sha: payload.head_sha,
        predicted_files: payload.predicted_files,
        failed_paths: payload.failed_paths,
        check_conclusion: payload.check_conclusion,
        graph_snapshot_id: payload.graph_snapshot_id || null,
      },
    });
    revalidatePath(`/orgs/${orgSlug}/postci`);
    revalidatePath(`/orgs/${orgSlug}/ci`);
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: humanizeDeposApiError(e, 800) };
  }
}

export async function runFederationAction(
  orgSlug: string,
  snapshot_ids: Record<string, string>,
  allowed: string[] | null,
): Promise<{ ok: true; data: FederationSnapshotsResponse } | { ok: false; error: string }> {
  try {
    const token = await requireSessionAccessToken();
    const data = await deposJson<FederationSnapshotsResponse>("/v1/federation/snapshots", token, {
      method: "POST",
      json: { org_slug: orgSlug, snapshot_ids, allowed },
    });
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: humanizeDeposApiError(e, 800) };
  }
}

export async function runDriftAction(
  orgSlug: string,
  graph_a_snapshot_id: string,
  graph_b_snapshot_id: string,
): Promise<{ ok: true; data: DriftSnapshotsResponse } | { ok: false; error: string }> {
  try {
    const token = await requireSessionAccessToken();
    const data = await deposJson<DriftSnapshotsResponse>("/v1/drift/snapshots", token, {
      method: "POST",
      json: {
        org_slug: orgSlug,
        graph_a_snapshot_id,
        graph_b_snapshot_id,
      },
    });
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: humanizeDeposApiError(e, 800) };
  }
}

export async function createIntelligenceRunAction(
  orgSlug: string,
  body: IntelligenceRunCreateRequest,
): Promise<{ ok: true; run_id: string } | { ok: false; error: string }> {
  try {
    const token = await requireSessionAccessToken();
    const res = await deposJson<{ run_id: string; findings: number }>(
      `/v1/orgs/${encodeURIComponent(orgSlug)}/intelligence/runs`,
      token,
      { method: "POST", json: body },
    );
    revalidatePath(`/orgs/${orgSlug}/intelligence`);
    return { ok: true, run_id: res.run_id };
  } catch (e) {
    return { ok: false, error: humanizeDeposApiError(e, 800) };
  }
}

import { createClient } from "@/lib/supabase/server";
import { deposJson } from "@/lib/depos/api";
import { requireSessionAccessToken } from "@/lib/depos/server";
import { getOrgIdBySlug, listGraphSnapshots } from "@/lib/supabase/queries";
import type { ReposListResponse } from "@/lib/depos/types";
import { AnalyzeLabClient } from "@/components/analyze/AnalyzeLabClient";

type Props = { params: { slug: string } };

export default async function AnalyzePage({ params }: Props) {
  const token = await requireSessionAccessToken();
  const supabase = createClient();
  const orgId = await getOrgIdBySlug(supabase, params.slug);

  let repos: ReposListResponse["repos"] = [];
  try {
    const data = await deposJson<ReposListResponse>(`/v1/orgs/${encodeURIComponent(params.slug)}/repos`, token);
    repos = data.repos ?? [];
  } catch {
    repos = [];
  }

  const allSnaps = orgId ? await listGraphSnapshots(supabase, orgId) : [];
  const readySnapshots = allSnaps.filter((s) => s.status === "ready");

  return (
    <div>
      <h1 className="font-display page-title">Analyze</h1>
      <p className="page-desc">
        Runs <code className="font-mono">POST /v1/ci/analyze</code> against a ready graph snapshot for this org.
      </p>
      {repos.length === 0 ? (
        <p className="empty-state">Add repositories under Repositories first.</p>
      ) : (
        <AnalyzeLabClient orgSlug={params.slug} repos={repos} readySnapshots={readySnapshots} />
      )}
    </div>
  );
}

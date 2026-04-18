import { createClient } from "@/lib/supabase/server";
import { deposJson } from "@/lib/depos/api";
import { requireSessionAccessToken } from "@/lib/depos/server";
import { getOrgIdBySlug, listGraphSnapshots } from "@/lib/supabase/queries";
import type { ReposListResponse } from "@/lib/depos/types";
import { PostciForm } from "@/components/postci/PostciForm";

type Props = { params: { slug: string } };

export default async function PostciPage({ params }: Props) {
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

  const snapshots = orgId ? await listGraphSnapshots(supabase, orgId) : [];

  return (
    <div>
      <h1 className="font-display page-title">Post-CI</h1>
      <p className="page-desc">Correlates predicted blast files with failed paths and persists a CI signal.</p>
      {repos.length === 0 ? (
        <p className="empty-state">No repositories configured.</p>
      ) : (
        <PostciForm orgSlug={params.slug} repos={repos} snapshots={snapshots} />
      )}
    </div>
  );
}

import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { deposJson } from "@/lib/depos/api";
import { fetchMe, requireSessionAccessToken } from "@/lib/depos/server";
import { isOrgAdmin } from "@/lib/depos/roles";
import { getOrgIdBySlug, listIntelligenceRuns } from "@/lib/supabase/queries";
import type { ReposListResponse } from "@/lib/depos/types";
import { NewRunForm } from "@/components/intelligence/NewRunForm";

type Props = { params: { slug: string } };

export default async function IntelligencePage({ params }: Props) {
  const token = await requireSessionAccessToken();
  const me = await fetchMe(token);
  const admin = isOrgAdmin(me.memberships ?? [], params.slug);

  const supabase = createClient();
  const orgId = await getOrgIdBySlug(supabase, params.slug);
  const runs = orgId ? await listIntelligenceRuns(supabase, orgId) : [];

  let repos: ReposListResponse["repos"] = [];
  try {
    const data = await deposJson<ReposListResponse>(`/v1/orgs/${encodeURIComponent(params.slug)}/repos`, token);
    repos = data.repos ?? [];
  } catch {
    repos = [];
  }

  return (
    <div>
      <h1 className="font-display page-title">Intelligence</h1>
      <p className="page-desc">Runs and findings stored for your org. List reads from Postgres (RLS); detail uses the API.</p>

      {admin && repos.length > 0 ? <NewRunForm orgSlug={params.slug} repos={repos} /> : null}
      {admin && repos.length === 0 ? (
        <p className="text-muted">Add a repository before creating a run (admin).</p>
      ) : null}
      {!admin ? <p className="text-muted">New runs: owners and admins only.</p> : null}

      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ fontSize: "1rem", color: "var(--fg-muted)", marginBottom: "0.75rem" }}>Runs</h2>
        {!orgId ? (
          <p className="empty-state">Could not resolve organization.</p>
        ) : runs.length === 0 ? (
          <p className="empty-state">No intelligence runs yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Repo</th>
                  <th>Mode</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td className="font-mono" style={{ fontSize: "0.75rem" }}>
                      {new Date(r.started_at).toLocaleString()}
                    </td>
                    <td className="font-mono">{r.repo_slug}</td>
                    <td>{r.analysis_mode}</td>
                    <td>
                      <span className="badge">{r.status}</span>
                    </td>
                    <td>
                      <Link href={`/orgs/${params.slug}/intelligence/${r.id}`}>Open</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

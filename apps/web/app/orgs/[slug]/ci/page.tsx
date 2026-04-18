import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { getOrgIdBySlug, listCISignals } from "@/lib/supabase/queries";

type Props = {
  params: { slug: string };
  searchParams: { repo?: string };
};

export default async function CiSignalsPage({ params, searchParams }: Props) {
  const supabase = createClient();
  const orgId = await getOrgIdBySlug(supabase, params.slug);
  const repoFilter = searchParams.repo?.trim() || undefined;
  const rows = orgId ? await listCISignals(supabase, orgId, repoFilter) : [];

  return (
    <div>
      <h1 className="font-display page-title">CI signals</h1>
      <p className="page-desc">Rows from Postgres (<code className="font-mono">ci_signals</code>) visible to org members via RLS.</p>

      <p className="text-muted" style={{ marginBottom: "1rem" }}>
        Filter:{" "}
        <Link href={`/orgs/${params.slug}/ci`} style={{ fontWeight: repoFilter ? 400 : 600 }}>
          All repos
        </Link>
        {" · "}
        <span className="font-mono" style={{ fontSize: "0.8rem" }}>
          ?repo=slug on URL
        </span>
      </p>

      {!orgId ? (
        <p className="empty-state">Could not resolve organization.</p>
      ) : rows.length === 0 ? (
        <p className="empty-state">No signals yet. Run Post-CI or your workflow.</p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>When</th>
                <th>Repo</th>
                <th>SHA</th>
                <th>Conclusion</th>
                <th>Overlap</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="font-mono" style={{ fontSize: "0.75rem" }}>
                    {new Date(r.created_at).toLocaleString()}
                  </td>
                  <td className="font-mono">
                    <Link href={`/orgs/${params.slug}/ci?repo=${encodeURIComponent(r.repo_slug)}`}>{r.repo_slug}</Link>
                  </td>
                  <td className="font-mono" style={{ fontSize: "0.75rem" }}>
                    {r.head_sha.slice(0, 12)}…
                  </td>
                  <td>
                    <span className="badge">{r.check_conclusion}</span>
                  </td>
                  <td>{r.overlap_score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

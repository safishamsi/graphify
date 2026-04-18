import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { getOrgIdBySlug, listCISignals } from "@/lib/supabase/queries";

type Props = { params: { slug: string } };

export default async function OrgDashboardPage({ params }: Props) {
  const supabase = createClient();
  const orgId = await getOrgIdBySlug(supabase, params.slug);
  const recent = orgId ? (await listCISignals(supabase, orgId)).slice(0, 6) : [];

  return (
    <div>
      <h1 className="font-display page-title">Overview</h1>
      <p className="page-desc">
        Blast-radius analysis, graph snapshots in Storage, and CI correlation. Use the sidebar to move between tools.
      </p>

      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ fontSize: "1rem", color: "var(--fg-muted)", marginBottom: "0.75rem" }}>Quick links</h2>
        <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--fg-muted)" }}>
          <li>
            <Link href={`/orgs/${params.slug}/snapshots`}>Upload a graph snapshot</Link> then{" "}
            <Link href={`/orgs/${params.slug}/analyze`}>run Analyze</Link>.
          </li>
          <li>
            <Link href={`/orgs/${params.slug}/postci`}>Post-CI correlation</Link> writes to CI signals.
          </li>
          <li>
            <Link href={`/orgs/${params.slug}/federation`}>Federation</Link> and{" "}
            <Link href={`/orgs/${params.slug}/drift`}>Drift</Link> compare ready snapshots.
          </li>
        </ul>
      </section>

      <section style={{ marginTop: "2.5rem" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "1rem" }}>
          <h2 style={{ fontSize: "1rem", color: "var(--fg-muted)", margin: 0 }}>Recent CI signals</h2>
          <Link href={`/orgs/${params.slug}/ci`} className="text-muted" style={{ fontSize: "0.875rem" }}>
            View all
          </Link>
        </div>
        {!orgId ? (
          <p className="empty-state" style={{ marginTop: "1rem" }}>
            Could not resolve organization in Supabase (check RLS and that you are a member).
          </p>
        ) : recent.length === 0 ? (
          <p className="empty-state" style={{ marginTop: "1rem" }}>
            No signals yet. Run <Link href={`/orgs/${params.slug}/postci`}>Post-CI</Link> or your GitHub Action.
          </p>
        ) : (
          <div className="table-wrap" style={{ marginTop: "0.75rem" }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Repo</th>
                  <th>SHA</th>
                  <th>Conclusion</th>
                  <th>Overlap</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((row) => (
                  <tr key={row.id}>
                    <td className="font-mono">{row.repo_slug}</td>
                    <td className="font-mono" style={{ fontSize: "0.75rem" }}>
                      {row.head_sha.slice(0, 10)}…
                    </td>
                    <td>
                      <span className="badge">{row.check_conclusion}</span>
                    </td>
                    <td>{row.overlap_score}</td>
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

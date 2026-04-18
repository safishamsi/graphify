import { createClient } from "@/lib/supabase/server";
import { getOrgIdBySlug, listGraphSnapshots } from "@/lib/supabase/queries";
import { SnapshotUploadWizard } from "@/components/snapshots/SnapshotUploadWizard";

type Props = { params: { slug: string } };

export default async function SnapshotsPage({ params }: Props) {
  const supabase = createClient();
  const orgId = await getOrgIdBySlug(supabase, params.slug);
  const rows = orgId ? await listGraphSnapshots(supabase, orgId) : [];

  return (
    <div>
      <h1 className="font-display page-title">Graph snapshots</h1>
      <p className="page-desc">Metadata from Postgres (RLS). Upload uses signed Storage URLs from the depOS API.</p>

      <SnapshotUploadWizard orgSlug={params.slug} />

      <section style={{ marginTop: "2.5rem" }}>
        <h2 style={{ fontSize: "1rem", color: "var(--fg-muted)", marginBottom: "0.75rem" }}>Recent snapshots</h2>
        {!orgId ? (
          <p className="empty-state">Could not resolve organization.</p>
        ) : rows.length === 0 ? (
          <p className="empty-state">No snapshots yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Repo</th>
                  <th>SHA</th>
                  <th>Status</th>
                  <th>Bytes</th>
                  <th>ID</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="font-mono">{r.repo_slug}</td>
                    <td className="font-mono" style={{ fontSize: "0.75rem" }}>
                      {r.git_sha.slice(0, 14)}…
                    </td>
                    <td>
                      <span className={`badge ${r.status === "ready" ? "badge-ok" : ""}`}>{r.status}</span>
                    </td>
                    <td>{r.byte_size ?? "—"}</td>
                    <td className="font-mono" style={{ fontSize: "0.7rem" }}>
                      {r.id}
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

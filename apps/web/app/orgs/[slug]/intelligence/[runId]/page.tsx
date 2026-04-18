import Link from "next/link";
import { notFound } from "next/navigation";
import { DeposApiError } from "@/lib/depos/api";
import { fetchIntelligenceRunDetail, requireSessionAccessToken } from "@/lib/depos/server";
import { JsonInspector } from "@/components/domain/JsonInspector";
import type { IntelligenceRunDetailResponse } from "@/lib/depos/types";

type Props = { params: { slug: string; runId: string } };

export default async function IntelligenceRunPage({ params }: Props) {
  const token = await requireSessionAccessToken();
  let detail: IntelligenceRunDetailResponse | null = null;
  let forbidden = false;
  try {
    detail = await fetchIntelligenceRunDetail(token, params.slug, params.runId);
  } catch (e) {
    if (e instanceof DeposApiError && e.status === 404) {
      notFound();
    }
    if (e instanceof DeposApiError && e.status === 403) {
      forbidden = true;
    } else {
      throw e;
    }
  }

  if (forbidden || !detail) {
    return (
      <div>
        <p className="text-muted" style={{ marginBottom: "1rem" }}>
          <Link href={`/orgs/${params.slug}/intelligence`}>← All runs</Link>
        </p>
        <h1 className="font-display page-title">Run access</h1>
        <p className="page-desc">
          You are signed in, but this run is not visible with your current role or membership. Ask an org admin if you
          need access.
        </p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-muted" style={{ marginBottom: "1rem" }}>
        <Link href={`/orgs/${params.slug}/intelligence`}>← All runs</Link>
      </p>
      <h1 className="font-display page-title">Run {detail.run.id.slice(0, 8)}…</h1>
      <p className="page-desc">
        {detail.run.repo_slug} · {detail.run.analysis_mode} · {detail.run.status}
      </p>

      <section style={{ marginTop: "1.5rem" }}>
        <h2 style={{ fontSize: "1rem", color: "var(--fg-muted)", marginBottom: "0.75rem" }}>Findings</h2>
        {detail.findings.length === 0 ? (
          <p className="empty-state">No findings on this run.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {detail.findings.map((f) => (
              <li
                key={f.id}
                style={{
                  marginBottom: "1rem",
                  padding: "1rem",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  background: "var(--bg-elevated)",
                }}
              >
                <p style={{ margin: 0, fontWeight: 600 }}>
                  <span className="badge">{f.trust_level}</span>{" "}
                  <span className="font-mono" style={{ fontSize: "0.8rem" }}>
                    {f.mode}
                  </span>{" "}
                  {f.bug_type}
                </p>
                <p className="text-muted" style={{ margin: "0.35rem 0 0", fontSize: "0.9rem" }}>
                  {f.description}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <JsonInspector value={detail} title="Full API payload" />
    </div>
  );
}

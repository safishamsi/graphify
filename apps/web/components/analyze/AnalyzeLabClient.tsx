"use client";

import { useEffect, useState } from "react";
import { runAnalyzeAction } from "@/app/orgs/[slug]/actions";
import type { GraphSnapshotRow } from "@/lib/supabase/queries";
import type { LLMGraphExport } from "@/lib/depos/types";
import type { RepoRow } from "@/lib/depos/types";
import { BlastSummary } from "@/components/analyze/BlastSummary";
import { JsonInspector } from "@/components/domain/JsonInspector";
import { Button } from "@/components/ui/button";

export function AnalyzeLabClient({
  orgSlug,
  repos,
  readySnapshots,
}: {
  orgSlug: string;
  repos: RepoRow[];
  readySnapshots: GraphSnapshotRow[];
}) {
  const [repoSlug, setRepoSlug] = useState(repos[0]?.slug ?? "");
  const [snapshotId, setSnapshotId] = useState(readySnapshots[0]?.id ?? "");
  const [changedRaw, setChangedRaw] = useState("");
  const [hopDepth, setHopDepth] = useState(2);
  const [sarifRaw, setSarifRaw] = useState("");
  const [codeowners, setCodeowners] = useState("");
  const [result, setResult] = useState<LLMGraphExport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const sn = readySnapshots.filter((s) => s.repo_slug === repoSlug && s.status === "ready");
    if (sn.length === 0) {
      setSnapshotId("");
      return;
    }
    if (!sn.some((s) => s.id === snapshotId)) {
      setSnapshotId(sn[0].id);
    }
  }, [repoSlug, readySnapshots, snapshotId]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setResult(null);
    let sarif: Record<string, unknown> | null = null;
    if (sarifRaw.trim()) {
      try {
        sarif = JSON.parse(sarifRaw) as Record<string, unknown>;
      } catch {
        setErr("SARIF field must be valid JSON.");
        return;
      }
    }
    const changed_files = changedRaw
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    setBusy(true);
    try {
      const res = await runAnalyzeAction(orgSlug, {
        repo_slug: repoSlug,
        graph_snapshot_id: snapshotId,
        changed_files,
        hop_depth: hopDepth,
        sarif,
        codeowners_content: codeowners.trim() || null,
      });
      if (!res.ok) {
        setErr(res.error);
        return;
      }
      setResult(res.data);
    } finally {
      setBusy(false);
    }
  }

  const snaps = readySnapshots.filter((s) => !repoSlug || s.repo_slug === repoSlug);

  return (
    <div>
      <form onSubmit={(e) => void onSubmit(e)} className="zone-interactive">
        <div className="field">
          <label htmlFor="al-repo">Repository</label>
          <select id="al-repo" className="input" value={repoSlug} onChange={(e) => setRepoSlug(e.target.value)} required>
            {repos.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.slug}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="al-snap">Ready graph snapshot</label>
          <select
            id="al-snap"
            className="input font-mono"
            value={snapshotId}
            onChange={(e) => setSnapshotId(e.target.value)}
            required
          >
            {snaps.length === 0 ? <option value="">No ready snapshots for this repo</option> : null}
            {snaps.map((s) => (
              <option key={s.id} value={s.id}>
                {s.git_sha.slice(0, 12)}… · {s.id.slice(0, 8)}…
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="al-changed">Changed files (comma or newline separated)</label>
          <textarea id="al-changed" className="textarea" value={changedRaw} onChange={(e) => setChangedRaw(e.target.value)} rows={4} />
        </div>
        <div className="field">
          <label htmlFor="al-hop">Hop depth</label>
          <input
            id="al-hop"
            type="number"
            className="input"
            min={1}
            max={8}
            value={hopDepth}
            onChange={(e) => setHopDepth(Number(e.target.value) || 2)}
          />
        </div>
        <div className="field">
          <label htmlFor="al-sarif">SARIF JSON (optional)</label>
          <textarea id="al-sarif" className="textarea" value={sarifRaw} onChange={(e) => setSarifRaw(e.target.value)} rows={5} />
        </div>
        <div className="field">
          <label htmlFor="al-owners">CODEOWNERS text (optional)</label>
          <textarea id="al-owners" className="textarea" value={codeowners} onChange={(e) => setCodeowners(e.target.value)} rows={4} />
        </div>
        {err ? <p className="text-danger">{err}</p> : null}
        <Button type="submit" variant="primary" disabled={busy || !snapshotId}>
          {busy ? "Running…" : "Run analyze"}
        </Button>
      </form>

      {result ? (
        <section style={{ marginTop: "2rem" }}>
          <h2 style={{ fontSize: "1.1rem" }}>Result</h2>
          <p style={{ margin: "0.5rem 0 0", whiteSpace: "pre-wrap" }}>{result.executive_summary}</p>
          <p className="text-muted" style={{ marginTop: "0.75rem", fontSize: "0.875rem" }}>
            Nodes with errors: {Object.keys(result.error_index).length} · Edge faults: {result.edge_fault_index.length}
          </p>
          <BlastSummary blast={result.blast_radius} />
          <JsonInspector value={result} title="Full export JSON" />
        </section>
      ) : null}
    </div>
  );
}

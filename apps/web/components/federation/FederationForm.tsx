"use client";

import { useState } from "react";
import { runFederationAction } from "@/app/orgs/[slug]/actions";
import { JsonInspector } from "@/components/domain/JsonInspector";
import { Button } from "@/components/ui/button";
import type { FederationSnapshotsResponse } from "@/lib/depos/types";

const DEFAULT = '{\n  "my-repo": "00000000-0000-4000-8000-000000000000"\n}';

export function FederationForm({ orgSlug }: { orgSlug: string }) {
  const [mapText, setMapText] = useState(DEFAULT);
  const [allowedText, setAllowedText] = useState("");
  const [result, setResult] = useState<FederationSnapshotsResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setResult(null);
    let snapshot_ids: Record<string, string>;
    try {
      snapshot_ids = JSON.parse(mapText) as Record<string, string>;
    } catch {
      setErr("Snapshot map must be valid JSON: repo slug → snapshot UUID.");
      return;
    }
    const allowed = allowedText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setBusy(true);
    try {
      const res = await runFederationAction(orgSlug, snapshot_ids, allowed.length ? allowed : null);
      if (!res.ok) {
        setErr(res.error);
        return;
      }
      setResult(res.data);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={(e) => void onSubmit(e)} className="zone-interactive">
        <p className="text-muted" style={{ marginTop: 0 }}>
          Each key is a repository slug; each value is a <strong>ready</strong> <code>graph_snapshots.id</code> for that
          repo in this org.
        </p>
        <div className="field">
          <label htmlFor="fed-map">snapshot_ids JSON</label>
          <textarea id="fed-map" className="textarea" value={mapText} onChange={(e) => setMapText(e.target.value)} rows={8} />
        </div>
        <div className="field">
          <label htmlFor="fed-allow">Allowed repo slugs (optional, comma-separated)</label>
          <input id="fed-allow" className="input" value={allowedText} onChange={(e) => setAllowedText(e.target.value)} />
        </div>
        {err ? <p className="text-danger">{err}</p> : null}
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "Merging…" : "Run federation"}
        </Button>
      </form>
      {result ? (
        <section style={{ marginTop: "1.5rem" }}>
          <p>
            Merged graph: <strong>{result.nodes}</strong> nodes, <strong>{result.edges}</strong> edges.
          </p>
          <JsonInspector value={result.graph} title="Merged node-link graph" />
        </section>
      ) : null}
    </div>
  );
}

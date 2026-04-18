"use client";

import { useEffect, useState } from "react";
import { runDriftAction } from "@/app/orgs/[slug]/actions";
import { JsonInspector } from "@/components/domain/JsonInspector";
import { Button } from "@/components/ui/button";
import type { GraphSnapshotRow } from "@/lib/supabase/queries";

export function DriftForm({ orgSlug, readySnapshots }: { orgSlug: string; readySnapshots: GraphSnapshotRow[] }) {
  const [a, setA] = useState(readySnapshots[0]?.id ?? "");
  const [b, setB] = useState(readySnapshots[1]?.id ?? readySnapshots[0]?.id ?? "");
  const [result, setResult] = useState<{ jaccard_edges: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (a !== b || readySnapshots.length < 2) return;
    const alt = readySnapshots.find((s) => s.id !== a)?.id;
    if (alt) setB(alt);
  }, [a, b, readySnapshots]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setResult(null);
    setBusy(true);
    try {
      const res = await runDriftAction(orgSlug, a.trim(), b.trim());
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
        <div className="field">
          <label htmlFor="dr-a">Graph A (ready snapshot)</label>
          <select id="dr-a" className="input font-mono" value={a} onChange={(e) => setA(e.target.value)} required>
            {readySnapshots.map((s) => (
              <option key={s.id} value={s.id}>
                {s.repo_slug} · {s.git_sha.slice(0, 10)}… · {s.id.slice(0, 8)}…
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="dr-b">Graph B (ready snapshot)</label>
          <select id="dr-b" className="input font-mono" value={b} onChange={(e) => setB(e.target.value)} required>
            {readySnapshots.map((s) => (
              <option key={`b-${s.id}`} value={s.id}>
                {s.repo_slug} · {s.git_sha.slice(0, 10)}… · {s.id.slice(0, 8)}…
              </option>
            ))}
          </select>
        </div>
        {err ? <p className="text-danger">{err}</p> : null}
        <Button type="submit" variant="primary" disabled={busy || !a || !b}>
          {busy ? "Computing…" : "Compare drift"}
        </Button>
      </form>
      {result ? (
        <section style={{ marginTop: "1.5rem" }}>
          <p>
            Edge-set Jaccard similarity:{" "}
            <strong className="font-mono">{Number.isFinite(result.jaccard_edges) ? result.jaccard_edges.toFixed(4) : "—"}</strong>
          </p>
          <JsonInspector value={result} title="Response" />
        </section>
      ) : null}
    </div>
  );
}

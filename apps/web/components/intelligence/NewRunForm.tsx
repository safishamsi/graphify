"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createIntelligenceRunAction } from "@/app/orgs/[slug]/actions";
import { Button } from "@/components/ui/button";

export function NewRunForm({ orgSlug, repos }: { orgSlug: string; repos: { slug: string }[] }) {
  const router = useRouter();
  const [repoSlug, setRepoSlug] = useState(repos[0]?.slug ?? "");
  const [mode, setMode] = useState<"diff_aware" | "full_repo_scan">("diff_aware");
  const [status, setStatus] = useState<"running" | "succeeded" | "partial_reasoning" | "failed">("succeeded");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      const body = {
        repo_slug: repoSlug,
        analysis_mode: mode,
        status,
        findings: [] as unknown[],
      };
      const res = await createIntelligenceRunAction(orgSlug, body);
      if (!res.ok) {
        setErr(res.error);
        return;
      }
      setMsg(`Created run ${res.run_id}`);
      router.push(`/orgs/${orgSlug}/intelligence/${res.run_id}`);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => void onSubmit(e)} className="zone-interactive" style={{ marginBottom: "2rem" }}>
      <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>New run (minimal)</h2>
      <p className="text-muted" style={{ marginTop: 0 }}>
        Creates a run with empty findings for wiring tests. Extend later for full reasoner payloads.
      </p>
      <div className="field">
        <label htmlFor="ir-repo">Repository</label>
        <select id="ir-repo" className="input" value={repoSlug} onChange={(e) => setRepoSlug(e.target.value)} required>
          {repos.map((r) => (
            <option key={r.slug} value={r.slug}>
              {r.slug}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="ir-mode">Analysis mode</label>
        <select id="ir-mode" className="input" value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
          <option value="diff_aware">diff_aware</option>
          <option value="full_repo_scan">full_repo_scan</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="ir-status">Status</label>
        <select id="ir-status" className="input" value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
          <option value="succeeded">succeeded</option>
          <option value="running">running</option>
          <option value="partial_reasoning">partial_reasoning</option>
          <option value="failed">failed</option>
        </select>
      </div>
      {err ? <p className="text-danger">{err}</p> : null}
      {msg ? <p style={{ color: "var(--accent)" }}>{msg}</p> : null}
      <Button type="submit" variant="primary" disabled={busy}>
        {busy ? "Creating…" : "Create run"}
      </Button>
    </form>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { runPostciAction } from "@/app/orgs/[slug]/actions";
import { JsonInspector } from "@/components/domain/JsonInspector";
import { Button } from "@/components/ui/button";
import type { CheckConclusion, PostCIResult } from "@/lib/depos/types";
import type { GraphSnapshotRow } from "@/lib/supabase/queries";

export function PostciForm({
  orgSlug,
  repos,
  snapshots,
}: {
  orgSlug: string;
  repos: { slug: string }[];
  snapshots: GraphSnapshotRow[];
}) {
  const router = useRouter();
  const [repoSlug, setRepoSlug] = useState(repos[0]?.slug ?? "");
  const [headSha, setHeadSha] = useState("");
  const [predicted, setPredicted] = useState("");
  const [failed, setFailed] = useState("");
  const [conclusion, setConclusion] = useState<CheckConclusion>("failure");
  const [snapOpt, setSnapOpt] = useState("");
  const [out, setOut] = useState<PostCIResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const snapsForRepo = useMemo(
    () => snapshots.filter((s) => s.repo_slug === repoSlug),
    [snapshots, repoSlug],
  );

  useEffect(() => {
    if (!snapOpt) return;
    if (!snapsForRepo.some((s) => s.id === snapOpt)) setSnapOpt("");
  }, [snapOpt, snapsForRepo]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setOut(null);
    const predicted_files = predicted
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    const failed_paths = failed
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (snapOpt && !snapsForRepo.some((s) => s.id === snapOpt)) {
      setErr("Graph snapshot must belong to the selected repository.");
      return;
    }
    setBusy(true);
    try {
      const res = await runPostciAction(orgSlug, {
        repo_slug: repoSlug,
        head_sha: headSha.trim(),
        predicted_files,
        failed_paths,
        check_conclusion: conclusion,
        graph_snapshot_id: snapOpt || null,
      });
      if (!res.ok) {
        setErr(res.error);
        return;
      }
      setOut(res.data);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={(e) => void onSubmit(e)} className="zone-interactive">
        <div className="field">
          <label htmlFor="pc-repo">Repository</label>
          <select id="pc-repo" className="input" value={repoSlug} onChange={(e) => setRepoSlug(e.target.value)} required>
            {repos.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.slug}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="pc-sha">Head SHA</label>
          <input id="pc-sha" className="input font-mono" value={headSha} onChange={(e) => setHeadSha(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="pc-pred">Predicted impacted files</label>
          <textarea id="pc-pred" className="textarea" value={predicted} onChange={(e) => setPredicted(e.target.value)} rows={4} />
        </div>
        <div className="field">
          <label htmlFor="pc-fail">Failed paths (optional)</label>
          <textarea id="pc-fail" className="textarea" value={failed} onChange={(e) => setFailed(e.target.value)} rows={3} />
        </div>
        <div className="field">
          <label htmlFor="pc-conc">Check conclusion</label>
          <select
            id="pc-conc"
            className="input"
            value={conclusion}
            onChange={(e) => setConclusion(e.target.value as CheckConclusion)}
          >
            <option value="success">success</option>
            <option value="failure">failure</option>
            <option value="neutral">neutral</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="pc-snap">Graph snapshot (optional, this repo only)</label>
          <select id="pc-snap" className="input font-mono" value={snapOpt} onChange={(e) => setSnapOpt(e.target.value)}>
            <option value="">— none —</option>
            {snapsForRepo.map((s) => (
              <option key={s.id} value={s.id}>
                {s.status} · {s.git_sha.slice(0, 10)}… · {s.id.slice(0, 8)}…
              </option>
            ))}
          </select>
        </div>
        {err ? <p className="text-danger">{err}</p> : null}
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "Posting…" : "Run post-CI"}
        </Button>
      </form>
      {out ? <JsonInspector value={out} title="API response" /> : null}
    </div>
  );
}

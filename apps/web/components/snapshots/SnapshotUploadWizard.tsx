"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { completeGraphSnapshotAction, prepareGraphSnapshotAction } from "@/app/orgs/[slug]/actions";
import { Button } from "@/components/ui/button";

async function sha256Hex(buf: ArrayBuffer): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function SnapshotUploadWizard({ orgSlug }: { orgSlug: string }) {
  const router = useRouter();
  const [repo, setRepo] = useState("");
  const [gitSha, setGitSha] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    if (!file) {
      setErr("Choose a graph JSON file.");
      return;
    }
    setBusy(true);
    try {
      const prep = await prepareGraphSnapshotAction(orgSlug, repo.trim(), gitSha.trim());
      if (!prep.ok) {
        setErr(prep.error);
        return;
      }
      const url = prep.data.signed_url || prep.data.signedUrl;
      if (!url) {
        setErr("API did not return a signed upload URL.");
        return;
      }
      const buf = await file.arrayBuffer();
      const hex = await sha256Hex(buf);
      const put = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: buf,
      });
      if (!put.ok) {
        setErr(`Storage upload failed (${put.status}).`);
        return;
      }
      const done = await completeGraphSnapshotAction(orgSlug, prep.data.snapshot_id, hex);
      if (!done.ok) {
        setErr(done.error);
        return;
      }
      setMsg(`Snapshot ${prep.data.snapshot_id} is ready.`);
      setFile(null);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="zone-interactive" onSubmit={(e) => void onSubmit(e)}>
      <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Upload graph JSON</h2>
      <p className="text-muted" style={{ marginTop: 0 }}>
        Prepares a signed URL, uploads your node-link JSON to Storage, then verifies on the server.
      </p>
      <div className="field">
        <label htmlFor="su-repo">Repository slug</label>
        <input
          id="su-repo"
          className="input font-mono"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          required
          placeholder="my-service"
        />
      </div>
      <div className="field">
        <label htmlFor="su-sha">Git SHA</label>
        <input
          id="su-sha"
          className="input font-mono"
          value={gitSha}
          onChange={(e) => setGitSha(e.target.value)}
          required
          minLength={7}
          placeholder="abc1234…"
        />
      </div>
      <div className="field">
        <label htmlFor="su-file">graph.json</label>
        <input id="su-file" type="file" accept=".json,application/json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>
      {err ? <p className="text-danger">{err}</p> : null}
      {msg ? <p style={{ color: "var(--accent)" }}>{msg}</p> : null}
      <Button type="submit" variant="primary" disabled={busy}>
        {busy ? "Uploading…" : "Prepare, upload, complete"}
      </Button>
    </form>
  );
}

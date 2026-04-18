"use client";

import * as Switch from "@radix-ui/react-switch";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toggleRepoAction } from "@/app/orgs/[slug]/actions";
import type { RepoRow } from "@/lib/depos/types";

export function RepoToggles({ orgSlug, repo, disabled }: { orgSlug: string; repo: RepoRow; disabled: boolean }) {
  const [pending, start] = useTransition();
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);

  function push(nextA: boolean, nextF: boolean) {
    if (disabled) return;
    setErr(null);
    start(async () => {
      const res = await toggleRepoAction(orgSlug, repo.slug, nextA, nextF);
      if (!res.ok) {
        setErr(res.error);
        router.refresh();
        return;
      }
      router.refresh();
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <label className="switch-row" style={{ cursor: disabled ? "default" : "pointer" }}>
        <Switch.Root
          className="switch-root"
          checked={repo.enabled_for_analysis}
          disabled={disabled || pending}
          onCheckedChange={(v) => push(v, repo.include_in_federated)}
        >
          <Switch.Thumb className="switch-thumb" />
        </Switch.Root>
        <span style={{ fontSize: "0.875rem", color: "var(--fg-muted)" }}>Analysis enabled</span>
      </label>
      <label className="switch-row" style={{ cursor: disabled ? "default" : "pointer" }}>
        <Switch.Root
          className="switch-root"
          checked={repo.include_in_federated}
          disabled={disabled || pending}
          onCheckedChange={(v) => push(repo.enabled_for_analysis, v)}
        >
          <Switch.Thumb className="switch-thumb" />
        </Switch.Root>
        <span style={{ fontSize: "0.875rem", color: "var(--fg-muted)" }}>Include in federated graph</span>
      </label>
      {pending ? <span className="text-muted">Saving…</span> : null}
      {err ? <p className="text-danger" style={{ margin: 0, fontSize: "0.8125rem" }}>{err}</p> : null}
    </div>
  );
}

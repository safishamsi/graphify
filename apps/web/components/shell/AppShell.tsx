import Link from "next/link";
import type { MeMembership } from "@/lib/depos/types";
import { OrgNav } from "@/components/shell/OrgNav";
import { OrgSwitcher } from "@/components/shell/OrgSwitcher";
import { SignOutButton } from "@/components/shell/SignOutButton";

export function AppShell({
  orgSlug,
  userEmail,
  memberships,
  apiConfigured,
  apiHealth,
  children,
}: {
  orgSlug: string;
  userEmail: string | null;
  memberships: MeMembership[];
  apiConfigured: boolean;
  apiHealth: { ok: boolean; status?: string };
  children: React.ReactNode;
}) {
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div>
          <Link href="/" className="font-display" style={{ fontSize: "1.25rem", color: "var(--fg)" }}>
            depOS
          </Link>
          <p className="text-muted" style={{ margin: "0.35rem 0 0", fontSize: "0.75rem" }}>
            Dependency Map OS
          </p>
        </div>

        <OrgSwitcher orgSlug={orgSlug} memberships={memberships} />

        <OrgNav orgSlug={orgSlug} />

        <div style={{ marginTop: "auto", paddingTop: "1rem", borderTop: "1px solid var(--border-subtle)" }}>
          <p className="text-muted" style={{ margin: "0 0 0.5rem", fontSize: "0.75rem" }}>
            {userEmail ?? "Signed in"}
          </p>
          <SignOutButton />
        </div>
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <div />
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span className="text-muted" style={{ fontSize: "0.75rem" }}>
              API
            </span>
            {!apiConfigured ? (
              <span className="badge">unset</span>
            ) : (
              <>
                <span className={`health-dot ${apiHealth.ok ? "ok" : "err"}`} title={apiHealth.status} />
                <span className="font-mono" style={{ fontSize: "0.75rem" }}>
                  {apiHealth.ok ? "/health" : "down"}
                </span>
              </>
            )}
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}

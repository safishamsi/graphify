import Link from "next/link";
import { redirect } from "next/navigation";
import { humanizeDeposApiError } from "@/lib/depos/api";
import { createClient } from "@/lib/supabase/server";
import { fetchMe } from "@/lib/depos/server";
import type { MeResponse } from "@/lib/depos/types";
import { OrgCreateForm } from "@/components/orgs/OrgCreateForm";

export default async function OrgsIndexPage() {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    redirect("/auth/sign-in?next=/orgs");
  }

  let meError: string | null = null;
  let me: MeResponse = { user_id: "", email: null, memberships: [] };
  try {
    me = await fetchMe(session.access_token);
  } catch (e) {
    meError = humanizeDeposApiError(e, 400);
  }

  const orgSlugs = (me.memberships ?? [])
    .map((m) => m.org_slug)
    .filter((s): s is string => Boolean(s));

  if (orgSlugs.length === 1) {
    redirect(`/orgs/${orgSlugs[0]}`);
  }

  return (
    <main className="marketing-page">
      <p className="text-muted" style={{ marginBottom: "2rem", display: "flex", flexWrap: "wrap", gap: "1rem", alignItems: "center" }}>
        <Link href="/">← depOS home</Link>
        <Link href="/orgs/logout">Sign out</Link>
      </p>
      <h1 className="font-display page-title">Organizations</h1>
      <p className="page-desc">Pick an org or create one. You need API access configured for org-scoped actions.</p>

      {!process.env.NEXT_PUBLIC_DEPOS_API_URL && (
        <p className="text-danger">Set NEXT_PUBLIC_DEPOS_API_URL in the repo root .env to load memberships from the API.</p>
      )}
      {meError ? <p className="text-danger">{meError}</p> : null}

      {orgSlugs.length > 0 && (
        <section style={{ marginBottom: "2.5rem" }}>
          <h2 style={{ fontSize: "1rem", color: "var(--fg-muted)", marginBottom: "0.75rem" }}>Your orgs</h2>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {orgSlugs.map((slug) => (
              <li key={slug} style={{ marginBottom: "0.5rem" }}>
                <Link href={`/orgs/${slug}`} className="font-mono" style={{ fontSize: "1rem" }}>
                  {slug}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="zone-interactive">
        <h2 style={{ marginTop: 0, fontSize: "1.05rem" }}>Create organization</h2>
        <p className="text-muted" style={{ marginTop: 0 }}>
          Slug becomes the URL segment and must be unique. Use lowercase letters, numbers, and hyphens.
        </p>
        <OrgCreateForm />
      </section>
    </main>
  );
}

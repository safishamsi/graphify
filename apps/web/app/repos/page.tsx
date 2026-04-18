import { createClient } from "@/lib/supabase/server";

type Membership = { org_slug: string | null; role: string };

async function fetchMemberships(token: string): Promise<Membership[]> {
  const base = process.env.NEXT_PUBLIC_DEPOS_API_URL;
  if (!base) return [];
  const resp = await fetch(`${base.replace(/\/$/, "")}/v1/me`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!resp.ok) return [];
  const data = await resp.json();
  return (data.memberships ?? []) as Membership[];
}

async function fetchRepos(
  token: string,
  orgSlug: string,
): Promise<{ slug: string; enabled_for_analysis: boolean; include_in_federated: boolean }[]> {
  const base = process.env.NEXT_PUBLIC_DEPOS_API_URL;
  if (!base) return [];
  const resp = await fetch(`${base.replace(/\/$/, "")}/v1/orgs/${encodeURIComponent(orgSlug)}/repos`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!resp.ok) return [];
  const data = await resp.json();
  return data.repos ?? [];
}

export default async function ReposPage() {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const token = session?.access_token ?? "";
  const memberships = token ? await fetchMemberships(token) : [];
  const primaryOrg = memberships.find((m) => m.org_slug)?.org_slug ?? null;
  const repos = primaryOrg ? await fetchRepos(token, primaryOrg) : [];

  return (
    <main>
      <nav>
        <a href="/">Home</a>
        <a href="/repos">Repositories</a>
      </nav>
      <h1>Repositories</h1>

      {!process.env.NEXT_PUBLIC_DEPOS_API_URL && (
        <p style={{ color: "var(--muted)" }}>
          Set <code>NEXT_PUBLIC_DEPOS_API_URL</code> to your depOS API (e.g. <code>http://127.0.0.1:8080</code>) to load
          repositories.
        </p>
      )}

      {process.env.NEXT_PUBLIC_DEPOS_API_URL && memberships.length === 0 && (
        <p style={{ color: "var(--muted)" }}>
          You are not a member of any organization yet. Ask an owner to invite you, or create one via{" "}
          <code>POST /v1/orgs</code>.
        </p>
      )}

      {primaryOrg && (
        <section>
          <h2>{primaryOrg}</h2>
          {repos.length === 0 ? (
            <p style={{ color: "var(--muted)" }}>No repositories yet.</p>
          ) : (
            <ul>
              {repos.map((r) => (
                <li key={r.slug}>
                  <code>{r.slug}</code>
                  {r.enabled_for_analysis ? " · analysis-on" : " · analysis-off"}
                  {r.include_in_federated ? " · federated" : ""}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}

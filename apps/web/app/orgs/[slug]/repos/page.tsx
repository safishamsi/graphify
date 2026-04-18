import { deposJson, humanizeDeposApiError } from "@/lib/depos/api";
import { fetchMe, requireSessionAccessToken } from "@/lib/depos/server";
import { isOrgAdmin } from "@/lib/depos/roles";
import type { ReposListResponse } from "@/lib/depos/types";
import { RepoToggles } from "@/components/repos/RepoToggles";

type Props = { params: { slug: string } };

export default async function OrgReposPage({ params }: Props) {
  const token = await requireSessionAccessToken();
  const me = await fetchMe(token);
  const admin = isOrgAdmin(me.memberships ?? [], params.slug);

  let repos: ReposListResponse["repos"] = [];
  let apiError: string | null = null;
  try {
    const data = await deposJson<ReposListResponse>(`/v1/orgs/${encodeURIComponent(params.slug)}/repos`, token);
    repos = data.repos ?? [];
  } catch (e) {
    apiError = humanizeDeposApiError(e, 400);
  }

  return (
    <div>
      <h1 className="font-display page-title">Repositories</h1>
      <p className="page-desc">
        Toggle analysis and federated inclusion. Only owners and admins can change flags.
      </p>
      {apiError ? <p className="text-danger">{apiError}</p> : null}
      {!apiError && repos.length === 0 ? (
        <p className="empty-state">No repositories yet. Toggles create rows when you first enable a slug.</p>
      ) : null}
      {!apiError && repos.length > 0 ? (
        <div className="table-wrap" style={{ marginTop: "1rem" }}>
          <table className="data">
            <thead>
              <tr>
                <th>Slug</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {repos.map((r) => (
                <tr key={r.slug}>
                  <td className="font-mono">{r.slug}</td>
                  <td>
                    <RepoToggles orgSlug={params.slug} repo={r} disabled={!admin} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

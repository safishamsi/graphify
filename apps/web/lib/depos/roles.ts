import type { MeMembership } from "@/lib/depos/types";

export function isOrgAdmin(memberships: MeMembership[], orgSlug: string): boolean {
  const m = memberships.find((x) => x.org_slug === orgSlug);
  if (!m?.org_slug) return false;
  return m.role === "owner" || m.role === "admin";
}

import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { getOrgIdBySlug, listGraphSnapshots } from "@/lib/supabase/queries";
import { DriftForm } from "@/components/drift/DriftForm";

type Props = { params: { slug: string } };

export default async function DriftPage({ params }: Props) {
  const supabase = createClient();
  const orgId = await getOrgIdBySlug(supabase, params.slug);
  const rows = orgId ? (await listGraphSnapshots(supabase, orgId)).filter((s) => s.status === "ready") : [];

  return (
    <div>
      <h1 className="font-display page-title">Drift</h1>
      <p className="page-desc">Compare two ready snapshots (edge Jaccard) via POST /v1/drift/snapshots.</p>
      {!orgId ? (
        <p className="empty-state">Could not resolve organization.</p>
      ) : rows.length < 2 ? (
        <p className="empty-state">
          Need at least two ready snapshots.{" "}
          <Link href={`/orgs/${params.slug}/snapshots`}>Upload and complete snapshots</Link> first.
        </p>
      ) : (
        <DriftForm orgSlug={params.slug} readySnapshots={rows} />
      )}
    </div>
  );
}

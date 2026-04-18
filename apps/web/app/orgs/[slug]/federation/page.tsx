import { FederationForm } from "@/components/federation/FederationForm";

type Props = { params: { slug: string } };

export default function FederationPage({ params }: Props) {
  return (
    <div>
      <h1 className="font-display page-title">Federation</h1>
      <p className="page-desc">Merge ready snapshots per repo via POST /v1/federation/snapshots.</p>
      <FederationForm orgSlug={params.slug} />
    </div>
  );
}

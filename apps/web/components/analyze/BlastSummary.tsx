import type { BlastRadiusResult } from "@/lib/depos/types";

export function BlastSummary({ blast }: { blast: BlastRadiusResult | null }) {
  if (!blast) {
    return <p className="text-muted">No blast radius (add changed files in the form).</p>;
  }
  return (
    <div style={{ marginTop: "1rem" }}>
      <p style={{ margin: "0 0 0.5rem", fontWeight: 600 }}>Blast radius</p>
      <p className="text-muted" style={{ margin: "0 0 0.75rem" }}>
        {blast.summary}
      </p>
      <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.875rem", color: "var(--fg-muted)" }}>
        <li>Seeds: {blast.seed_files.length}</li>
        <li>Impacted nodes: {blast.impacted_node_ids.length}</li>
        <li>Hop depth: {blast.hop_depth}</li>
        <li>Blast score: {blast.blast_score}</li>
      </ul>
      {blast.cross_owner_warnings?.length ? (
        <ul className="text-danger" style={{ margin: "0.75rem 0 0", paddingLeft: "1.1rem" }}>
          {blast.cross_owner_warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

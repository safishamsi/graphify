/** Types aligned with depOS FastAPI JSON (tenant routes). */

export type MeMembership = { org_slug: string | null; role: string };

export type MeResponse = {
  user_id: string;
  email: string | null;
  memberships: MeMembership[];
};

export type RepoRow = {
  slug: string;
  enabled_for_analysis: boolean;
  include_in_federated: boolean;
};

export type ReposListResponse = { repos: RepoRow[] };

export type BlastRadiusResult = {
  seed_files: string[];
  impacted_node_ids: string[];
  hop_depth: number;
  blast_score: number;
  defect_boost: number;
  summary: string;
  cross_owner_warnings: string[];
};

export type LLMGraphExport = {
  graph: Record<string, unknown>;
  error_index: Record<string, unknown[]>;
  edge_fault_index: unknown[];
  executive_summary: string;
  blast_radius: BlastRadiusResult | null;
};

export type GraphSnapshotPrepareResponse = {
  snapshot_id: string;
  storage_path: string;
  bucket: string;
  signed_url?: string;
  signedUrl?: string;
  token?: string;
  path?: string;
};

export type FederationSnapshotsResponse = {
  nodes: number;
  edges: number;
  graph: Record<string, unknown>;
};

export type DriftSnapshotsResponse = {
  /** Edge-set Jaccard similarity in [0, 1] from drift_edge_jaccard. */
  jaccard_edges: number;
};

export type IntelligenceRunSummary = {
  id: string;
  repo_slug: string;
  status: string;
  analysis_mode: string;
  started_at: string | null;
  finished_at: string | null;
};

export type IntelligenceRunsListResponse = {
  runs: IntelligenceRunSummary[];
};

export type IntelligenceFindingRow = {
  id: string;
  trust_level: string;
  mode: string;
  bug_type: string;
  description: string;
  affected_components: unknown[];
  witness_path: unknown[];
  verifier_outcome: string;
  reasoner_confidence: number;
};

export type IntelligenceRunDetailResponse = {
  run: {
    id: string;
    repo_slug: string;
    base_ref: string | null;
    head_ref: string | null;
    analysis_mode: string;
    provider: string | null;
    status: string;
    started_at: string | null;
    finished_at: string | null;
  };
  findings: IntelligenceFindingRow[];
};

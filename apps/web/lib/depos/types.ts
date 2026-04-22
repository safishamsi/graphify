/** Types aligned with depOS FastAPI JSON (tenant routes). */

export type OrgRole = "owner" | "admin" | "member";
export type CheckConclusion = "success" | "failure" | "neutral";
export type IntelligenceReasonerRunHealth = "ok" | "degraded" | "failed";
export type IntelligencePersistedFindingTrustLevel = "confirmed" | "partially_confirmed" | "evaluator_surfaced";
export type IntelligenceUniverse = "code" | "deps" | "env" | "prompt" | "schema" | "nextjs" | "infra";
export type IntelligenceDiagnosticCategory =
  | "type_error"
  | "lint"
  | "security"
  | "test_failure"
  | "build"
  | "unresolved"
  | "unknown";
export type IntelligenceDiagnosticSeverity = "error" | "warning" | "note";
export type ApiErrorPayload = Record<string, unknown>;

export type MeMembership = { org_slug: string | null; role: OrgRole };

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

export type DiagnosticRef = {
  id: string;
  category: IntelligenceDiagnosticCategory;
  severity: IntelligenceDiagnosticSeverity;
  rule_id: string | null;
  message: string;
  tool: string;
  uri: string;
  start_line: number;
  end_line: number;
};

export type EdgeFaultRef = {
  source: string;
  target: string;
  fault: true;
  fault_categories: string[];
  relation: string | null;
};

export type LLMGraphExport = {
  graph: Record<string, unknown>;
  error_index: Record<string, DiagnosticRef[]>;
  edge_fault_index: EdgeFaultRef[];
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

export type IntelligenceAnalysisMode = "diff_aware" | "full_repo_scan";
export type IntelligenceRunStatus = "running" | "succeeded" | "partial_reasoning" | "failed";
export type IntelligenceReasonerMode = "A" | "B" | "C";
export type IntelligenceVerifierOutcome =
  | "confirmed"
  | "partially_confirmed"
  | "unconfirmed"
  | "invalid_reasoning"
  | "evaluator_surfaced";
export type IntelligenceSeverity = "info" | "low" | "medium" | "high" | "critical";

export type IntelligenceRunSummary = {
  id: string;
  repo_slug: string;
  status: IntelligenceRunStatus;
  analysis_mode: IntelligenceAnalysisMode;
  pipeline_version: string;
  started_at: string | null;
  finished_at: string | null;
};

export type IntelligenceRunsListResponse = {
  runs: IntelligenceRunSummary[];
};

export type IntelligenceFindingRow = {
  id: string;
  trust_level: IntelligenceVerifierOutcome;
  mode: IntelligenceReasonerMode | null;
  bug_type: string;
  description: string;
  affected_components: string[];
  witness_path: string[];
  detector_name: string;
  detector_version: string;
  pipeline_version: string;
  severity: IntelligenceSeverity;
  verifier_outcome: IntelligenceVerifierOutcome;
  reasoner_confidence: number;
};

export type IntelligenceDetectorStatRow = {
  detector_name: string;
  detector_version: string;
  candidates_emitted: number;
  verified_confirmed: number;
  verified_invalid: number;
  mean_latency_ms: number;
  errors: ApiErrorPayload[];
};

export type IntelligenceRunDetailResponse = {
  run: {
    id: string;
    repo_slug: string;
    base_ref: string | null;
    head_ref: string | null;
    analysis_mode: IntelligenceAnalysisMode;
    provider: string | null;
    status: IntelligenceRunStatus;
    pipeline_version: string;
    enabled_detectors: string[];
    universes_present: IntelligenceUniverse[];
    ingest_errors: ApiErrorPayload[];
    started_at: string | null;
    finished_at: string | null;
  };
  detector_stats: IntelligenceDetectorStatRow[];
  findings: IntelligenceFindingRow[];
};

export type IntelligenceFindingCreateRequest = {
  trust_level: IntelligencePersistedFindingTrustLevel;
  mode?: IntelligenceReasonerMode | null;
  bug_type?: string;
  description?: string;
  affected_components?: string[];
  witness_path?: string[];
  missing_guard?: string | null;
  recommended_fix?: string | null;
  reasoner_confidence?: number;
  ranking_phase?: number;
  verifier_outcome?: string;
  verifier_checks_passed?: string[];
  verifier_checks_inconclusive?: string[];
  rls_verdict?: string | null;
  migration_state_facts?: Record<string, string>;
  caveats?: Record<string, unknown>;
  detector_name?: string;
  detector_version?: string;
  pipeline_version?: string;
  severity?: IntelligenceSeverity;
};

export type IntelligenceRunCreateRequest = {
  repo_slug: string;
  analysis_mode: IntelligenceAnalysisMode;
  base_ref?: string | null;
  head_ref?: string | null;
  provider?: string | null;
  low_stitcher_coverage?: boolean;
  token_estimator?: string;
  ranking_phase?: number;
  status?: IntelligenceRunStatus;
  pack_manifest_id?: string | null;
  pipeline_version?: string;
  ingest_errors?: ApiErrorPayload[];
  universes_present?: IntelligenceUniverse[];
  enabled_detectors?: string[];
  detector_policy?: Record<string, unknown> | null;
  detector_stats?: IntelligenceDetectorStatRow[];
  findings?: IntelligenceFindingCreateRequest[];
  reasoner_run_health?: IntelligenceReasonerRunHealth;
  reasoner_health_reason?: string;
  reasoner_attempts?: number;
  reasoner_successes?: number;
  reasoner_failures?: number;
  reasoner_failure_breakdown?: Record<string, number>;
  evidence_summary?: Record<string, unknown>;
  bundles_built?: number;
  bundles_sent_to_reasoner?: number;
  bundles_skipped_low_evidence?: number;
  dataset_path_resolution?: Record<string, unknown>;
};

export type PostCIResult = {
  check_conclusion: CheckConclusion;
  overlap_score: number;
  intersecting_paths: string[];
  unexpected_failure: boolean;
  summary: string;
};

"""All Pydantic models for the depOS intelligence layer.

Single source of truth. Import from here everywhere. Do not create a
``depos/intelligence_types.py`` module.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

NodeId = str
EdgeId = str


# ---------------------------------------------------------------------------
# Module 1 — semantic edges & coverage
# ---------------------------------------------------------------------------

class ContractKind(str, Enum):
    http = "http"
    rpc = "rpc"
    queue = "queue"
    schema = "schema"
    rls = "rls"


class RLSCoverage(str, Enum):
    full = "full"
    partial_operation = "partial_operation"
    partial_predicate = "partial_predicate"
    context_mismatch = "context_mismatch"
    none = "none"


class MigrationState(str, Enum):
    exists_in_branch = "exists_in_branch"
    exists_only_in_later_migration = "exists_only_in_later_migration"
    removed_in_branch = "removed_in_branch"
    ambiguous = "ambiguous"


class SemanticEdgeMetadata(BaseModel):
    """Attached to every enriched edge emitted by Module 1."""

    model_config = ConfigDict(extra="allow")

    confidence: float = 1.0
    inferred: bool = False
    source_system: Optional[str] = None
    target_system: Optional[str] = None
    contract_kind: Optional[ContractKind] = None

    api_method: Optional[str] = None
    route_pattern: Optional[str] = None
    table_name: Optional[str] = None
    column_name: Optional[str] = None
    rpc_name: Optional[str] = None
    task_name: Optional[str] = None
    payload_fields: list[str] = Field(default_factory=list)
    migration_id: Optional[str] = None
    migration_order: Optional[int] = None
    branch_visible: Optional[bool] = None
    rls_policy_id: Optional[str] = None
    rls_command: Optional[str] = None
    rls_coverage: Optional[RLSCoverage] = None


class StitcherCoverageReport(BaseModel):
    total_fastapi_routes: int = 0
    linked_routes: int = 0
    unlinked_routes: list[str] = Field(default_factory=list)
    coverage_ratio: float = 0.0
    low_coverage: bool = False

    total_celery_tasks: int = 0
    matched_producer_consumer_pairs: int = 0

    rls_nodes_found: int = 0
    migration_files_found: int = 0


# ---------------------------------------------------------------------------
# Module 2 — candidates
# ---------------------------------------------------------------------------

class SeedType(str, Enum):
    diff_anchor = "diff_anchor"
    interface_surface = "interface_surface"
    graph_anomaly = "graph_anomaly"
    ai_driven = "ai_driven"


class AnalysisMode(str, Enum):
    diff_aware = "diff_aware"
    full_repo_scan = "full_repo_scan"


class ChangeManifestEntry(BaseModel):
    path: Optional[str] = None
    node_ids: list[NodeId] = Field(default_factory=list)
    high_churn_file: bool = False
    dropped_from_budget: list[NodeId] = Field(default_factory=list)
    migration_change: bool = False
    file_change: bool = False


class ChangeManifest(BaseModel):
    entries: list[ChangeManifestEntry] = Field(default_factory=list)
    resolved_via: str = "git"  # "cpg_diff" | "git" | "manual"


class Candidate(BaseModel):
    candidate_id: str
    scope_id: str
    seed_type: SeedType
    priority_score: float = 0.0
    language_pair: Optional[str] = None
    seam_edges: list[EdgeId] = Field(default_factory=list)
    diff_anchors: list[NodeId] = Field(default_factory=list)
    analysis_mode: AnalysisMode = AnalysisMode.diff_aware
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Module 3 — context bundles
# ---------------------------------------------------------------------------

class CodeSnippet(BaseModel):
    node_id: NodeId
    source_file: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    text: str = ""


class SeamEdge(BaseModel):
    edge_id: EdgeId
    source: NodeId
    target: NodeId
    relation: str
    metadata: SemanticEdgeMetadata = Field(default_factory=SemanticEdgeMetadata)


class PackManifest(BaseModel):
    manifest_id: str
    token_estimator: str = "chars4"  # "chars4" | "tiktoken-cl100k" | ...
    included: list[str] = Field(default_factory=list)
    truncated: list[str] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
    truncation_order_applied: list[str] = Field(default_factory=list)


class ContextBundle(BaseModel):
    bundle_id: str
    candidate_id: str
    scope_id: str

    call_chain_in: list[dict[str, Any]] = Field(default_factory=list)
    call_chain_out: list[dict[str, Any]] = Field(default_factory=list)
    data_reads: list[str] = Field(default_factory=list)
    data_writes: list[str] = Field(default_factory=list)
    cross_language_seams: list[SeamEdge] = Field(default_factory=list)
    diff_anchors: list[dict[str, Any]] = Field(default_factory=list)
    rls_coverage: dict[str, RLSCoverage] = Field(default_factory=dict)
    migration_state: dict[str, MigrationState] = Field(default_factory=dict)
    code_snippets: list[CodeSnippet] = Field(default_factory=list)

    pack_manifest: PackManifest
    token_budget: int = 0
    truncation_events: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Module 4 — reasoner outputs
# ---------------------------------------------------------------------------

class ReasonerMode(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class ModeAFinding(BaseModel):
    bug_type: str
    description: str
    trigger_condition: str = ""
    affected_path: list[NodeId] = Field(default_factory=list)
    confidence: float = 0.0
    graph_anchor_nodes: list[NodeId] = Field(default_factory=list)


class ModeAOutput(BaseModel):
    mode: ReasonerMode = ReasonerMode.A
    findings: list[ModeAFinding] = Field(default_factory=list)


class ModeBFinding(BaseModel):
    violation_type: str
    description: str
    component_a: str
    component_b: str
    disagreement: str
    confidence: float = 0.0
    graph_anchor_nodes: list[NodeId] = Field(default_factory=list)


class ModeBOutput(BaseModel):
    mode: ReasonerMode = ReasonerMode.B
    findings: list[ModeBFinding] = Field(default_factory=list)


class ModeCFinding(BaseModel):
    flow_bug_type: str
    description: str
    operation: str
    violating_path: list[NodeId] = Field(default_factory=list)
    missing_guard: str = ""
    confidence: float = 0.0
    graph_anchor_nodes: list[NodeId] = Field(default_factory=list)


class ModeCOutput(BaseModel):
    mode: ReasonerMode = ReasonerMode.C
    findings: list[ModeCFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Module 5 — ranker
# ---------------------------------------------------------------------------

class RankerDiffFeatures(BaseModel):
    changed_nodes_on_path: int = 0
    removed_entities_referenced: int = 0
    cross_lang_seams_on_path: int = 0
    unresolved_symbols: int = 0


class RankerInput(BaseModel):
    candidate_id: str
    invariant_id: Optional[str] = None
    candidate_path: list[NodeId] = Field(default_factory=list)
    edge_sequence: list[str] = Field(default_factory=list)
    node_attrs: dict[str, Any] = Field(default_factory=dict)
    diff_features: RankerDiffFeatures = Field(default_factory=RankerDiffFeatures)


class RankerScore(BaseModel):
    candidate_id: str
    score: float
    ranking_phase: int = 0
    components: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Module 6 — verifier
# ---------------------------------------------------------------------------

class VerifierOutcome(str, Enum):
    confirmed = "confirmed"
    partially_confirmed = "partially_confirmed"
    unconfirmed = "unconfirmed"
    invalid_reasoning = "invalid_reasoning"
    evaluator_surfaced = "evaluator_surfaced"


class VerifierCheckResult(BaseModel):
    name: str
    result: str  # "pass" | "fail" | "unavailable" | "rls_covered" | "rls_partial" | "insufficient_static_evidence" | "invalid"
    detail: str = ""


class VerifierAuditEntry(BaseModel):
    finding_id: str
    verifier_outcome: VerifierOutcome
    checks_run: list[VerifierCheckResult] = Field(default_factory=list)
    inferred_edge_confidence_floor_applied: bool = False
    pack_manifest_id: str = ""
    reasoner_mode: ReasonerMode
    surfaced: bool = False


# ---------------------------------------------------------------------------
# Module 7 — gray zone
# ---------------------------------------------------------------------------

class GrayZoneEntryReason(str, Enum):
    partially_confirmed_1_check = "partially_confirmed_1_check"
    unconfirmed_high_confidence = "unconfirmed_high_confidence"
    all_inferred_edges = "all_inferred_edges"
    rls_context_mismatch = "rls_context_mismatch"
    low_stitcher_coverage = "low_stitcher_coverage"


class GrayZoneVote(str, Enum):
    bug = "bug"
    no_bug = "no_bug"
    uncertain = "uncertain"
    confirmed = "confirmed"
    refuted = "refuted"


class GrayZoneVoteOutcome(str, Enum):
    evaluator_surfaced = "evaluator_surfaced"
    hold_for_review = "hold_for_review"
    discard = "discard"


class GrayZoneAuditRow(BaseModel):
    finding_id: str
    entry_reason: GrayZoneEntryReason
    model_a_verdict: GrayZoneVote
    model_a_confidence: float = 0.0
    model_a_reasoning: str = ""
    model_b_verdict: GrayZoneVote
    model_b_counter_reasoning: str = ""
    model_c_structural_questions: list[str] = Field(default_factory=list)
    model_c_graph_answers: list[str] = Field(default_factory=list)
    model_c_verdict: GrayZoneVote
    vote_outcome: GrayZoneVoteOutcome
    surfaced: bool = False
    final_label: str = ""
    training_export: bool = True


# ---------------------------------------------------------------------------
# Output: violations.json
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    finding_id: str
    trust_level: VerifierOutcome
    mode: ReasonerMode
    verifier_outcome: VerifierOutcome
    bug_type: str = ""
    description: str = ""
    affected_components: list[str] = Field(default_factory=list)
    witness_path: list[NodeId] = Field(default_factory=list)
    missing_guard: Optional[str] = None
    recommended_fix: Optional[str] = None
    reasoner_confidence: float = 0.0
    ranking_phase: int = 0
    verifier_checks_passed: list[str] = Field(default_factory=list)
    verifier_checks_inconclusive: list[str] = Field(default_factory=list)
    rls_verdict: Optional[RLSCoverage] = None
    migration_state_facts: dict[str, str] = Field(default_factory=dict)
    pack_manifest_id: str = ""

    partially_confirmed_caveat: Optional[str] = None
    evaluator_surfaced_caveat: Optional[str] = None
    low_stitcher_coverage_caveat: Optional[str] = None
    stale_diff_replay_caveat: Optional[str] = None


# ---------------------------------------------------------------------------
# Training data rows
# ---------------------------------------------------------------------------

class RankerExample(BaseModel):
    example_id: str
    candidate_path: list[NodeId]
    edge_sequence: list[str]
    node_attrs: dict[str, Any] = Field(default_factory=dict)
    diff_features: RankerDiffFeatures
    label: str  # "suspicious" | "not_suspicious"
    label_source: str  # "verifier_confirmed" | "verifier_contradicted" | "evaluator_all_reject" | "reviewer_dismissed"
    confidence: float = 0.0
    ranking_phase_at_creation: int = 0
    repo_id: str = ""
    base_ref: str = ""
    head_ref: str = ""


class ReasonerExample(BaseModel):
    example_id: str
    mode: ReasonerMode
    evidence_pack: dict[str, Any] = Field(default_factory=dict)
    pack_manifest: PackManifest
    expected_output_json: dict[str, Any] = Field(default_factory=dict)
    verifier_outcome: VerifierOutcome
    evaluator_outcome: Optional[GrayZoneVoteOutcome] = None
    label_source: str = ""
    repo_id: str = ""
    base_ref: str = ""
    head_ref: str = ""


class ReasonerQueueRow(BaseModel):
    bundle_id: str
    candidate_id: str
    mode: ReasonerMode
    evidence_pack: dict[str, Any] = Field(default_factory=dict)
    pack_manifest: PackManifest
    graphcodebert_score: float = 0.0
    graphcodebert_pattern: str = ""
    ranking_phase: int = 0
    queued_at: datetime


# ---------------------------------------------------------------------------
# Run metadata
# ---------------------------------------------------------------------------

class RunMetadata(BaseModel):
    run_id: str
    repo_id: str = ""
    base_ref: str = ""
    head_ref: str = ""
    analysis_mode: AnalysisMode = AnalysisMode.diff_aware
    provider: str = ""
    token_estimator: str = "chars4"
    ranking_phase: int = 0
    low_stitcher_coverage: bool = False
    partial_reasoning: bool = False
    stitcher_coverage: StitcherCoverageReport = Field(default_factory=StitcherCoverageReport)
    graph_source_metadata: dict[str, Any] = Field(default_factory=dict)

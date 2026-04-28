"""Pydantic models for intent IR (manifest, chunks, units, summaries)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

IntentUnitKind = Literal[
    "invariant",
    "ownership",
    "security_policy",
    "api_contract_narrative",
    "data_model",
    "unknown",
]
ExtractorName = Literal["rules_v0", "llm_v0", "oft_markdown_v0"]
PathClassification = Literal["intent", "mixed"]

IntentTier = Literal["P0", "P1", "P2"]

TierSource = Literal[
    "policy_glob",
    "default",
    "frontmatter",
    "binding_glob",
    "oft_markdown_pattern",
    "merged",
]


class TierLineageEntry(BaseModel):
    source: TierSource
    tier_after: IntentTier


class DocSignalsRecord(BaseModel):
    git_commit_at: Optional[str] = None
    git_commit_sha: Optional[str] = None
    git_available: bool = False
    degraded_warning: Optional[str] = None


class IntentEvidence(BaseModel):
    chunk_id: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None


class IntentUnit(BaseModel):
    unit_id: str
    kind: IntentUnitKind = "unknown"
    natural_language: str = ""
    scope_hints: list[str] = Field(default_factory=list)
    evidence: list[IntentEvidence] = Field(default_factory=list)
    extractor: ExtractorName
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    effective_tier: IntentTier = "P2"
    normative_surface: bool = False
    tier_lineage: list[TierLineageEntry] = Field(default_factory=list)
    effective_weight: float = Field(ge=0.0, le=1.0, default=0.0)
    # OpenFastTrace interoperability (populated when extractor is oft_markdown_v0)
    oft_spec_item_id: Optional[str] = None
    oft_artifact_type: Optional[str] = None
    oft_item_name: Optional[str] = None
    oft_revision: Optional[int] = None
    oft_needs: list[str] = Field(default_factory=list)
    oft_covers: list[str] = Field(default_factory=list)
    oft_depends: list[str] = Field(default_factory=list)
    oft_status: Optional[str] = None
    oft_rationale_excerpt: Optional[str] = None
    oft_comment_excerpt: Optional[str] = None


class IntentChunkRecord(BaseModel):
    chunk_id: str
    source_relpath: str
    start_line: int
    end_line: int
    heading_stack: list[str] = Field(default_factory=list)
    text: str
    path_classification: PathClassification = "intent"
    effective_tier: IntentTier = "P2"
    normative_surface: bool = False
    tier_lineage: list[TierLineageEntry] = Field(default_factory=list)
    effective_weight: float = Field(ge=0.0, le=1.0, default=0.0)


class FencedBlockMeta(BaseModel):
    language: str = ""
    start_line: int
    end_line: int


class IntentManifestFile(BaseModel):
    relpath: str
    sha256: str
    byte_length: int
    path_classification: PathClassification = "intent"
    warnings: list[str] = Field(default_factory=list)
    policy_tier: IntentTier = "P2"
    doc_signals: DocSignalsRecord = Field(default_factory=DocSignalsRecord)
    tier_lineage: list[TierLineageEntry] = Field(default_factory=list)
    effective_tier: IntentTier = "P2"
    normative_surface: bool = False


class IntentManifest(BaseModel):
    intent_schema_version: int = 2
    repo_sha: str = "unknown"
    built_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    files: list[IntentManifestFile] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    policy_parse_warnings: list[str] = Field(default_factory=list)
    counts_by_tier: dict[str, int] = Field(default_factory=dict)
    p0_paths: list[str] = Field(default_factory=list)
    llm_enabled: bool = False
    llm_model: Optional[str] = None
    llm_calls: int = 0
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    truncation_warnings: list[str] = Field(default_factory=list)
    chunks_written: int = 0
    units_rules: int = 0
    units_llm: int = 0
    units_oft: int = 0
    oft_artifact_type_counts: dict[str, int] = Field(default_factory=dict)
    oft_unique_spec_ids: list[str] = Field(default_factory=list)
    oft_revision_warnings: list[str] = Field(default_factory=list)
    coverage_tags_found: int = 0


class IntentFileSummary(BaseModel):
    source_relpath: str
    summary: str
    bullet_claims: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class IntentRepoSummary(BaseModel):
    summary: str
    themes: list[str] = Field(default_factory=list)
    file_relpaths: list[str] = Field(default_factory=list)


class CoverageTagRecord(BaseModel):
    """OFT-style coverage reference found in source (comment)."""

    source_relpath: str
    line: int
    tag_shape: Literal["short", "long"] = "long"
    covering_artifact: Optional[str] = None
    covered_spec_id: str
    raw_excerpt: str = ""


class TraceHintNode(BaseModel):
    id: str
    kind: str = "spec_item"
    source_chunk_id: Optional[str] = None


class TraceHintEdge(BaseModel):
    source_id: str
    target_id: str
    kind: Literal["covers", "depends"] = "covers"


class IntentTraceHints(BaseModel):
    """Lightweight graph hint for downstream Graphical Context (not full OFT aspec)."""

    nodes: list[TraceHintNode] = Field(default_factory=list)
    edges: list[TraceHintEdge] = Field(default_factory=list)
    coverage_tags: list[dict[str, Any]] = Field(default_factory=list)

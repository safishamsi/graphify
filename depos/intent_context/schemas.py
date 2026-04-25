"""Pydantic models for intent IR (manifest, chunks, units, summaries)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

IntentUnitKind = Literal[
    "invariant",
    "ownership",
    "security_policy",
    "api_contract_narrative",
    "data_model",
    "unknown",
]
ExtractorName = Literal["rules_v0", "llm_v0"]
PathClassification = Literal["intent", "mixed"]


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


class IntentChunkRecord(BaseModel):
    chunk_id: str
    source_relpath: str
    start_line: int
    end_line: int
    heading_stack: list[str] = Field(default_factory=list)
    text: str
    path_classification: PathClassification = "intent"


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


class IntentManifest(BaseModel):
    repo_sha: str = "unknown"
    built_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    files: list[IntentManifestFile] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)
    llm_enabled: bool = False
    llm_model: Optional[str] = None
    llm_calls: int = 0
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0
    truncation_warnings: list[str] = Field(default_factory=list)
    chunks_written: int = 0
    units_rules: int = 0
    units_llm: int = 0


class IntentFileSummary(BaseModel):
    source_relpath: str
    summary: str
    bullet_claims: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class IntentRepoSummary(BaseModel):
    summary: str
    themes: list[str] = Field(default_factory=list)
    file_relpaths: list[str] = Field(default_factory=list)

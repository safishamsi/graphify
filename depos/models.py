"""Pydantic models for diagnostics, blast radius, and LLM export."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DiagnosticCategory(str, Enum):
    type_error = "type_error"
    lint = "lint"
    security = "security"
    test_failure = "test_failure"
    build = "build"
    unresolved = "unresolved"
    unknown = "unknown"


class DiagnosticRef(BaseModel):
    id: str = ""
    category: DiagnosticCategory = DiagnosticCategory.unknown
    severity: str = "error"  # error | warning | note
    rule_id: str | None = None
    message: str = ""
    tool: str = ""
    uri: str = ""
    start_line: int = 0
    end_line: int = 0


class BlastRadiusResult(BaseModel):
    seed_files: list[str] = Field(default_factory=list)
    impacted_node_ids: list[str] = Field(default_factory=list)
    hop_depth: int = 2
    blast_score: float = 0.0
    defect_boost: float = 0.0
    summary: str = ""
    cross_owner_warnings: list[str] = Field(default_factory=list)


class LLMGraphExport(BaseModel):
    """Graph + error indices for Claude Code / MCP consumers."""

    graph: dict[str, Any]
    error_index: dict[str, list[dict[str, Any]]]
    edge_fault_index: list[dict[str, Any]]
    executive_summary: str = ""
    blast_radius: BlastRadiusResult | None = None

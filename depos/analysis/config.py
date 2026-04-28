"""Runtime configuration for the intelligence layer.

Lives separately from Supabase/Auth env vars — those are read only by
``depos.db``, ``depos.auth``, ``depos.supabase_client``, and the Next.js
``lib/supabase/*`` modules. Do NOT read ``SUPABASE_*`` / ``DATABASE_URL``
from here.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class IntentContextConfig(BaseModel):
    """Intent Context Layer: doc discovery, chunking, rules + optional OpenAI."""

    llm_mode: str = "auto"  # auto | rules | llm
    max_tokens_per_call: int = 4096
    max_input_bytes_per_repo: int = 5_000_000
    max_chunks_per_run: int = 500
    max_bytes_per_file: int = 512_000
    chunk_max_chars: int = 8000
    chunk_overlap_chars: int = 400
    intent_openai_model: Optional[str] = Field(
        default=None,
        description="If set, overrides OPENAI_MODEL for intent extraction and summaries only.",
    )
    fenced_code_policy: str = "strip"  # strip | annotate
    enable_tag_scan: bool = True
    tag_scan_globs: list[str] = Field(
        default_factory=lambda: [
            "**/*.py",
            "**/*.go",
            "**/*.rs",
            "**/*.java",
            "**/*.ts",
            "**/*.tsx",
            "**/*.js",
            "**/*.jsx",
            "**/*.c",
            "**/*.h",
            "**/*.cpp",
            "**/*.cs",
            "**/*.sql",
            "**/*.sh",
        ],
    )
    #: When enabled, populate ``IntentManifestFile.doc_signals`` from ``git log -1``.
    enable_doc_git_signals: bool = True
    #: When set (``P0``/``P1``/``P2``), overrides YAML ``default_tier`` without editing the file.
    default_intent_tier: Optional[str] = Field(default=None)


class VerifierPolicy(BaseModel):
    min_edge_confidence_for_confirmed: float = 0.8
    min_edge_confidence_for_partially_confirmed: float = 0.6
    phantom_anchor_short_circuit: bool = True
    full_repo_scan_confidence_delta: float = 0.1


class CandidateBudget(BaseModel):
    max_seeds: int = 80
    max_seeds_per_diff: int = 80
    max_paths_per_seed: int = 10
    max_hop_count: int = 6
    high_churn_file_threshold: int = 50
    high_churn_file_sample: int = 20


class BundleBudget(BaseModel):
    token_budget_default: int = 8000
    token_estimator: str = "chars4"  # pinned default; tiktoken if installed & enabled
    allow_tiktoken: bool = True
    extra_source_roots: list[str] = Field(default_factory=list)
    path_aliases: dict[str, str] = Field(default_factory=dict)
    min_snippet_chars: int = 80
    min_evidence_quality_for_reasoner: str = "embedded"  # full | embedded | label_only
    min_evidence_score_for_reasoner: float = 0.00


class ReasonerProviderConfig(BaseModel):
    provider: str = "gemma"  # gemma | openai | ollama | stub
    max_retries: int = 2
    gemma_api_url: Optional[str] = None
    gemma_model: str = "gemma-4"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    ollama_host: Optional[str] = None
    ollama_model: str = "gemma:2b"
    default_max_tokens: int = 1000
    # JSON path expressions used to extract the model's text reply from the
    # provider response. Override per-deployment (e.g. Vertex AI Gemma vs
    # an Ollama-style server). The Gemma provider tries the configured path
    # first, then falls back through a known list of common shapes.
    gemma_response_path: str = "response"
    openai_response_path: str = "choices[0].message.content"
    ollama_response_path: str = "response"


class GrayZoneConfig(BaseModel):
    enabled: bool = True
    model_a_provider: str = "gemma"
    model_b_provider: str = "gemma"
    model_c_provider: str = "gemma"
    unconfirmed_confidence_threshold: float = 0.75


class RankerConfig(BaseModel):
    ranking_phase_override: Optional[int] = None  # force a phase for tests
    use_graphcodebert: bool = False
    graphcodebert_model_name: str = "microsoft/graphcodebert-base"
    graphcodebert_cache_dir: str | None = None
    graphcodebert_device: str | None = None
    graphcodebert_local_files_only: bool = False
    phase_0_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "cross_language_seam_count": 0.3,
            "changed_node_density": 0.25,
            "unresolved_symbol_count": 0.2,
            "removed_entity_references": 0.15,
            "missing_guard_signals": 0.1,
            "graphcodebert_score": 0.05,
        }
    )


class IntelligenceConfig(BaseModel):
    data_dir: Path = Field(default_factory=lambda: Path(os.environ.get("DEPOS_DATA", "depos-data")))
    run_output_subdir: str = "intelligence"

    # Module 1 defaults
    migration_glob: str = "supabase/migrations/*.sql"
    migration_timestamp_pattern: str = r"(\d{14})_.*\.sql"

    # Module 1 coverage threshold
    low_stitcher_coverage_threshold: float = 0.7

    # Replay
    replay_stale_threshold_days: int = 7

    prompt_globs: list[str] = Field(
        default_factory=lambda: [
            "**/prompts/**/*.{md,toml,json,prompt}",
            "**/.cursor/rules/*.md",
            "**/agents/**/*.{md,toml}",
        ]
    )
    openapi_globs: list[str] = Field(
        default_factory=lambda: [
            "**/openapi.yaml",
            "**/openapi.yml",
            "**/openapi.json",
        ]
    )

    # Module 2 optional expansion: lexical/heuristic AI-style seeds until a
    # real embedding model is wired in.
    enable_ai_driven_seeds: bool = False

    # Branch ref for migration branch-state resolution. ``None`` means "HEAD".
    branch_ref: Optional[str] = None

    verifier: VerifierPolicy = Field(default_factory=VerifierPolicy)
    candidates: CandidateBudget = Field(default_factory=CandidateBudget)
    bundles: BundleBudget = Field(default_factory=BundleBudget)
    reasoner: ReasonerProviderConfig = Field(default_factory=ReasonerProviderConfig)
    gray_zone: GrayZoneConfig = Field(default_factory=GrayZoneConfig)
    ranker: RankerConfig = Field(default_factory=RankerConfig)
    intent_context: IntentContextConfig = Field(default_factory=IntentContextConfig)


def load_config_from_env() -> IntelligenceConfig:
    """Build a config from DEPOS_INTEL_* env vars where present. Unknown
    vars are ignored; everything falls back to the defaults above."""
    cfg = IntelligenceConfig()
    cfg.reasoner.provider = os.environ.get("DEPOS_INTEL_PROVIDER", cfg.reasoner.provider)
    cfg.reasoner.openai_api_key = os.environ.get("OPENAI_API_KEY", cfg.reasoner.openai_api_key)
    cfg.reasoner.openai_model = os.environ.get("OPENAI_MODEL", cfg.reasoner.openai_model)
    cfg.reasoner.gemma_api_url = os.environ.get("GEMMA_API_URL", cfg.reasoner.gemma_api_url)
    cfg.reasoner.gemma_model = os.environ.get("GEMMA_MODEL", cfg.reasoner.gemma_model)
    cfg.reasoner.gemma_response_path = os.environ.get(
        "GEMMA_RESPONSE_PATH", cfg.reasoner.gemma_response_path
    )
    cfg.reasoner.openai_response_path = os.environ.get(
        "OPENAI_RESPONSE_PATH", cfg.reasoner.openai_response_path
    )
    cfg.reasoner.ollama_response_path = os.environ.get(
        "OLLAMA_RESPONSE_PATH", cfg.reasoner.ollama_response_path
    )
    cfg.reasoner.ollama_host = os.environ.get("OLLAMA_HOST", cfg.reasoner.ollama_host)
    cfg.reasoner.ollama_model = os.environ.get("OLLAMA_MODEL", cfg.reasoner.ollama_model)
    cfg.ranker.use_graphcodebert = os.environ.get("DEPOS_INTEL_USE_GRAPHCODEBERT", "").strip().lower() in {"1", "true", "yes", "on"}
    cfg.ranker.graphcodebert_cache_dir = os.environ.get("DEPOS_INTEL_GRAPHCODEBERT_CACHE", cfg.ranker.graphcodebert_cache_dir)
    cfg.ranker.graphcodebert_device = os.environ.get("DEPOS_INTEL_GRAPHCODEBERT_DEVICE", cfg.ranker.graphcodebert_device)
    cfg.ranker.graphcodebert_local_files_only = os.environ.get("DEPOS_INTEL_GRAPHCODEBERT_LOCAL_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        cfg.bundles.token_budget_default = int(os.environ.get("DEPOS_INTEL_TOKEN_BUDGET", cfg.bundles.token_budget_default))
    except ValueError:
        pass

    extra_roots = os.environ.get("DEPOS_INTEL_EXTRA_SOURCE_ROOTS")
    if extra_roots:
        cfg.bundles.extra_source_roots = [
            part for part in extra_roots.split(os.pathsep) if part.strip()
        ]
    aliases_json = os.environ.get("DEPOS_INTEL_PATH_ALIASES_JSON")
    if aliases_json:
        try:
            import json as _json

            parsed = _json.loads(aliases_json)
            if isinstance(parsed, dict):
                cfg.bundles.path_aliases = {str(k): str(v) for k, v in parsed.items()}
        except ValueError:
            pass
    min_evidence = os.environ.get("DEPOS_INTEL_MIN_EVIDENCE")
    if min_evidence in {"full", "embedded", "label_only"}:
        cfg.bundles.min_evidence_quality_for_reasoner = min_evidence
    try:
        cfg.bundles.min_evidence_score_for_reasoner = float(
            os.environ.get(
                "DEPOS_INTEL_MIN_EVIDENCE_SCORE",
                cfg.bundles.min_evidence_score_for_reasoner,
            )
        )
    except ValueError:
        pass

    intent_mode = os.environ.get("DEPOS_INTEL_INTENT_LLM", "").strip().lower()
    if intent_mode in {"auto", "rules", "llm"}:
        cfg.intent_context.llm_mode = intent_mode
    cfg.intent_context.intent_openai_model = os.environ.get(
        "DEPOS_INTEL_INTENT_MODEL", cfg.intent_context.intent_openai_model
    )
    for key, attr in (
        ("DEPOS_INTEL_INTENT_MAX_TOKENS", "max_tokens_per_call"),
        ("DEPOS_INTEL_INTENT_MAX_REPO_BYTES", "max_input_bytes_per_repo"),
        ("DEPOS_INTEL_INTENT_MAX_CHUNKS", "max_chunks_per_run"),
        ("DEPOS_INTEL_INTENT_MAX_FILE_BYTES", "max_bytes_per_file"),
        ("DEPOS_INTEL_INTENT_CHUNK_CHARS", "chunk_max_chars"),
        ("DEPOS_INTEL_INTENT_CHUNK_OVERLAP", "chunk_overlap_chars"),
    ):
        raw = os.environ.get(key)
        if raw:
            try:
                setattr(cfg.intent_context, attr, int(raw))
            except ValueError:
                pass
    fenced = os.environ.get("DEPOS_INTEL_INTENT_FENCED", "").strip().lower()
    if fenced in {"strip", "annotate"}:
        cfg.intent_context.fenced_code_policy = fenced
    cfg.intent_context.enable_tag_scan = os.environ.get(
        "DEPOS_INTEL_INTENT_TAG_SCAN", "1"
    ).strip().lower() not in {"0", "false", "off", "no"}
    cfg.intent_context.enable_doc_git_signals = os.environ.get(
        "DEPOS_INTEL_INTENT_GIT_SIGNALS", "1"
    ).strip().lower() not in {"0", "false", "off", "no"}
    git_typed = os.environ.get("DEPOS_INTEL_INTENT_DEFAULT_TIER", "").strip().upper()
    if git_typed in {"P0", "P1", "P2"}:
        cfg.intent_context.default_intent_tier = git_typed
    return cfg

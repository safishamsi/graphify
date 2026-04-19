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


class ReasonerProviderConfig(BaseModel):
    provider: str = "gemma"  # gemma | openai | ollama
    max_retries: int = 2
    gemma_api_url: Optional[str] = None
    gemma_model: str = "gemma-4"
    openai_api_key: Optional[str] = None
    ollama_host: Optional[str] = None
    default_max_tokens: int = 1000


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


def load_config_from_env() -> IntelligenceConfig:
    """Build a config from DEPOS_INTEL_* env vars where present. Unknown
    vars are ignored; everything falls back to the defaults above."""
    cfg = IntelligenceConfig()
    cfg.reasoner.provider = os.environ.get("DEPOS_INTEL_PROVIDER", cfg.reasoner.provider)
    cfg.reasoner.openai_api_key = os.environ.get("OPENAI_API_KEY", cfg.reasoner.openai_api_key)
    cfg.reasoner.gemma_api_url = os.environ.get("GEMMA_API_URL", cfg.reasoner.gemma_api_url)
    cfg.reasoner.gemma_model = os.environ.get("GEMMA_MODEL", cfg.reasoner.gemma_model)
    cfg.reasoner.ollama_host = os.environ.get("OLLAMA_HOST", cfg.reasoner.ollama_host)
    cfg.ranker.use_graphcodebert = os.environ.get("DEPOS_INTEL_USE_GRAPHCODEBERT", "").strip().lower() in {"1", "true", "yes", "on"}
    cfg.ranker.graphcodebert_cache_dir = os.environ.get("DEPOS_INTEL_GRAPHCODEBERT_CACHE", cfg.ranker.graphcodebert_cache_dir)
    cfg.ranker.graphcodebert_device = os.environ.get("DEPOS_INTEL_GRAPHCODEBERT_DEVICE", cfg.ranker.graphcodebert_device)
    cfg.ranker.graphcodebert_local_files_only = os.environ.get("DEPOS_INTEL_GRAPHCODEBERT_LOCAL_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        cfg.bundles.token_budget_default = int(os.environ.get("DEPOS_INTEL_TOKEN_BUDGET", cfg.bundles.token_budget_default))
    except ValueError:
        pass
    return cfg

"""Orchestrate intent context discovery, chunking, rules + optional LLM, artifacts."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from depos.analysis.config import IntelligenceConfig
from depos.intent_context.chunk import chunk_normalized_text
from depos.intent_context.discover import discover_intent_files
from depos.intent_context.doc_signals import git_doc_signals
from depos.intent_context.intent_policy import load_intent_policy
from depos.intent_context.llm_v0 import extract_units_llm_batched
from depos.intent_context.normalize import normalize_markdown
from depos.intent_context.normative import (
    compute_file_tier_bundle,
    enrich_chunk_tier_inplace,
    enrich_units_from_chunks,
)
from depos.intent_context.oft_markdown_v0 import extract_oft_markdown_v0
from depos.intent_context.rules_v0 import extract_rules_v0
from depos.intent_context.schemas import DocSignalsRecord, IntentManifest, IntentManifestFile
from depos.intent_context.summaries import summarize_files, summarize_repo
from depos.intent_context.tag_scan import (
    build_trace_hints_from_oft_units,
    oft_inventory_from_units,
    scan_coverage_tags,
)

logger = logging.getLogger(__name__)

_OFT_ID_CAP = 500
_P0_PATH_CAP = 200


def _repo_sha(repo_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


def _fenced_policy(cfg: IntelligenceConfig) -> str:
    p = cfg.intent_context.fenced_code_policy
    if p not in ("strip", "annotate"):
        return "strip"
    return p


def _llm_addon_enabled(cfg: IntelligenceConfig) -> bool:
    mode = (cfg.intent_context.llm_mode or "auto").lower()
    key = cfg.reasoner.openai_api_key
    if mode == "rules":
        return False
    if mode == "llm":
        return bool(key)
    return bool(key)


def run_intent_context_build(
    repo_root: Path,
    output_dir: Path,
    config: IntelligenceConfig,
    *,
    intent_llm_override: str | None = None,
) -> int:
    """Build intent artifacts under ``output_dir``. Returns process exit code."""
    if intent_llm_override in {"auto", "rules", "llm"}:
        config.intent_context.llm_mode = intent_llm_override

    if config.intent_context.llm_mode == "llm" and not config.reasoner.openai_api_key:
        print(
            "intent-context: llm mode requires OPENAI_API_KEY (or set --intent-llm rules).",
            file=sys.stderr,
        )
        return 2

    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    icfg = config.intent_context
    discovered, disc_warnings = discover_intent_files(repo_root, icfg)
    fence = _fenced_policy(config)

    policy, policy_warnings = load_intent_policy(repo_root)
    policy_parse_warnings: list[str] = list(policy_warnings)
    dtier = getattr(icfg, "default_intent_tier", None)
    if dtier in {"P0", "P1", "P2"}:
        policy = replace(policy, default_tier=dtier)

    all_chunks: list = []
    manifest_files: list[IntentManifestFile] = []
    units_rules: list = []
    units_oft: list = []
    trunc: list[str] = list(disc_warnings)

    for df in discovered:
        try:
            raw = df.abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            trunc.append(f"{df.relpath}: read failed (tiers/git signals skipped): {e}")
            continue

        policy_tier, effective_tier, file_lineage, file_ns = compute_file_tier_bundle(
            policy=policy,
            relpath_posix=df.relpath,
            raw_text=raw,
        )
        doc_sig = (
            git_doc_signals(repo_root, df.relpath)
            if getattr(icfg, "enable_doc_git_signals", True)
            else DocSignalsRecord(
                git_available=False,
                degraded_warning="doc git signals disabled (DEPOS_INTEL_INTENT_GIT_SIGNALS)",
            )
        )

        try:
            nd = normalize_markdown(df.abs_path, fence)  # type: ignore[arg-type]
        except OSError as e:
            trunc.append(f"{df.relpath}: normalize failed: {e}")
            continue
        chunks = chunk_normalized_text(
            df.relpath,
            nd.text,
            icfg,
            df.path_classification,
        )
        for ch in chunks:
            enrich_chunk_tier_inplace(
                ch,
                file_lineage=file_lineage,
                file_effective=effective_tier,
                file_ns=file_ns,
            )

        manifest_files.append(
            IntentManifestFile(
                relpath=df.relpath,
                sha256=df.sha256,
                byte_length=df.byte_length,
                path_classification=df.path_classification,  # type: ignore[arg-type]
                warnings=list(df.warnings),
                policy_tier=policy_tier,
                doc_signals=doc_sig,
                tier_lineage=file_lineage,
                effective_tier=effective_tier,
                normative_surface=file_ns,
            )
        )
        for ch in chunks:
            for u in extract_rules_v0(ch.text, chunk_id=ch.chunk_id, start_line=ch.start_line):
                units_rules.append(u)
            for u in extract_oft_markdown_v0(ch.text, chunk_id=ch.chunk_id, start_line=ch.start_line):
                units_oft.append(u)
            all_chunks.append(ch)

    if len(all_chunks) > icfg.max_chunks_per_run:
        trunc.append(
            f"truncated chunks from {len(all_chunks)} to {icfg.max_chunks_per_run} (max_chunks_per_run)"
        )
        all_chunks = all_chunks[: icfg.max_chunks_per_run]

    coverage_records: list = []
    if icfg.enable_tag_scan and icfg.tag_scan_globs:
        try:
            coverage_records = scan_coverage_tags(
                repo_root,
                icfg.tag_scan_globs,
                max_bytes_per_file=icfg.max_bytes_per_file,
            )
        except Exception:
            logger.exception("tag_scan")
            trunc.append("tag_scan: unexpected error (see logs)")

    oft_counts, oft_unique, oft_rev_warnings = oft_inventory_from_units(units_oft)
    oft_unique_capped = oft_unique[:_OFT_ID_CAP]
    if len(oft_unique) > _OFT_ID_CAP:
        trunc.append(f"oft_unique_spec_ids truncated to {_OFT_ID_CAP} entries")

    trace_hints = build_trace_hints_from_oft_units(units_oft, coverage_records)

    llm_on = _llm_addon_enabled(config)
    units_llm: list = []
    llm_calls = 0
    llm_tin = 0
    llm_tout = 0
    file_summaries = []
    repo_summary = None

    if llm_on:
        try:
            units_llm, c1, t1, t2 = extract_units_llm_batched(config, all_chunks)
            llm_calls += c1
            llm_tin += t1
            llm_tout += t2
        except Exception:
            logger.exception("llm_v0 extraction")
            trunc.append("llm_v0: unexpected error (see logs)")
        try:
            fs, c2, t3, t4 = summarize_files(config, all_chunks)
            file_summaries = fs
            llm_calls += c2
            llm_tin += t3
            llm_tout += t4
        except Exception:
            logger.exception("file summaries")
            trunc.append("file summaries: unexpected error (see logs)")
        try:
            rs, c3, t5, t6 = summarize_repo(config, file_summaries)
            repo_summary = rs
            llm_calls += c3
            llm_tin += t5
            llm_tout += t6
        except Exception:
            logger.exception("repo summary")
            trunc.append("repo summary: unexpected error (see logs)")

    chunk_by_id = {ch.chunk_id: ch for ch in all_chunks}
    enrich_units_from_chunks(units_rules, chunk_by_id)
    enrich_units_from_chunks(units_oft, chunk_by_id)
    enrich_units_from_chunks(units_llm, chunk_by_id)

    model = None
    if llm_on:
        model = icfg.intent_openai_model or config.reasoner.openai_model

    counts_by_tier: dict[str, int] = {"P0": 0, "P1": 0, "P2": 0}
    for mf in manifest_files:
        counts_by_tier[mf.effective_tier] = counts_by_tier.get(mf.effective_tier, 0) + 1
    p0_paths = sorted(m.relpath for m in manifest_files if m.effective_tier == "P0")[:_P0_PATH_CAP]

    manifest = IntentManifest(
        repo_sha=_repo_sha(repo_root),
        files=manifest_files,
        parse_warnings=trunc,
        policy_parse_warnings=policy_parse_warnings,
        counts_by_tier=counts_by_tier,
        p0_paths=p0_paths,
        llm_enabled=llm_on,
        llm_model=model,
        llm_calls=llm_calls,
        llm_tokens_in=llm_tin,
        llm_tokens_out=llm_tout,
        truncation_warnings=[w for w in trunc if "truncat" in w.lower() or "cap" in w.lower()],
        chunks_written=len(all_chunks),
        units_rules=len(units_rules),
        units_llm=len(units_llm),
        units_oft=len(units_oft),
        oft_artifact_type_counts=oft_counts,
        oft_unique_spec_ids=oft_unique_capped,
        oft_revision_warnings=oft_rev_warnings,
        coverage_tags_found=len(coverage_records),
    )

    (output_dir / "intent_manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    chunks_path = output_dir / "intent_chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(ch.model_dump(mode="json")) + "\n")

    combined_units = (
        [u.model_dump(mode="json") for u in units_rules]
        + [u.model_dump(mode="json") for u in units_oft]
        + [u.model_dump(mode="json") for u in units_llm]
    )
    (output_dir / "intent_units.json").write_text(
        json.dumps(combined_units, indent=2),
        encoding="utf-8",
    )

    with (output_dir / "intent_coverage_tags.jsonl").open("w", encoding="utf-8") as f:
        for rec in coverage_records:
            f.write(json.dumps(rec.model_dump(mode="json")) + "\n")

    (output_dir / "intent_trace_hints.json").write_text(
        json.dumps(trace_hints.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    summaries_path = output_dir / "intent_file_summaries.jsonl"
    if llm_on and file_summaries:
        with summaries_path.open("w", encoding="utf-8") as f:
            for s in file_summaries:
                f.write(json.dumps(s.model_dump(mode="json")) + "\n")
    else:
        summaries_path.write_text(
            json.dumps({"skipped_reason": "llm_disabled_or_no_output"}) + "\n",
            encoding="utf-8",
        )

    repo_path = output_dir / "intent_repo_summary.json"
    if llm_on and repo_summary:
        repo_path.write_text(json.dumps(repo_summary.model_dump(mode="json"), indent=2), encoding="utf-8")
    else:
        repo_path.write_text(
            json.dumps({"skipped_reason": "llm_disabled_or_no_output"}),
            encoding="utf-8",
        )

    return 0

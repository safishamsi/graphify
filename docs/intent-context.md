# Intent Context Layer

The Intent Context Layer discovers **intent-bearing documentation** (Markdown, READMEs, ADRs, GitHub policy docs), normalizes and **chunks** it, then emits a **versioned, provenance-rich intermediate representation (IR)** for downstream consumers (for example a future Graphical Context Layer that compares intent to the AST graph).

It does **not** mutate the code graph or tree-sitter output. Intent entries are **claims with evidence** (file, chunk, line ranges), not ground truth.

**Schema version:** `intent_manifest.json` includes **`intent_schema_version`** (currently **2**). New fields are additive; readers that do not care about tiers should ignore unknown keys. **Do not** treat raw `confidence` from extractors as sufficient for merge or CI gating—prefer **`effective_weight`** and **`effective_tier`** together (see [Tiers and gating](#tiers-and-gating)).

---

## Tiers and gating

Tiers are **policy-as-code**, not model scores. They use internal IDs **`P0` | `P1` | `P2`** (see table). **Precedence** merges policy globs, YAML frontmatter (`normative: true`), optional `binding_globs`, and OFT backtick IDs in chunk text. The merge rule is **deterministic** and **auditable** via `tier_lineage` on each file, chunk, and unit.

| Tier | Intended use | Typical downstream behavior |
|------|----------------|----------------------------|
| **P0** | Binding intent jurisdiction (architecture, regulated policy, contractual ADRs when policy says so) | May **block merge / fail CI** for doc↔graph conflicts only when a consumer enables strict mode |
| **P1** | Normative but not blocking (ADR drafts, OFT IDs, `normative: true`, `binding_globs`) | **PR comment / checklist** |
| **P2** | Informative / ambient (generic README prose) | **Ignore for gates** unless verbose diagnostics |

Rank order for merging: **P0 = strictest → P1 → P2 = loosest**, implemented as integer ranks **`P0 = 0, P1 = 1, P2 = 2`**.

**Merge rule (deterministic)**

1. `tier_policy = first_matching(tier_rules, relpath)` from `.depos/intent.yaml`; if none matches, **`default_tier`**.
2. **`effective_tier`** = minimum rank among: policy tier **and** bumps from:
   - `binding_globs`: treat as normative jurisdiction (floor toward **at least P1**);
   - frontmatter **`normative: true`** (same floor);
   - **OFT** `` `type~name~revision` `` in a **chunk** (floors that chunk toward **at least P1**).
   Stricter tiers are never overridden by weaker bumps (**P0** set by policy is preserved).

Pseudo-code:

```python
tier_rank = {"P0": 0, "P1": 1, "P2": 2}
effective_rank = min(
    tier_rank[policy_or_default(path)],
    binding_and_frontmatter_floor(path),
    oft_chunk_floor(chunk),
)
```

**Downstream weight:** For each **`IntentUnit`**, **`effective_weight`** = `confidence × tier_multiplier(effective_tier)` with multipliers **`P0: 1.0`**, **`P1: 0.85`**, **`P2: 0.45`**, clipped to **`[0, 1]`**. Chunks expose **`effective_weight`** = the tier multiplier alone (no extractor confidence at chunk level). Consumers should gate on **`effective_weight`** and **`effective_tier`**, not on raw **`confidence`** alone.

---

## Pipeline order (top-down)

```text
checkout_at_SHA
  → intent-context build   (this layer)
  → graphify snapshot      (structural truth)
  → graphical context / detectors / rank / reason
```

Intent artifacts are designed to feed **graphical context** and similar tools; the detector spine can stay unchanged until you wire cross-layer signals.

## CLI

```bash
depos-intel intent-context build --repo-root . --output-dir ./intent-out
```

- **`--intent-llm auto|rules|llm`** — Overrides `DEPOS_INTEL_INTENT_LLM`. Default **`auto`**: if `OPENAI_API_KEY` is set, runs **`llm_v0`** unit extraction plus file/repo summaries **in addition to** **`rules_v0`**. With **`rules`**, no network calls (CI-friendly). With **`llm`**, OpenAI is **required**; the command exits non-zero if the key is missing.

## Configuration

### Environment

| Env / setting | Purpose |
|----------------|---------|
| `OPENAI_API_KEY` | When set and mode is `auto`, enables the LLM add-on (same variable as the reasoner). |
| `OPENAI_MODEL` | Default chat model; reused unless `DEPOS_INTEL_INTENT_MODEL` is set. |
| `DEPOS_INTEL_INTENT_LLM` | `auto` (default), `rules`, or `llm`. |
| `DEPOS_INTEL_INTENT_MODEL` | Optional model override **only** for intent extraction/summaries. |
| `DEPOS_INTEL_INTENT_MAX_TOKENS`, `..._MAX_REPO_BYTES`, `..._MAX_CHUNKS`, `..._MAX_FILE_BYTES`, `..._CHUNK_CHARS`, `..._CHUNK_OVERLAP` | Caps and chunking (see [`depos/analysis/config.py`](../depos/analysis/config.py) `IntentContextConfig`). |
| `DEPOS_INTEL_INTENT_FENCED` | `strip` (default) or `annotate` — fenced ``` blocks are removed or replaced with an HTML comment marker in chunk text. |
| `DEPOS_INTEL_INTENT_TAG_SCAN` | `1` (default) or `0` — scan code globs for OpenFastTrace-style tags (`[impl->req~foo~1]`). |
| `DEPOS_INTEL_INTENT_DEFAULT_TIER` | Optional override **`P0` / `P1` / `P2`** for YAML `default_tier` (no file edit). |
| `DEPOS_INTEL_INTENT_GIT_SIGNALS` | `1` (default) or `0` — populate per-file git last-commit metadata in `doc_signals`. When `0`, git fields are empty and a **degraded** note is recorded. |

### Repo file `.depos/intent.yaml`

```yaml
intent_schema_policy: 1   # optional: policy-file shape version

# Include extra markdown (in addition to defaults in code)
include_globs:
  - "design/**/*.md"
exclude_globs:
  - "**/vendor/**"

# Tier policy — first matching tier_rules glob wins; else default_tier (P0 strictest for merge)
default_tier: P2
tier_rules:
  - glob: "docs/architecture/**/*.md"
    tier: P0
  - glob: "docs/adr/**/*.md"
    tier: P1

# Paths treated as normative jurisdiction (floors tier toward at least P1 unless policy already stricter)
binding_globs:
  - "policies/**/*.md"
```

Glob patterns support ``**`` (multi-segment) and POSIX ``/``. Invalid tier strings in YAML produce **warnings** and skip that rule row; malformed ``tier_rules`` entries are skipped with diagnostics in **`intent_manifest.policy_parse_warnings`**.


| File | Description |
|------|-------------|
| `intent_manifest.json` | `intent_schema_version` (**2**), repo SHA (`git rev-parse` when available), timestamps, per-file `sha256` / bytes, **`policy_tier`**, **`effective_tier`**, **`tier_lineage`**, **`doc_signals`** (git last-touch per file when enabled), **`normative_surface`**, `path_classification`, `parse_warnings`, **`policy_parse_warnings`**, **`counts_by_tier`**, capped **`p0_paths`**, LLM stats when enabled, chunk/unit counts. |
| `intent_chunks.jsonl` | Chunk fields plus **`effective_tier`**, **`normative_surface`**, **`tier_lineage`**, **`effective_weight`** (tier multiplier); `chunk_id`, `source_relpath`, line range, headings, normalized `text`, `path_classification`. |
| `intent_units.json` | **`IntentUnit`** including **`confidence`**, **`effective_tier`**, **`effective_weight`**, **`normative_surface`**, **`tier_lineage`**, extractor, evidence, optional OFT fields. |
| `intent_coverage_tags.jsonl` | One JSON object per line: coverage references found in source comments (long form `[impl->req~id~1]`, short form `[[name:rev]]`). |
| `intent_trace_hints.json` | Lightweight graph hint: **nodes** (OFT spec IDs from docs), **edges** (`covers`, `depends` from parsed doc blocks), **coverage_tags** (raw tag locations for joining to the AST by path/line). Not a full OpenFastTrace `aspec` export. |
| `intent_file_summaries.jsonl` | When LLM add-on runs: one JSON object per file (`summary`, `bullet_claims`, `chunk_ids`). Otherwise a single stub line with `skipped_reason`. |
| `intent_repo_summary.json` | When LLM add-on produces a rollup: `summary`, `themes`, `file_relpaths`. Otherwise a stub with `skipped_reason`. |

## OpenFastTrace interoperability (optional strict layer)

[OpenFastTrace](https://github.com/itsallcode/openfasttrace) models **specification items** with stable IDs (`` `type~name~revision` ``), `Needs` / `Covers` / `Depends`, revisions that invalidate stale links, and **code comment tags** pointing from implementation to spec IDs.

graphify’s intent layer **does not replace** OFT or embed the Java engine. It **consumes compatible Markdown** and **tag shapes** so you can mix:

- **Broad discovery:** `rules_v0` + `llm_v0` on normal READMEs and ADRs.
- **Audit-grade items:** when authors use OFT-style IDs in backticks, `oft_markdown_v0` emits structured units plus `intent_trace_hints.json` edges for `Covers` / `Depends`.

**Scan guards:** HTML comments `<!-- oft:off -->` … `<!-- oft:on -->` (and RST-style `.. oft:off` / `.. oft:on`) strip regions before chunking—same idea as OFT’s `oft:off` switch so examples do not create false spec items.

**Merge precedence (recommended for consumers):** First apply **[Tiers and gating](#tiers-and-gating)** using **`effective_weight`** and **`effective_tier`**. Within the same **`chunk_id`** and similar tier, prefer **higher `confidence`**. If tied, prefer **`oft_markdown_v0`** (explicit ID) over **`llm_v0`**, then over **`rules_v0`** heuristics—unless you explicitly want LLM nuance to override weak OFT stubs.

**Do not** treat OFT tag presence or `Needs` lists as proof of correctness—only as **link evidence**; the AST graph and detectors still own behavior truth.

## Graphical Context Layer — input spec (handoff)

**Required for alignment work**

1. **`intent_manifest.intent_schema_version`** and **`intent_manifest.repo_sha`** — Pick a downstream branch for tier fields (`>= 2`); tie IR to the same commit as the graph snapshot.
2. **`intent_manifest.files[].doc_signals`** — When git is unavailable, `git_available` is false and **`degraded_warning`** is set; freshness is informational only until you enable git or supply out-of-band provenance (export/SBOM).
3. **`intent_chunks.jsonl`** — Stable **`chunk_id`** keys; **`intent_units[].evidence[].chunk_id`** MUST reference existing chunks.
4. **`intent_units.json`** — Treat rows as hypotheses; **gate** using **`effective_tier`** + **`effective_weight`**, then fall back to **`extractor`** + **`confidence`** tie-breaks described above—not raw **`confidence`** alone for policy decisions.
5. **`path_classification`** — `mixed` hints that prose lives next to implementation trees (higher drift risk).

**Merge policy (v1):** Prefer higher **`effective_tier` strictness** (P0) for blocking integrations when paired with extractor agreement. If `rules_v0` and `llm_v0` cite the same `chunk_id` at the **same tier**, prefer higher **`confidence`**, or prefer **`llm_v0`** if equal. Prefer **`oft_markdown_v0`** where it carries an explicit ID. Document deviations in your consumer.

## Implementation layout

- Tier policy resolver: [`depos/intent_context/intent_policy.py`](../depos/intent_context/intent_policy.py)
- Git freshness: [`depos/intent_context/doc_signals.py`](../depos/intent_context/doc_signals.py)
- Normative cues + merges: [`depos/intent_context/normative.py`](../depos/intent_context/normative.py)
- Package: [`depos/intent_context/`](../depos/intent_context/)
- Glob discovery / path hygiene aligns with [`depos/ingest/prompts.py`](../depos/ingest/prompts.py) (walk + denylist); intent IR stays **separate** from the code graph.

**Limitations:** v1 tiers are **deterministic** and never call an LLM. **Doc-vs-code churn** relations and richer freshness (beyond last git touch) are deferred. **`intent_doc_signals.jsonl`** is intentionally **not** emitted—use **`intent_manifest`** as the canonical per-file **`doc_signals`** mirror to avoid enterprise confusion.

## Non-goals

- No NetworkX / graph mutation from this layer.
- No SARIF or “confirmed vulnerability” wording—only **intent claims**.
- No automatic graph edges from LLM output without a separate verification story.

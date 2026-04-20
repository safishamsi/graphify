# `--extract-model`: Opt-In Model Routing for Step 3B

## Summary

`/graphify`'s Step 3B dispatches one semantic-extraction subagent per chunk. Today those subagents inherit the parent Claude Code model, which is often Opus — overkill for the portion of the work that is simple pattern matching.

This change adds an **opt-in** `--extract-model sonnet|opus|auto` flag. With no flag, graphify behaves exactly as before. Only users who explicitly pass the flag get model pinning or the auto-heuristic.

No default behavior change. No Python package change. Only `skill.md`.

## Why

Step 3B extraction is the cost hotspot (1 subagent per chunk × many chunks on large corpora). The subagent's job mixes two kinds of work:

| Sub-task | Nature | Quality ceiling on Sonnet 4.6 |
|---|---|---|
| EXTRACTED edges (explicit import / cite / call) | pattern matching | near parity with Opus |
| JSON schema compliance, file I/O, basic vision | structured output | near parity |
| **INFERRED edges** (latent deps, shared assumptions) | judgment | Opus materially better |
| **`semantically_similar_to`** (non-obvious cross-document links) | cross-document reasoning | Opus materially better — this is graphify's "surprise" feature |
| **Hyperedges** (3+ node shared patterns) | pattern abstraction | Opus moderately better |
| **`confidence_score` calibration** | fine-grained judgment | Opus distributes better; Sonnet clusters at 0.5/0.8 |

Running Opus over a code-heavy corpus that is dominated by EXTRACTED edges wastes budget. Running Sonnet under `--mode deep` (which intentionally pushes aggressive INFERRED extraction) sacrifices the quality that mode is asking for. A single flag resolves both.

## Behavior

A new flag, **opt-in**:

```
--extract-model sonnet|opus|auto
```

Resolution:

| User input | `EXTRACT_MODEL` | `model=` on Agent calls | Behavior |
|---|---|---|---|
| *(flag omitted)* | unset | not passed | **unchanged** — subagents inherit parent |
| `--extract-model sonnet` | `sonnet` | `model="sonnet"` | all chunks use Sonnet |
| `--extract-model opus` | `opus` | `model="opus"` | all chunks use Opus |
| `--extract-model auto` | result of heuristic below | `model=<result>` | corpus-shape routing |

### `auto` heuristic

Evaluated in order; first match wins. Inputs come from `graphify-out/.graphify_detect.json` (`total_files` and `len(files[category])`).

| Condition | Result | Rationale |
|---|---|---|
| `--mode deep` passed | `opus` | deep mode intentionally pushes aggressive INFERRED; reasoning pays off |
| `code_files / total_files > 0.8` | `sonnet` | AST carries a code-heavy corpus; semantic layer is thin |
| `(docs + papers) / total > 0.3` | `opus` | cross-document semantic edges (the main payoff) need judgment |
| otherwise | `sonnet` | cheap and adequate for mixed small corpora |

When the flag is given, `skill.md` instructs the orchestrator to print one line:

```
Extract model: sonnet (reason: auto-code-heavy)
```

When the flag is omitted, nothing is printed about the model — output is byte-identical to pre-flag graphify.

### Threshold rationale

- **`0.8` for code-heavy**: Below ~20% docs/papers the semantic-extraction subagent has few cross-file concept edges to find; the AST extractor in Part A already captures most of the structural signal. Sonnet's delta on EXTRACTED edges is small in this regime.
- **`0.3` for doc-heavy**: At or above roughly one-third docs/papers, `semantically_similar_to` begins producing the characteristic cross-document "surprise" edges that `graphify` advertises. Opus's judgment calibration materially improves those.
- Between the two (0.2–0.8 code, <0.3 docs/papers): falls through to `sonnet`. This is the common case of code-first projects with README and inline comments — Sonnet handles it well.

## Scope

- Single file touched in this PR: `graphify/skill.md` (Claude Code variant).
- Other assistant variants (`skill-codex.md`, `skill-trae.md`, `skill-aider.md`, etc.) are **not** changed. The `model` parameter on a dispatched subagent is a Claude-Code-specific mechanism; other CLIs have different model-selection surfaces.
- No Python package change. `detect.json` is already produced and contains all fields the heuristic needs.

## Considered alternatives

| Option | Why not |
|---|---|
| Add `haiku` to the choice set | Haiku 4.5 only wins over Sonnet in corpora where AST already dominates — the marginal gain is small, and the extra choice complicates both the UX and the heuristic. `sonnet|opus|auto` is clearer. |
| Change default (no opt-in) | Changes behavior for every existing `/graphify` invocation. Risks quality regressions users didn't opt into. Opt-in keeps the blast radius zero until a user explicitly chooses otherwise. |
| Per-chunk LLM meta-classifier | Requires an extra LLM call per chunk to decide which model to dispatch, burning budget to save budget. Static corpus-shape heuristic is within one rule of the ceiling. |
| Use an environment variable instead of a flag | Less discoverable; doesn't show up in `--help`/usage block. Flags are how every other opt-in already surfaces in `skill.md`. |

## Compatibility

- Cache (`graphify-out/.graphify_semantic_cache/`) is keyed on file content hash, not model. Changing `--extract-model` between runs does not invalidate cache — useful if a user toggles between Sonnet and Opus on the same corpus.
- No schema change to `graph.json`, `GRAPH_REPORT.md`, or any output file.
- Rollback: reverting `graphify/skill.md` to its prior version removes the opt-in entry point. No persistent state, no migration.

## Test plan (manual)

1. Small mixed corpus (~50 files, 60% code + 40% docs):
   - Run without flag → confirm no `Extract model:` line printed; graph looks identical to a known-good prior run.
   - Run with `--extract-model auto` → confirm prints `auto-doc-heavy` and resolves to `opus`.
   - Run with `--extract-model sonnet` → confirm prints `manual` and dispatches with `model="sonnet"`.
2. Code-only corpus (~50 files, 100% code):
   - Run with `--extract-model auto` → confirm resolves to `sonnet` (`auto-code-heavy`).
3. Run with `--mode deep --extract-model auto` → confirm resolves to `opus` (`auto-deep`), regardless of corpus shape.
4. Confirm `graph.json` INFERRED edges still exist under Sonnet; `confidence_score` distribution is reasonable (not collapsed to 0.5 across the board).

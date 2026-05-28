# Code Review — Terraform Branches

**Reviewer:** Claude (Opus 4.7), autonomous session, 2026-05-26
**Scope:** `extract-terraform`, `cross-file-refs`, `worked-terraform-infra`
**Base:** `fork/v8` @ `3efae38`

---

## TL;DR — Do not open `extract-terraform` as a PR

**PR [#416 by Maurice Wittek](https://github.com/safishamsi/graphify/pull/416) is going to land.** It is +2055/-10 LOC, OPEN since 2026-05-08, MERGEABLE, rebased to v7, and has 3 community thumbs-up. It already implements:

- All 7 HCL block types (resource, data, module, variable, output, locals, **provider**)
- Cross-file module-input edge resolution (module call → child variable)
- Secret scrubbing (AWS keys, GitHub PATs, RSA keys, generic token/secret/password patterns)
- 14 structured diagnostic codes with severity levels and per-file caps
- Resource limits (5MB file, 200k AST nodes)
- Confidence scoring (EXTRACTED/1.0 vs INFERRED/0.8) with explicit `resolution_status` and `unresolved_target_key`
- `.tfvars` support

PR [#841 by Carter Wooten](https://github.com/safishamsi/graphify/pull/841) was a smaller competing PR (326 LOC). **Carter closed it himself on 2026-05-13**, saying *"Suspect it's much more robust given this was a one shot from an LLM. Will close this PR in preference to that PR."*

Your branch is closer in size and scope to #841 than to #416. The same conversation will play out.

**Recommended action:** Do not open the extractor PR. Reposition `cross-file-refs` as a **follow-up PR after #416 merges** — if and only if your cross-file resolution covers ground #416 misses. (See the "Differentiator analysis" section below.)

Keep `worked-terraform-infra` as a personal blog asset / future `examples/` PR.

---

## Branch-by-branch review

### `extract-terraform` (+316/−2, 5 files)

**What it does:** Adds `extract_terraform(path)` to `extract.py`. Walks tree-sitter-hcl AST, emits `contains` edges (file → block → attribute) and within-file `references` edges. Wires `.tf` into `_DISPATCH`.

**Strengths:**
- Clean placement next to other extractors in `extract.py`.
- Uses the established `add_node` / `add_edge` closure pattern (matches bash/PowerShell extractors).
- Tree-sitter-based, not regex — robust to HCL formatting quirks.
- 9 single-file tests cover all block types.

**Issues:**

1. **Schema mismatch with v8 — missing `confidence_score`.**
   The edge dict emits `"confidence": "EXTRACTED"` but no `confidence_score: 1.0`. Other extractors on v8 emit both (and the wider codebase consumes `confidence_score`). PR #416 emits both. This will show up as inconsistent edge metadata in `graph.json` and may break downstream consumers (cluster/query/wiki).
   - **Fix:** Add `"confidence_score": 1.0` to all edges emitted by `add_edge`.

2. **Bug: `_walk_expr` does not recurse into nested expressions.**
   `_walk_expr` checks `if node.type == "variable_expr"` and otherwise does nothing. Nested expressions like `coalesce(var.x, var.y)` or `[for k, v in var.map : k]` are silently dropped. References inside complex expressions never become edges.
   - **Fixed in `cross-file-refs`** (added `else: for child in node.children: _walk_expr(child, attr_node)`). But this means **the `extract-terraform` branch as it stands is buggy on real Terraform.** Either rebase the fix down or don't ship this branch separately.

3. **Bug: resource ref resolver returns false positives.**
   The fallback loop `for i in range(1, len(parts))` returns `_make_id(stem, "resource", type_name, name_part)` for any 2-part attribute access. With `seen_ids` filter in `extract-terraform`, this only fires for refs to in-file resources — OK. But `cross-file-refs` removed the filter (see below) which makes this a serious source of phantom edges.

4. **Attribute-as-node design is unusually fine-grained.**
   Every attribute (e.g., `ami = "ami-12345"`) becomes its own node. For a small fixture this is fine; for production Terraform (your worked example reports 608 nodes for 54 files) this is ~11 nodes/file, which is acceptable but trends high. Compare to PR #416, which scopes nodes to block-level (resource/data/module/variable/output/locals/provider) and uses edges for relationships — leaner graphs, less noise in cluster detection.
   - **Decision call:** opinionated, not wrong. But Safi has shown a preference for "graph density that matches architectural intent" — see his comments on issue #951 and discussion #345. Attribute-level may be noise.

5. **No `.tfvars` handling.**
   PR description for your branch says "intentionally excluded." Real Terraform users put real configuration in `.tfvars` files. PR #416 includes them. This will be a code-review pushback.

6. **No diagnostics on parse error.**
   Returns `{"nodes": [], "edges": [], "error": str(e)}` and the caller sees nothing actionable. PR #416 emits structured `hcl_parse_error` / `hcl_partial_parse` diagnostics with severity and source spans.

7. **No resource limits.**
   No file-size cap, no AST node cap. A pathological `.tf` file can OOM the extractor. PR #416 caps at 5MB / 200k AST nodes.

8. **No secret scrubbing.**
   Terraform files routinely contain `default = "<secret>"` for variable defaults. Persisted `source_location` and `context` fields can leak secrets into `graph.json`. PR #416 has `_HCL_SECRET_PATTERNS` for AWS keys, GitHub PATs, RSA keys, and generic credential patterns.

9. **Test gap: no fixtures exercise multi-block-type interaction.**
   Each test checks "did label X appear" — node-level, not edge-level. No test verifies that `output.instance_ip` references `aws_instance.web`. Cross-file resolution is entirely untested in this branch.

### `cross-file-refs` (+149/−14, 1 file)

**What it does:** Two things bundled in one commit:
1. Makes all Terraform block nids stem-independent (`_make_id("resource", "aws_vpc", "main")` instead of `_make_id(stem, "resource", "aws_vpc", "main")`).
2. Adds `_resolve_cross_file_tf_refs()` orchestration pass after the Python/Java resolvers in `extract()`.

Also fixes the `_walk_expr` recursion bug.

**Strengths:**
- The `_walk_expr` recursion fix is correct and necessary.
- Wiring into `extract()` follows the existing Python/Java resolver pattern.
- `raw_tf_refs` carrying unresolved refs is the right pattern — mirrors `raw_calls`.

**Issues:**

1. **Stem-independent nids break Terraform's actual scoping rules.**
   Terraform's resource namespace is the **module**, not the directory or file. Two modules `modules/api/main.tf` and `modules/worker/main.tf` can both legally declare `resource "aws_iam_role" "task"`. Under your scheme, both nodes collide to one `resource_aws_iam_role_task` node — wrong. References from each module silently merge.
   - PR #416 (per its description) resolves cross-file at the module-input edge level. Cleaner.
   - **Fix:** scope nids to the nearest module directory (parent containing `main.tf` or a `modules/<name>` parent), not the file stem or globally.

2. **`_resolve_ref_to_nid` for resources lost its `seen_ids` filter.**
   ```python
   for i in range(1, len(parts)):
       type_name = parts[i - 1]
       name_part = parts[i]
       return _make_id("resource", type_name, name_part)  # always returns first candidate
   ```
   Previous code only returned a candidate if it was in `seen_ids` (a poor-man's filter). New code returns unconditionally. This means **any** two-component attribute access like `data.something.bar` or `local.x.y` or `tags.Name` could now be mis-classified as a resource reference.
   - The cross-file resolver `_resolve_cross_file_tf_refs` filters against `all_tf_nids` which catches some bad cases, but only after the fact and only for things that look like real nids. Spurious matches against module-named-aws resources (`aws_instance.tags`) will still pollute the graph.
   - **Fix:** keep the `seen_ids` check, and add a second cross-file lookup pass against the union of `all_tf_nids` collected before edges are emitted (currently you emit then check, which is backwards).

3. **Unresolved refs are silently dropped.**
   The `else: unresolved_tf_refs.append(...)` branch collects unresolved nids but the function drops them at exit without emitting diagnostics. PR #416 would emit `hcl_unresolved_variable` / `hcl_unresolved_output` diagnostics with severity `info`.

4. **Bundled change diff is hard to review.**
   One commit does (a) stem→global nid scheme change, (b) walk_expr bug fix, (c) cross-file orchestration. Split into three commits: any reviewer will want these separable.

5. **Tests for cross-file behavior are missing.**
   No test in `tests/test_languages.py` exercises the cross-file path. The only signal that it works is the worked example. That's not enough.

### `worked-terraform-infra` (+2,886, 13 files)

**What it does:** Imports your `aws-terraform-multi-env-template` repo under `worked/terraform-infra/`, pre-generates `graph.json` (608 nodes / 733 edges / 8 communities), and adds `README.md`, `GRAPH_REPORT.md`, `review.md`.

**Strengths:**
- Real-world corpus, not a toy. 54 files across 8 modules is a fair stress test.
- Pre-built `graph.json` is the right artifact for a blog post — readers can run queries without running the extractor.
- Joins the existing `worked/` directory pattern (`worked/example/`, `worked/httpx/`, `worked/karpathy-repos/`, `worked/mixed-corpus/` are all already there).

**Issues:**

1. **Not a PR candidate alongside the extractor.**
   2886 LOC of Terraform code dwarfs the extractor diff. Reviewers will get distracted.
   - **Better path:** open as a separate PR *after* the extractor lands upstream (via #416 or your own). Or host on your fork as a blog reference.

2. **`review.md` overstates confidence.**
   Claims:
   - *"100% EXTRACTED confidence — Every edge comes from AST analysis, not inference. No phantom nodes or spurious connections."*
     This is partially true on this corpus but is **structurally not guaranteed** — the resource-ref resolver in `cross-file-refs` will produce phantom edges on other corpora (see issue 2 in `cross-file-refs` review above).
   - *"No missing edges: All attribute references in the source code are captured."*
     Not verified — there's no oracle for "all references in the corpus." The number 168 is what the extractor *found*, not what *exists*.
   - *"production-ready"* — the extractor still has the resource-ref bug and the module-scoping bug. Not production-ready yet.

   Tone down to "On this corpus, the extractor produced 608 nodes / 733 edges with no parse errors and 168 cross-file reference edges resolved."

3. **`GRAPH_REPORT.md` and per-file extraction were not reviewed in this pass.**
   Should be sanity-checked: do the "god nodes" listed (`variable_domain_name`, `resource_aws_vpc_main`) actually correspond to the highest-degree nodes in `graph.json`? Verifiable in <5 minutes.

---

## Differentiator analysis — does your work cover ground PR #416 misses?

This is the deciding question for whether `cross-file-refs` survives as a follow-up.

| Capability | Your branches | PR #416 (per description) |
|---|---|---|
| `resource`, `data`, `module`, `variable`, `output`, `locals` blocks as nodes | ✅ | ✅ |
| `terraform` block | ✅ | ❓ (not mentioned) |
| `provider` block | ❌ | ✅ |
| `.tfvars` | ❌ | ✅ |
| Cross-file module-input edges (module call → child variable) | Partial (general ref pass) | ✅ (specific to module inputs) |
| Cross-file general resource references (e.g., `aws_vpc.main.id` in another file in same module) | ✅ (via stem-independent nids) | ❓ (only "module dependency edges" mentioned — may not cover this) |
| Confidence scoring (EXTRACTED/INFERRED, score 0–1) | Partial (string only, no score) | ✅ |
| Diagnostics with severity + source spans | ❌ | ✅ (14 codes) |
| Per-file diagnostic caps | ❌ | ✅ (200/file) |
| Resource limits (file size, AST nodes) | ❌ | ✅ (5MB / 200k) |
| Secret scrubbing | ❌ | ✅ |
| Module-scope-correct nids (collision-safe across modules) | ❌ | ❓ (description suggests yes, would need to read diff) |
| Attribute-level nodes | ✅ (high granularity) | ❌ (block-level only) |
| Worked example | ✅ (608 nodes / 733 edges) | ❌ |

**Possible differentiators that survive #416:**
- General cross-file reference resolution (not just module-input edges) — IF #416 doesn't already do this. **Read #416's diff before assuming.**
- Attribute-level nodes — opinionated; may or may not be welcome.
- The worked example corpus.

**Action item:** before doing anything else with these branches, run:
```bash
gh pr diff 416 -R safishamsi/graphify | less
```
and check whether `_resolve_cross_file_terraform_refs` or equivalent exists. If yes, your follow-up window is small. If no, `cross-file-refs` (after fixing the bugs noted above) is a clean follow-up PR.

---

## Recommended action plan

1. **Do not open the `extract-terraform` PR.** It will be closed in favor of #416 within days of being seen.
2. **Read PR #416's diff in full.** Identify the exact gap (most likely: general cross-file refs and/or attribute granularity).
3. **Watch #416 merge.** Once it does, rebase onto upstream and prepare a follow-up PR titled something like `feat(hcl): cross-file reference resolution for inter-file resource/variable/local references` — narrowly scoped, with the three bugs in `cross-file-refs` fixed first.
4. **Reframe `worked-terraform-infra`** as either (a) a blog asset on your fork, or (b) a follow-on `worked/` PR after #416 lands. The current `review.md` needs the overclaiming dialed down.
5. **Move on to MCP-ingest** (in progress in this session) as the application-focused contribution. That space is uncontested — verified by `gh pr list --search` returning zero MCP-ingest PRs.

The Terraform work was not wasted: it demonstrates you can navigate this codebase, write tree-sitter extractors, and reason about cross-file resolution. That experience makes the MCP module faster to ship. But landing it as a PR against #416 is a fight that's already over.

---

*Files reviewed in detail: `graphify/extract.py` (changed regions), `graphify/detect.py`, `tests/fixtures/sample.tf`, `tests/test_languages.py`, `worked/terraform-infra/README.md`, `worked/terraform-infra/review.md`.*
*Files not opened in this pass: `worked/terraform-infra/GRAPH_REPORT.md`, individual `.tf` files under `worked/terraform-infra/raw/`, `worked/terraform-infra/graph.json`.*

---

## Resolution (2026-05-26)

### Verified: #416's cross-file gap is real

Pulled the full diff of PR #416 and grepped `resolve_hcl_cross_file`:

> The function only handles `ref["kind"] == "module_input"` (module call argument → child variable) and `ref["kind"] == "module_output"` (caller block → child output). **It does not build a resource index or resolve general `resource.x.y` references across files in the same module directory.**

So the gap you predicted is genuine. A `compute.tf` referencing `aws_vpc.main.id` from `vpc.tf` in the same module gets NO `references` edge under #416. That IS a legitimate follow-up window.

### Decision: park `cross-file-refs` — do not fix the 3 bugs

Despite the gap being real, the current `cross-file-refs` branch is **on the wrong foundation** for shipping a follow-up against #416:

- #416 uses **per-file nids** (`hcl_file:<path>::<kind>:<identity>`).
- `cross-file-refs` uses **stem-independent globals** (`resource_aws_vpc_main`).

Fixing the three named bugs (resource-ref `seen_ids` filter, stem-independent collision, schema `confidence_score`) doesn't reconcile these two designs — `cross-file-refs` would still be incompatible with #416's data model after the fixes.

The right follow-up, once #416 merges, is a **rewrite** that:

1. Adopts #416's nid scheme as-is.
2. Adds a `resource_index: dict[dir, dict[(type, name), nid]]` mirroring how #416 builds `var_index` and `out_index`.
3. Resolves deferred resource refs against that index, emitting `references` edges with the same `hcl_make_edge` / `hcl_deferred_refs` / diagnostic plumbing #416 already uses.

That PR is small (~150-200 LOC), uses zero new abstractions, and is essentially a one-function extension to #416. It will land easily IF #416 lands.

So:

- **`extract-terraform`**: dead.
- **`cross-file-refs`**: dead as-is. Do not push more commits to it. Wait for #416 to merge, then write the follow-up fresh against #416's primitives.
- **`worked-terraform-infra`**: kept on fork as blog/demo asset. `review.md` toned down (commit `7de21af`).

### Decision: ship MCP as the primary contribution

PR opened against upstream as **[safishamsi/graphify#1034](https://github.com/safishamsi/graphify/pull/1034)** on the same day. State: OPEN, MERGEABLE, +755 LOC, 29 tests.

This is the application-grade contribution. The Terraform work was a costly but useful exercise in learning the codebase; it should not be the public deliverable.

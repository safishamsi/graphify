# Review: rsl-siege-manager

**Corpus:** [`glitchwerks/rsl-siege-manager`](https://github.com/glitchwerks/rsl-siege-manager) @ `6085fd66`
**Date:** 2026-05-15
**Run:** tests included, no `.graphifyignore`
**Counts:** 1886 nodes · 3876 edges · 141 communities · 90% EXTRACTED / 10% INFERRED (avg INFERRED confidence 0.62)
**Cost:** $0 (tree-sitter only; this corpus's natural file mix surfaced no non-code files in meaningful quantity)
**Setup:** ~10 minutes of CLI time end-to-end

This review evaluates the **headline outputs** in `GRAPH_REPORT.md` — god nodes, surprising connections, communities, isolated nodes, suggested questions — against a single criterion: do they reflect things a developer familiar with this codebase would themselves nominate as core, surprising, or worth investigating? Each finding quotes the report directly so it is verifiable against the committed artifacts.

---

## Finding 1 — Test fixtures dominate "core abstractions" when tests are included

Top god nodes, verbatim from `GRAPH_REPORT.md` (lines 141–150):

```
1. `_make_siege()` - 124 edges
2. `_make_member()` - 92 edges
3. `_make_position()` - 85 edges
4. `SiegeMember` - 78 edges
5. `_make_building()` - 64 edges
6. `_make_group()` - 60 edges
7. `BoardPage()` - 55 edges
8. `makeSiegeMember()` - 55 edges
9. `PostsPage()` - 37 edges
10. `_session_with_siege_and_configs()` - 35 edges
```

Six of the top ten — positions 1, 2, 3, 5, 6, and 8 — are test factory functions (`_make_siege`, `_make_member`, `_make_position`, `_make_building`, `_make_group`, `makeSiegeMember`). Position 10 is a test session fixture. These are the highest-connectivity nodes in the graph, and they are infrastructure for verifying the codebase, not the codebase itself.

The god-node list is labeled "your core abstractions" in the report. On this corpus, no developer would nominate `_make_siege()` as a core abstraction of a siege-assignment web app. Degree centrality on a well-tested codebase will tend to surface test factories: by design, factories create the primary domain objects that every test then exercises, so they accumulate edges from every part of the suite. The pattern is structural — the better the test coverage, the more saturated the factory's degree count.

For users running graphify on a codebase with substantial test coverage, the documented mitigation (a `.graphifyignore` excluding `tests/`, `__tests__/`, etc.) is effective at removing this class of false-positive. See Finding 2 for what the same corpus surfaces without tests.

## Finding 2 — Without tests, god nodes mix domain types with entry points and utilities

For comparison, an earlier run of the same corpus with `.graphifyignore` excluding `backend/tests/` and `frontend/src/**/__tests__/` produced this god-node list:

```
1. `SiegeMember` - 55 edges
2. `BoardPage()` - 53 edges
3. `Post Suggestions Modal Handoff` - 40 edges
4. `postsTab` - 29 edges
5. `cn()` - 29 edges
6. `PostsPage()` - 28 edges
7. `BuildingType` - 27 edges
8. `MembersPage()` - 27 edges
9. `MemberRole` - 25 edges
10. `Self-Host on Azure Wiki Page` - 23 edges
```

(That run's artifacts are not committed here — only the tests-included artifacts are kept — but the list is reproducible by re-running with the same `.graphifyignore`.)

Three of ten — `SiegeMember`, `BuildingType`, `MemberRole` (positions 1, 7, 9) — are legitimate domain models a developer would identify.

The other seven illustrate a second pattern worth knowing about:

- **React top-level page components** (`BoardPage`, `PostsPage`, `MembersPage` at 2, 6, 8) — these import many things because they are entry points, not because they encode domain logic.
- **Class-merge utilities** — `cn()` (position 5) is a one-line Tailwind class-merging utility (`src/lib/utils.ts`). It scores 29 edges because every component that conditionally combines classes imports it. The connection count reflects a structural pattern (the React+Tailwind idiom), not semantic importance.
- **Document/wiki entities** — `Post Suggestions Modal Handoff` (position 3) is a planning document under `docs/design-refs/`; `Self-Host on Azure Wiki Page` (position 10) is a wiki article. Both are extracted as nodes alongside code entities and sort by edge count the same way.

This is informative for users tuning expectations: degree centrality on a React frontend with a shared `cn()` utility will surface that utility regardless of how aggressive the ignore filter is, because the connections are real even though the semantic importance is low.

## Finding 3 — Surprising connections cross language boundaries

Both runs surface INFERRED edges between Python backend types and TypeScript frontend types under "Surprising Connections (you probably didn't know these)." Examples:

```
- `AuthError` --uses--> `Member`  [INFERRED]
  backend/app/api/auth.py → frontend/src/api/types.ts
```

```
- `TestStartupValidation` --uses--> `MemberRole`  [INFERRED]
  backend/tests/test_auth.py → frontend/src/api/types.ts
```

A Python class does not "use" a TypeScript type at runtime. These are name-based similarity matches between identically-named constructs in two languages, surfaced as semantic relationships. The confidence values are flagged as INFERRED (avg 0.62 on this run), but the section header presents them as insights worth investigating.

The one cross-language INFERRED edge in this run that maps to a real design contract is:

```
- `PostPriorityResponse` --uses--> `PostPriorityConfig`  [INFERRED]
  backend/app/api/post_priority_config.py → frontend/src/api/posts.ts
```

The backend Pydantic schema and the frontend TypeScript type do mirror each other intentionally — this is the API contract. That relationship is real, but a developer who wrote either side already knows about it; INFERRED detection here recovers a fact rather than discovering one.

For corpora that mix Python and TypeScript with overlapping type names (common in monorepos with shared domain vocabulary), users should expect a high false-positive rate in this section and read it with the INFERRED confidence in mind.

## Finding 4 — Community cohesion is uniformly low on this corpus

Most of rsl-siege-manager's 141 communities (tests-included run) score between 0.05 and 0.17 on cohesion. The report itself flags 0.05 as "weakly interconnected" in the Suggested Questions section:

> "Should `Community 0` be split into smaller, more focused modules? — Cohesion score 0.05 - nodes in this community are weakly interconnected."

Community 0 has 112 nodes on this corpus.

rsl-siege-manager has a clean three-service architecture (backend / frontend / bot). The community-detection pass does not recover that structure as three large cohesive communities; it produces many small communities with low internal cohesion. Possible interpretations: the underlying graph has many INFERRED cross-language edges diluting the cluster signal, the chosen algorithm parameters favor over-segmentation on graphs of this density, or this corpus genuinely lacks tight intra-cluster topology that community detection can exploit.

A neutral framing for users: community cohesion is informative on this corpus mainly as a signal that the graph topology does not match the obvious three-tier mental model — which itself may be useful (it surfaces that the cross-language edges are doing the work). The "split this community" prompts the report generates from low cohesion scores are less actionable as direct architectural advice on this corpus.

## Finding 5 — Alembic migration docstrings surface as isolated nodes

The tests-included run reports 752 isolated nodes; the without-tests run reports 259. The leading examples are identical in both:

```
`initial schema  Revision ID: 0001 Revises: Create Date: 2026-03-16`,
`add autofill and attack day preview columns to siege  Revision ID: 0002 Revises:`,
`make siege date nullable  Revision ID: 0003 Revises: 0002 Create Date: 2026-03-1`,
`Add post_priority_config table`, ...
```

These are Alembic migration revision docstrings parsed as standalone graph nodes. There are 17 migration files in this corpus. The isolated-node count growing from 259 to 752 when tests are added is dominated by test docstrings parsed the same way.

The report labels these as "possible documentation gaps or missing edges." For users with corpora that contain Alembic migrations, pytest docstrings, or other docstring-heavy auto-generated files, this label can be misleading — these are change annotations or test descriptions, not architectural entities with missing connections.

A `.graphifyignore` rule for `**/alembic/versions/*.py` reduces the isolated-node count materially on this corpus; users with similar setups may want a default recipe.

## Finding 6 — Suggested questions skew toward graph-property prompts

The Suggested Questions section consists primarily of two kinds of questions:

1. **Betweenness centrality prompts:** "Why does `_make_siege()` connect Community 12 to Community 0, Community 1, Community 3...?" The answer on this corpus is direct: `_make_siege()` creates the primary domain object, every test that touches a siege uses it, and the test suite spans the codebase — so the fixture is a betweenness bridge by construction.

2. **Inferred-edge audits:** "Are the 17 inferred relationships involving `SiegeMember` (e.g. with `Base` and `TestSeedDemoMembers`) actually correct?" These ask the developer to validate the tool's own low-confidence connections.

A genuinely concrete question in this section — "What is the exact relationship between `bootstrap-images.ps1` and `scripts/bootstrap-images.ps1`?" — is tagged AMBIGUOUS by the report. The answer is concrete (they are the same script referenced by two slightly different paths), but it is a file-naming observation, not an architectural insight.

For users hoping the Suggested Questions section will surface domain-level prompts ("how does authentication flow?", "what enforces the siege-day invariant?"), this corpus's section is dominated by graph-property meta-questions.

---

## What worked well on this corpus

- **Throughput:** 1886 nodes extracted in a few minutes at $0 cost. tree-sitter handles all 29 supported languages locally; LLM calls fire only for non-code files.
- **Genuine domain extractions are present:** `SiegeMember`, `BuildingType`, and `MemberRole` in the god-node list are correct. `PostPriorityResponse --uses--> PostPriorityConfig` is a real API contract that INFERRED detection picked up across the Python/TypeScript boundary.
- **`graph.html` visualization:** clear, navigable, easy to filter and search. Useful for browsing communities even when the labelled cohesion scores are low.

The underlying graph build is solid. The findings above are about how the report layer summarizes that graph into headline metrics — specifically, what those metrics surface on a well-tested cross-language full-stack web app.

---

## Suggested follow-ups

Patterns from this review that may be worth tracking upstream:

1. **Test-fixture suppression** — degree centrality on covered codebases consistently surfaces test factories; documenting the ignore-pattern recipe in a "first run on a codebase with tests" section would shorten the iteration loop for users.
2. **Cross-language INFERRED edges in monorepos** — name-based matches between Python and TypeScript types in mixed-language repos may warrant a higher confidence threshold or a "potential contract" label rather than the current "surprising connection" framing.
3. **Docstring-heavy files (Alembic, pytest)** — defaulting to skip migration `versions/` directories, or detecting and grouping docstring nodes that share a structural pattern, would reduce the isolated-node noise materially.

These are observations, not change requests — users running graphify on similar corpora may find the same patterns useful to know about.

# Graph Report - /home/shetautnetjerheru/graphify/graphify  (2026-04-07)

## Corpus Check
- 25 files · ~60,111 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 306 nodes · 440 edges · 18 communities detected
- Extraction: 66% EXTRACTED · 34% INFERRED · 0% AMBIGUOUS · INFERRED: 150 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `_make_id()` - 23 edges
2. `_read_text()` - 16 edges
3. `_extract_generic()` - 15 edges
4. `detect()` - 10 edges
5. `_cross_file_surprises()` - 8 edges
6. `_fetch_webpage()` - 8 edges
7. `main()` - 7 edges
8. `ingest()` - 7 edges
9. `_is_file_node()` - 6 edges
10. `_cross_community_surprises()` - 6 edges

## Surprising Connections (you probably didn't know these)
- None detected - all connections are within the same source files.

## Communities

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (74): _csharp_extra_walk(), extract(), extract_c(), extract_cpp(), extract_csharp(), extract_elixir(), _extract_generic(), extract_go() (+66 more)

### Community 1 - "Community 1"
Cohesion: 0.11
Nodes (30): classify_file(), convert_office_file(), count_words(), detect(), detect_incremental(), docx_to_markdown(), extract_pdf_text(), FileType (+22 more)

### Community 2 - "Community 2"
Cohesion: 0.13
Nodes (24): _cross_community_surprises(), _cross_file_surprises(), _file_category(), god_nodes(), graph_diff(), _is_concept_node(), _is_file_node(), _node_community_map() (+16 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (20): attach_hyperedges(), _cypher_escape(), _html_script(), _html_styles(), _hyperedge_script(), push_to_neo4j(), Store hyperedges in the graph's metadata dict., Escape a string for safe embedding in a Cypher single-quoted literal. (+12 more)

### Community 4 - "Community 4"
Cohesion: 0.16
Nodes (21): _detect_url_type(), _download_binary(), _fetch_arxiv(), _fetch_html(), _fetch_tweet(), _fetch_webpage(), _html_to_markdown(), ingest() (+13 more)

### Community 5 - "Community 5"
Cohesion: 0.16
Nodes (17): _agents_install(), _agents_uninstall(), _check_skill_version(), claude_install(), claude_uninstall(), install(), _install_claude_hook(), main() (+9 more)

### Community 6 - "Community 6"
Cohesion: 0.18
Nodes (16): cache_dir(), cached_files(), check_semantic_cache(), clear_cache(), file_hash(), load_cached(), Save semantic extraction results to cache, keyed by source_file.      Groups nod, SHA256 of file contents + resolved path. Prevents cache collisions on identical (+8 more)

### Community 7 - "Community 7"
Cohesion: 0.17
Nodes (13): _build_opener(), _NoFileRedirectHandler, Fetch *url* and return decoded text (UTF-8, replacing bad bytes).      Wraps saf, Resolve *path* and verify it stays inside *base*.      *base* defaults to the `g, Strip control characters, cap length, then HTML-escape.      Applied to all node, Raise ValueError if *url* is not http or https, or targets a private/internal IP, Redirect handler that re-validates every redirect target.      Prevents open-red, Fetch *url* and return raw bytes.      Protections applied:     - URL scheme val (+5 more)

### Community 8 - "Community 8"
Cohesion: 0.21
Nodes (12): build_graph(), cluster(), cohesion_score(), _partition(), Community detection on NetworkX graphs. Uses Leiden (graspologic) if available,, Ratio of actual intra-community edges to maximum possible., Build a NetworkX graph from graphify node/edge dicts.      Preserves original ed, Run Leiden community detection. Returns {community_id: [node_ids]}.      Communi (+4 more)

### Community 9 - "Community 9"
Cohesion: 0.22
Nodes (12): _git_root(), install(), _install_hook(), Remove graphify section from a git hook using start/end markers., Install graphify post-commit and post-checkout hooks in the nearest git repo., Remove graphify post-commit and post-checkout hooks., Check if graphify hooks are installed., Walk up to find .git directory. (+4 more)

### Community 10 - "Community 10"
Cohesion: 0.18
Nodes (9): _communities_from_graph(), _find_node(), _load_graph(), Start the MCP server. Requires pip install mcp., Reconstruct community dict from community property stored on nodes., Render subgraph as text, cutting at token_budget (approx 3 chars/token)., Return node IDs whose label or ID matches the search term (case-insensitive)., serve() (+1 more)

### Community 11 - "Community 11"
Cohesion: 0.28
Nodes (8): _estimate_tokens(), print_benchmark(), _query_subgraph_tokens(), Token-reduction benchmark - measures how much context graphify saves vs naive fu, Print a human-readable benchmark report., Run BFS from best-matching nodes and return estimated tokens in the subgraph con, Measure token reduction: corpus tokens vs graphify query tokens.      Args:, run_benchmark()

### Community 12 - "Community 12"
Cohesion: 0.28
Nodes (7): build(), build_from_json(), Merge multiple extraction results into one graph.      Extractions are merged in, assert_valid(), Validate an extraction JSON dict against the graphify schema.     Returns a list, Raise ValueError with all errors if extraction is invalid., validate_extraction()

### Community 13 - "Community 13"
Cohesion: 0.36
Nodes (8): _community_article(), _cross_community_links(), _god_node_article(), _index_md(), Return (community_label, edge_count) pairs for cross-community connections, sort, Generate a Wikipedia-style wiki from the graph.      Writes:       - index.md, _safe_filename(), to_wiki()

### Community 14 - "Community 14"
Cohesion: 0.36
Nodes (7): _has_non_code(), _notify_only(), Watch watch_path for new or modified files and auto-update the graph.      For c, Re-run AST extraction + build + cluster + report for code files. No LLM needed., Write a flag file and print a notification (fallback for non-code-only corpora)., _rebuild_code(), watch()

### Community 15 - "Community 15"
Cohesion: 0.67
Nodes (1): graphify - extract · build · cluster · analyze · report.

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (0): 

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **126 isolated node(s):** `graphify - extract · build · cluster · analyze · report.`, `graphify CLI - `graphify install` sets up the Claude Code skill.`, `Warn if the installed skill is from an older graphify version.`, `Write the graphify section to the local AGENTS.md (Codex/OpenCode/OpenClaw).`, `Remove the graphify section from the local AGENTS.md.` (+121 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 16`** (2 nodes): `report.py`, `generate()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (1 nodes): `manifest.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
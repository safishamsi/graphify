from __future__ import annotations
from pathlib import Path
from graphify.installers.core import _PLATFORM_CONFIG

_ANTIGRAVITY_RULES_PATH = Path(".agents") / "rules" / "graphify.md"
_ANTIGRAVITY_WORKFLOW_PATH = Path(".agents") / "workflows" / "graphify.md"

_ANTIGRAVITY_RULES = """\
---
trigger: always_on
description: Consult the graphify knowledge graph at graphify-out/ for codebase and architecture questions.
---

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- For codebase or architecture questions, when `graphify-out/graph.json` exists, first run `graphify query "<question>"` (CLI) or `query_graph` (MCP). Use `graphify path "<A>" "<B>"` / `shortest_path` for relationships and `graphify explain "<concept>"` / `get_node` for focused concepts. These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output.
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
"""

_ANTIGRAVITY_WORKFLOW = """\
---
name: graphify
description: Turn any folder of files into a navigable knowledge graph
---

# Workflow: graphify

Follow the graphify skill installed at ~/.agents/skills/graphify/SKILL.md to run the full pipeline.

If no path argument is given, use `.` (current directory).
"""


def _antigravity_install(project_dir: Path) -> None:
    rules_path = project_dir / _ANTIGRAVITY_RULES_PATH
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(_ANTIGRAVITY_RULES, encoding="utf-8")
    print(f"  rule installed   ->  {rules_path}")

    wf_path = project_dir / _ANTIGRAVITY_WORKFLOW_PATH
    wf_path.parent.mkdir(parents=True, exist_ok=True)
    wf_path.write_text(_ANTIGRAVITY_WORKFLOW, encoding="utf-8")
    print(f"  workflow installed ->  {wf_path}")

def _antigravity_uninstall(project_dir: Path) -> None:
    rules_path = project_dir / _ANTIGRAVITY_RULES_PATH
    if rules_path.exists():
        rules_path.unlink()
        print(f"graphify rule removed from {rules_path.resolve()}")
    else:
        print("No graphify Antigravity rule found - nothing to do")

    wf_path = project_dir / _ANTIGRAVITY_WORKFLOW_PATH
    if wf_path.exists():
        wf_path.unlink()
        print(f"graphify workflow removed from {wf_path.resolve()}")

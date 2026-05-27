from __future__ import annotations
import sys
from pathlib import Path

_DEVIN_RULES = """## graphify
Before answering questions about the architecture or codebase structure, read graphify-out/GRAPH_REPORT.md.
For deep-dives on specific files/functions, use `graphify query "<question>"` to get a focused subgraph.
After writing new code or modifying files, run `graphify update .` to keep the graph current.
"""

def _devin_rules_install(project_dir: Path) -> None:
    rules_dir = project_dir / ".windsurf" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "graphify.md"
    if rules_file.exists() and rules_file.read_text(encoding="utf-8") == _DEVIN_RULES:
        print("  no change")
        return
    rules_file.write_text(_DEVIN_RULES, encoding="utf-8")
    print(f"  devin rules written ->  {rules_file}")
    print("  hint: git add .devin .windsurf")

def _devin_rules_uninstall(project_dir: Path) -> None:
    rules_file = project_dir / ".windsurf" / "rules" / "graphify.md"
    if rules_file.exists():
        rules_file.unlink()
        print("  devin rules removed")

from __future__ import annotations
from pathlib import Path

_KIRO_STEERING = """\
---
inclusion: always
---

graphify: A knowledge graph of this project lives in `graphify-out/`. \
For codebase, architecture, or dependency questions, when `graphify-out/graph.json` exists, \
first run `graphify query "<question>"` (or `graphify path "<A>" "<B>"` / `graphify explain "<concept>"`). \
These return a scoped subgraph, usually much smaller than `GRAPH_REPORT.md` or raw grep output. \
Read `GRAPH_REPORT.md` only for broad architecture review or when those commands do not surface enough context.
"""

_KIRO_STEERING_MARKER = "graphify: A knowledge graph of this project"

def _kiro_install(project_dir: Path) -> None:
    project_dir = project_dir or Path(".")

    # We must go up two directories (installers -> graphify -> root)
    skill_src = Path(__file__).parent.parent.parent / "skills" / "skill-kiro.md"
    skill_dst = project_dir / ".kiro" / "skills" / "graphify" / "SKILL.md"
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    if skill_src.exists():
        skill_dst.write_text(skill_src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        print(f"error: {skill_src} not found in package", file=sys.stderr)
    print(f"  {skill_dst.relative_to(project_dir)}  ->  /graphify skill")

    steering_dir = project_dir / ".kiro" / "steering"
    steering_dir.mkdir(parents=True, exist_ok=True)
    steering_dst = steering_dir / "graphify.md"
    if steering_dst.exists() and steering_dst.read_text(encoding="utf-8") == _KIRO_STEERING:
        print(f"  .kiro/steering/graphify.md  ->  already configured (no change)")
    else:
        action = "updated" if steering_dst.exists() else "written"
        steering_dst.write_text(_KIRO_STEERING, encoding="utf-8")
        print(f"  .kiro/steering/graphify.md  ->  always-on steering {action}")

    print()
    print("Kiro will now read the knowledge graph before every conversation.")
    print("Use /graphify to build or update the graph.")


def _kiro_uninstall(project_dir: Path) -> None:
    project_dir = project_dir or Path(".")
    removed = []

    skill_dst = project_dir / ".kiro" / "skills" / "graphify" / "SKILL.md"
    if skill_dst.exists():
        skill_dst.unlink()
        removed.append(str(skill_dst.relative_to(project_dir)))
        try:
            skill_dst.parent.rmdir()
        except OSError:
            pass

    steering_dst = project_dir / ".kiro" / "steering" / "graphify.md"
    if steering_dst.exists():
        steering_dst.unlink()
        removed.append(str(steering_dst.relative_to(project_dir)))

    print("Removed: " + (", ".join(removed) if removed else "nothing to remove"))

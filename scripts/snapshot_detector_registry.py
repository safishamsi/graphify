from __future__ import annotations

import argparse
from pathlib import Path

from depos.analysis.detectors import list_detectors, load_builtin


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the current detector registry to markdown.")
    parser.add_argument("--output", default="docs/detector-registry.md")
    args = parser.parse_args()

    load_builtin()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Detector Registry",
        "",
        "> Auto-generated snapshot of the built-in detector registry.",
        "",
        "| Name | Version | Universe | Requires reasoner | Severity |",
        "| --- | --- | --- | --- | --- |",
    ]
    for spec in sorted(list_detectors(), key=lambda row: row.name):
        lines.append(
            f"| `{spec.name}` | `{spec.version}` | `{spec.universe.value}` | "
            f"`{str(spec.requires_reasoner).lower()}` | `{spec.severity_default}` |"
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

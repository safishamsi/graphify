from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot prompt schema files into an index JSON file.")
    parser.add_argument("--schema-dir", default="depos/ingest/prompt_schemas")
    parser.add_argument("--output", default="depos/ingest/prompt_schemas/index.json")
    args = parser.parse_args()

    schema_dir = Path(args.schema_dir)
    index: dict[str, dict[str, str]] = {}
    for path in sorted(schema_dir.glob("*.schema.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid JSON schema: {path}: {exc}") from exc
        index[path.stem.replace(".schema", "")] = {
            "path": str(path.as_posix()),
            "title": str(payload.get("title") or path.stem),
            "schema": str(payload.get("$schema") or ""),
        }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"schemas": len(index), "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

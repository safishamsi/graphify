from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Iterable


def _rows(paths: Iterable[Path]) -> list[dict]:
    out: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as fp:  # type: ignore[arg-type]
            if path.suffix in {".json", ".gz"}:
                try:
                    data = json.load(fp)
                except json.JSONDecodeError:
                    data = []
                if isinstance(data, list):
                    out.extend(row for row in data if isinstance(row, dict))
                continue
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    out.sort(key=lambda row: (str(row.get("ecosystem") or ""), str(row.get("name") or ""), str(row.get("id") or "")))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic local advisory snapshot.")
    parser.add_argument("--input", action="append", default=[], help="Local JSON, JSONL, or gzipped JSON advisory source.")
    parser.add_argument("--output-dir", default="data/advisories")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _rows([Path(value) for value in args.input])
    snapshot = output_dir / "advisories.jsonl"
    with snapshot.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, sort_keys=True) + "\n")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest() if snapshot.exists() else ""
    (output_dir / "advisories.lock").write_text(json.dumps({"sha256": digest, "count": len(rows)}, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(snapshot), "rows": len(rows), "sha256": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

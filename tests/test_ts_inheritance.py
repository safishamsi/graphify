"""Regression tests for issue #1095: TypeScript inheritance capture.

Two gaps on v0.8.26:
  1. `interface A extends B` produced no `inherits` edge (walker only looked at
     `class_heritage`, but interface heritage is an `extends_type_clause` node).
  2. `class X extends Y` where Y is same-file produced no edge (the use-fact
     resolver only consulted the import table, never same-file symbol nodes).

Files live under a `src/` subdir so the one-parent-level node-ID stem is stable
(a root-level file would derive its stem from the tmp dir name).
"""
from pathlib import Path

from graphify.extract import _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _has_inherits(result: dict, src_file: str, src_sym: str,
                  tgt_file: str, tgt_sym: str, relation: str = "inherits") -> bool:
    src = _make_id(_file_stem(Path(src_file)), src_sym)
    tgt = _make_id(_file_stem(Path(tgt_file)), tgt_sym)
    return any(
        (e["source"], e["target"], e["relation"]) == (src, tgt, relation)
        for e in result["edges"]
    )


def test_interface_extends_same_file(tmp_path):
    f = _write(tmp_path / "src" / "a.ts",
               "export interface Base { x: number; }\n"
               "export interface Derived extends Base { y: number; }\n")
    result = extract([f], cache_root=tmp_path)
    assert _has_inherits(result, "src/a.ts", "Derived", "src/a.ts", "Base")


def test_interface_extends_multiple_same_file(tmp_path):
    f = _write(tmp_path / "src" / "a.ts",
               "interface A { a: number; }\n"
               "interface B { b: number; }\n"
               "interface M extends A, B { m: number; }\n")
    result = extract([f], cache_root=tmp_path)
    assert _has_inherits(result, "src/a.ts", "M", "src/a.ts", "A")
    assert _has_inherits(result, "src/a.ts", "M", "src/a.ts", "B")


def test_class_extends_same_file(tmp_path):
    f = _write(tmp_path / "src" / "a.ts",
               "class Animal {}\n"
               "class Dog extends Animal {}\n")
    result = extract([f], cache_root=tmp_path)
    assert _has_inherits(result, "src/a.ts", "Dog", "src/a.ts", "Animal")


def test_interface_extends_generic_base_same_file(tmp_path):
    f = _write(tmp_path / "src" / "a.ts",
               "interface Base<T> { x: T; }\n"
               "interface G extends Base<number> { y: number; }\n")
    result = extract([f], cache_root=tmp_path)
    assert _has_inherits(result, "src/a.ts", "G", "src/a.ts", "Base")


def test_interface_extends_imported(tmp_path):
    _write(tmp_path / "src" / "b.ts", "export interface Imported { z: number; }\n")
    f = _write(tmp_path / "src" / "a.ts",
               "import { Imported } from './b';\n"
               "export interface D extends Imported { d: number; }\n")
    result = extract([tmp_path / "src" / "a.ts", tmp_path / "src" / "b.ts"], cache_root=tmp_path)
    assert _has_inherits(result, "src/a.ts", "D", "src/b.ts", "Imported")


def test_imported_class_extends_still_works(tmp_path):
    """Regression guard: the originally-working imported-class case must stay."""
    _write(tmp_path / "src" / "b.ts", "export class Imported {}\n")
    f = _write(tmp_path / "src" / "a.ts",
               "import { Imported } from './b';\n"
               "class Cat extends Imported {}\n")
    result = extract([tmp_path / "src" / "a.ts", tmp_path / "src" / "b.ts"], cache_root=tmp_path)
    assert _has_inherits(result, "src/a.ts", "Cat", "src/b.ts", "Imported")


def test_class_implements_same_file_interface(tmp_path):
    f = _write(tmp_path / "src" / "a.ts",
               "interface Walker { walk(): void; }\n"
               "class Person implements Walker { walk() {} }\n")
    result = extract([f], cache_root=tmp_path)
    assert _has_inherits(result, "src/a.ts", "Person", "src/a.ts", "Walker", relation="implements")

from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _extract_for(paths: list[Path], root: Path):
    return extract(paths, cache_root=root)


def _has_edge(result: dict, source: str, target: str, relation: str = "imports_from") -> bool:
    expected = (_make_id(source), _make_id(target), relation)
    actual = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }
    return expected in actual


def _has_symbol_edge(
    result: dict,
    source: str,
    target_file: str,
    symbol: str,
    relation: str = "imports",
) -> bool:
    expected = (_make_id(source), _make_id(_file_stem(Path(target_file)), symbol), relation)
    actual = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }
    return expected in actual


def _has_symbol_to_symbol_edge(
    result: dict,
    source_file: str,
    source_symbol: str,
    target_file: str,
    target_symbol: str,
    relation: str,
) -> bool:
    expected = (
        _make_id(_file_stem(Path(source_file)), source_symbol),
        _make_id(_file_stem(Path(target_file)), target_symbol),
        relation,
    )
    actual = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }
    return expected in actual


def _has_no_symbol_to_symbol_edge(
    result: dict,
    source_file: str,
    source_symbol: str,
    target_file: str,
    target_symbol: str,
    relation: str,
) -> bool:
    return not _has_symbol_to_symbol_edge(
        result,
        source_file,
        source_symbol,
        target_file,
        target_symbol,
        relation,
    )


def test_ts_bare_relative_import_resolves_existing_ts_file(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export const foo = 1\n")
    importer = _write(
        tmp_path / "src/lib/page.ts",
        "import { foo } from './foo'\nconsole.log(foo)\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/lib/page.ts", "src/lib/foo.ts")


def test_ts_directory_import_resolves_index_ts(tmp_path: Path):
    target = _write(tmp_path / "src/lib/server/queue/index.ts", "export const queue = 1\n")
    importer = _write(
        tmp_path / "src/lib/page.ts",
        "import { queue } from './server/queue'\nconsole.log(queue)\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/lib/page.ts", "src/lib/server/queue/index.ts")


def test_ts_named_reexport_alias_from_index_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class InternalFoo { id = '' }\n")
    barrel = _write(
        tmp_path / "src/lib/index.ts",
        "export { InternalFoo as Foo } from './foo'\n",
    )
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(
        result,
        "src/routes/page.ts",
        "src/lib/foo.ts",
        "InternalFoo",
    )


def test_ts_export_star_from_index_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export * from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_import_alias_then_reexport_alias_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    barrel = _write(
        tmp_path / "src/lib/index.ts",
        "import type { Foo as LocalFoo } from './foo'\nexport type { LocalFoo as PublicFoo }\n",
    )
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { PublicFoo } from '../lib/index'\nexport type X = PublicFoo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_import_from_index_then_exported_type_alias_resolves_to_origin_symbol(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_reexported_interface_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export interface Foo { id: string }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export type { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_reexported_type_alias_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export type Foo = { id: string }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export type { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Foo } from '../lib/index'\nexport type X = Foo\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_reexported_abstract_class_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export abstract class Foo { abstract run(): void }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo } from '../lib/index'\nclass Impl extends Foo { run() {} }\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_const_alias_reexport_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export class Foo { id = '' }\n")
    barrel = _write(
        tmp_path / "src/lib/index.ts",
        "import { Foo } from './foo'\nexport const PublicFoo = Foo\n",
    )
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { PublicFoo } from '../lib/index'\nnew PublicFoo()\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "Foo")


def test_ts_local_const_alias_then_named_reexport_resolves_imported_symbol_to_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export function makeFoo() { return {} }\n")
    barrel = _write(
        tmp_path / "src/lib/index.ts",
        "import { makeFoo } from './foo'\nconst PublicFactory = makeFoo\nexport { PublicFactory }\n",
    )
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { PublicFactory } from '../lib/index'\nPublicFactory()\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_edge(result, "src/lib/index.ts", "src/lib/foo.ts", "re_exports")
    assert _has_symbol_edge(result, "src/routes/page.ts", "src/lib/foo.ts", "makeFoo")


def test_ts_arrow_function_call_through_barrel_targets_origin_symbol(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export function Foo() { return 1 }\n")
    unrelated = _write(tmp_path / "src/other/foo.ts", "export function Foo() { return 2 }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo } from '../lib/index'\nconst X = () => Foo()\n",
    )

    result = _extract_for([target, unrelated, barrel, consumer], tmp_path)

    assert _has_symbol_to_symbol_edge(
        result,
        "src/routes/page.ts",
        "X",
        "src/lib/foo.ts",
        "Foo",
        "calls",
    )


def test_ts_import_alias_does_not_affect_same_named_local_symbol_when_unused(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export function Foo() { return 1 }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo as Bar } from '../lib/index'\nconst Foo = () => {}\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_no_symbol_to_symbol_edge(
        result,
        "src/routes/page.ts",
        "Foo",
        "src/lib/foo.ts",
        "Foo",
        "calls",
    )


def test_ts_import_alias_call_from_same_named_local_symbol_targets_origin(tmp_path: Path):
    target = _write(tmp_path / "src/lib/foo.ts", "export function Foo() { return 1 }\n")
    barrel = _write(tmp_path / "src/lib/index.ts", "export { Foo } from './foo'\n")
    consumer = _write(
        tmp_path / "src/routes/page.ts",
        "import { Foo as Bar } from '../lib/index'\nconst Foo = () => Bar()\n",
    )

    result = _extract_for([target, barrel, consumer], tmp_path)

    assert _has_symbol_to_symbol_edge(
        result,
        "src/routes/page.ts",
        "Foo",
        "src/lib/foo.ts",
        "Foo",
        "calls",
    )


def test_svelte_rune_import_resolves_svelte_ts_file(tmp_path: Path):
    target = _write(tmp_path / "src/lib/hooks/is-mobile.svelte.ts", "export const isMobile = true\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import { isMobile } from '../lib/hooks/is-mobile.svelte'\nconsole.log(isMobile)\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/lib/hooks/is-mobile.svelte.ts")


def test_tsconfig_alias_import_resolves_existing_ts_file(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"$lib/*": ["src/lib/*"]}}}),
    )
    target = _write(tmp_path / "src/lib/types/type-helpers.ts", "export type Helper = string\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Helper } from '$lib/types/type-helpers'\nconst value: Helper = 'x'\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/lib/types/type-helpers.ts")


def test_tsconfig_array_extends_alias_resolves_existing_ts_file(tmp_path: Path):
    # TypeScript 5.0 allows `extends` as an array; later entries override
    # earlier ones. The `paths` alias is inherited from the second parent.
    # Regression: an array `extends` previously raised
    # `AttributeError: 'list' object has no attribute 'startswith'`, which
    # _safe_extract turned into a skip of every file using the alias.
    _write(tmp_path / "tsconfig.base.json", json.dumps({"compilerOptions": {"strict": True}}))
    _write(
        tmp_path / "tsconfig.paths.json",
        json.dumps({"compilerOptions": {"baseUrl": ".", "paths": {"$lib/*": ["src/lib/*"]}}}),
    )
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"extends": ["./tsconfig.base.json", "./tsconfig.paths.json"]}),
    )
    target = _write(tmp_path / "src/lib/types/type-helpers.ts", "export type Helper = string\n")
    importer = _write(
        tmp_path / "src/routes/page.ts",
        "import type { Helper } from '$lib/types/type-helpers'\nconst value: Helper = 'x'\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "src/routes/page.ts", "src/lib/types/type-helpers.ts")


def test_pnpm_workspace_package_import_resolves_package_entry(tmp_path: Path):
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    _write(
        tmp_path / "packages/types/package.json",
        json.dumps({"name": "@workspace/types", "exports": "./src/index.ts"}),
    )
    target = _write(
        tmp_path / "packages/types/src/index.ts",
        "export interface SomeDto { id: string }\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/page.ts",
        "import type { SomeDto } from '@workspace/types'\nconst dto: SomeDto = { id: '1' }\n",
    )

    result = _extract_for([target, importer], tmp_path)

    assert _has_edge(result, "apps/web/src/page.ts", "packages/types/src/index.ts")


def test_js_import_resolution_ignores_stale_importer_cache_when_target_appears(tmp_path: Path):
    importer = _write(
        tmp_path / "src/lib/page.ts",
        "import { foo } from './foo'\nconsole.log(foo)\n",
    )

    first = _extract_for([importer], tmp_path)
    assert not _has_edge(first, "src/lib/page.ts", "src/lib/foo.ts")

    target = _write(tmp_path / "src/lib/foo.ts", "export const foo = 1\n")
    second = _extract_for([target, importer], tmp_path)

    assert _has_edge(second, "src/lib/page.ts", "src/lib/foo.ts")


def test_workspace_package_cache_refreshes_between_extract_calls(tmp_path: Path):
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'apps/*'\n  - 'packages/*'\n",
    )
    importer = _write(
        tmp_path / "apps/web/src/page.ts",
        "import type { SomeDto } from '@workspace/types'\nconst dto: SomeDto = { id: '1' }\n",
    )

    first = _extract_for([importer], tmp_path)
    assert not _has_edge(first, "apps/web/src/page.ts", "packages/types/src/index.ts")

    _write(
        tmp_path / "packages/types/package.json",
        json.dumps({"name": "@workspace/types", "exports": "./src/index.ts"}),
    )
    target = _write(
        tmp_path / "packages/types/src/index.ts",
        "export interface SomeDto { id: string }\n",
    )

    second = _extract_for([target, importer], tmp_path)

    assert _has_edge(second, "apps/web/src/page.ts", "packages/types/src/index.ts")


def test_ts_type_relationships_and_contexts(tmp_path: Path):
    base = _write(
        tmp_path / "src/lib/base.ts",
        "export interface IProcessor<T> { run(input: T): Result<T> }\n"
        "export abstract class BaseProcessor {}\n"
        "export type Result<T> = { value: T }\n"
        "export class Payload {}\n",
    )
    impl = _write(
        tmp_path / "src/lib/impl.ts",
        "import type { IProcessor, BaseProcessor, Result, Payload } from './base'\n"
        "export abstract class DataProcessor extends BaseProcessor implements IProcessor<Payload> {\n"
        "  current!: Result<Payload>\n"
        "  run(input: Payload): Result<Payload> { return this.current }\n"
        "}\n",
    )

    result = _extract_for([base, impl], tmp_path)
    labels = {node["id"]: node["label"] for node in result["nodes"]}

    def _norm(label: str) -> str:
        return label.strip("()").lstrip(".")

    reference_contexts = {
        (
            _norm(labels.get(edge["source"], edge["source"])),
            _norm(labels.get(edge["target"], edge["target"])),
            edge.get("context"),
        )
        for edge in result["edges"]
        if edge.get("relation") == "references"
    }

    assert _has_symbol_to_symbol_edge(result, "src/lib/impl.ts", "DataProcessor", "src/lib/base.ts", "BaseProcessor", "inherits")
    assert _has_symbol_to_symbol_edge(result, "src/lib/impl.ts", "DataProcessor", "src/lib/base.ts", "IProcessor", "implements")
    assert ("run", "Payload", "parameter_type") in reference_contexts
    assert ("run", "Result", "return_type") in reference_contexts
    assert ("run", "Payload", "generic_arg") in reference_contexts

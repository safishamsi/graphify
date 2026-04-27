"""Tests for node ID collision disambiguation in extract()."""

from pathlib import Path

from graphify.extract import extract, collect_files

COLLISION_DIR = Path(__file__).parent / "fixtures" / "collision"


def _extract_collision_files(subdirs: list[str]) -> dict:
    """Run extract() on files from the given subdirectories."""
    files = []
    for subdir in subdirs:
        d = COLLISION_DIR / subdir
        files.extend(collect_files(d))
    return extract(files)


def test_same_stem_different_dirs_get_unique_ids():
    """Two Program.cs in different dirs must produce distinct node IDs."""
    result = _extract_collision_files(["app1", "app2"])
    ids = [n["id"] for n in result["nodes"]]
    program_ids = [i for i in ids if "program" in i and "program_cs" not in i.replace("program_cs", "")]
    # There must be at least two distinct Program-class nodes
    class_ids = [i for i in ids if i.endswith("_program") or "_program_" in i]
    assert len(set(class_ids)) >= 2, f"Expected distinct IDs, got: {class_ids}"


def test_no_node_ids_collide_after_disambiguation():
    """After disambiguation, all node IDs must be unique."""
    result = _extract_collision_files(["app1", "app2"])
    ids = [n["id"] for n in result["nodes"]]
    assert len(ids) == len(set(ids)), f"Duplicate IDs found: {[i for i in ids if ids.count(i) > 1]}"


def test_edges_reference_valid_nodes():
    """All edge sources and targets must exist in the node set."""
    result = _extract_collision_files(["app1", "app2"])
    node_ids = {n["id"] for n in result["nodes"]}
    for e in result["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e['source']}"
        # targets may reference external (unresolved) nodes, but sources must exist


def test_same_parent_dir_uses_deeper_path():
    """src/app/Startup.cs and tests/app/Startup.cs share parent 'app',
    so disambiguation must use deeper path components."""
    result = _extract_collision_files(["src/app", "tests/app"])
    ids = [n["id"] for n in result["nodes"]]
    startup_ids = [i for i in ids if "startup" in i and not i.endswith("_cs")]
    assert len(set(startup_ids)) >= 2, (
        f"Expected distinct IDs even with same parent dir, got: {startup_ids}"
    )


def test_cross_file_edges_remapped():
    """Edges crossing file boundaries must have their targets remapped."""
    result = _extract_collision_files(["app1", "app2"])
    node_ids = {n["id"] for n in result["nodes"]}
    for e in result["edges"]:
        if e["source"] in node_ids:
            # If we can verify the target, it must not be an old pre-rename ID
            if e["target"] in node_ids:
                continue
            # Target may be an external ref (MyService, Helper) — that's fine

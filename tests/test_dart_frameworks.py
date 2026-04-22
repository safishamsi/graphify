from pathlib import Path
from graphify.extract import extract_dart

FIXTURES = Path(__file__).parent / "fixtures"

def _edges_of(r, relation):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == relation
    }

def _node_meta(r, label):
    return next((n for n in r["nodes"] if n["label"] == label), None)

def test_riverpod_watches_provider():
    r = extract_dart(FIXTURES / "sample_riverpod.dart")
    watches = _edges_of(r, "watches_provider")
    assert len(watches) > 0

def test_riverpod_reads_provider():
    r = extract_dart(FIXTURES / "sample_riverpod.dart")
    reads = _edges_of(r, "reads_provider")
    assert len(reads) > 0

def test_riverpod_framework_tag():
    r = extract_dart(FIXTURES / "sample_riverpod.dart")
    page = _node_meta(r, "CounterPage")
    assert page is not None
    assert "riverpod" in page.get("frameworks", [])

def test_bloc_handles_event():
    r = extract_dart(FIXTURES / "sample_bloc.dart")
    handles = _edges_of(r, "handles_event")
    assert len(handles) > 0

def test_bloc_framework_tag():
    r = extract_dart(FIXTURES / "sample_bloc.dart")
    bloc = _node_meta(r, "CounterBloc")
    assert bloc is not None
    assert "bloc" in bloc.get("frameworks", [])

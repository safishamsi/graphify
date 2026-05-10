from pathlib import Path
from graphify.extract import extract_pascal, extract

FIXTURES = Path(__file__).parent / "fixtures" / "pascal"

def test_pascal_import_resolution():
    """Verify that 'uses Foo' resolves to foo.pas in the same directory."""
    main_path = FIXTURES / "main.pas"
    foo_path = FIXTURES / "foo.pas"
    
    # Extract both
    r = extract([main_path, foo_path])
    
    # Check nodes
    node_ids = {n["id"] for n in r["nodes"]}
    # IDs are path-based for files
    main_nid = next(n["id"] for n in r["nodes"] if "main.pas" in n["label"])
    foo_nid = next(n["id"] for n in r["nodes"] if "foo.pas" in n["label"])
    
    # Verify imports edge from main to foo
    import_edges = [
        e for e in r["edges"] 
        if e["source"] == main_nid and e["target"] == foo_nid and e["relation"] == "imports"
    ]
    assert len(import_edges) == 1, f"Expected import edge from main to foo, found {import_edges}"

def test_pascal_placeholder_for_unresolvable_unit():
    """Verify that 'uses Bar' creates a placeholder node since bar.pas doesn't exist."""
    main_path = FIXTURES / "main.pas"
    
    r = extract_pascal(main_path)
    
    # Bar should be a placeholder node
    bar_nodes = [n for n in r["nodes"] if n["label"] == "Bar"]
    assert len(bar_nodes) == 1
    assert bar_nodes[0]["source_file"] == "" # Indicates placeholder
    
    # Edge from main to Bar
    main_nid = next(n["id"] for n in r["nodes"] if "main.pas" in n.get("label", ""))
    bar_nid = bar_nodes[0]["id"]
    
    import_edges = [
        e for e in r["edges"] 
        if e["source"] == main_nid and e["target"] == bar_nid and e["relation"] == "imports"
    ]
    assert len(import_edges) == 1

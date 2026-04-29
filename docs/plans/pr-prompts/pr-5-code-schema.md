# PR 5: Typed Code Schema

**Phase:** 8
**Stream:** B (Code Intelligence)
**Estimate:** 2-3 weeks
**Depends on:** Phase 1 (fork baseline)

## What to Build

### 1. Code Schema (`graphify/code_schema.py` — NEW)

Define 17 node types and 21 edge types as enums, plus typed dataclasses:

```python
from enum import Enum, auto
from dataclasses import dataclass, field

class NodeType(Enum):
    FUNCTION = auto()
    CLASS = auto()
    METHOD = auto()
    INTERFACE = auto()
    ENUM = auto()
    TYPE_ALIAS = auto()
    CONSTRUCTOR = auto()
    STRUCT = auto()
    TRAIT = auto()
    NAMESPACE = auto()
    MODULE = auto()
    ROUTE = auto()
    TOOL = auto()
    PROCESS = auto()
    CONCEPT = auto()      # Legacy: non-code files
    FILE = auto()         # File-level hub
    UNKNOWN = auto()

class EdgeType(Enum):
    CALLS = auto()
    IMPORTS = auto()
    IMPORTS_FROM = auto()
    EXTENDS = auto()
    IMPLEMENTS = auto()
    METHOD_OVERRIDES = auto()
    CONTAINS = auto()
    MEMBER_OF = auto()
    HANDLES_ROUTE = auto()
    STEP_IN_PROCESS = auto()
    USES = auto()
    REFERENCES = auto()
    RATIONALE_FOR = auto()
    SEMANTICALLY_SIMILAR_TO = auto()
    DEPENDS_ON = auto()
    CONFIGURES = auto()
    INFORMS = auto()
    INHERITS = auto()
    CASE_OF = auto()
    RELATES_TO = auto()

# Map from existing relation strings → EdgeType
RELATION_MAP: dict[str, EdgeType] = {
    "calls": EdgeType.CALLS,
    "imports": EdgeType.IMPORTS,
    "imports_from": EdgeType.IMPORTS_FROM,
    "extends": EdgeType.EXTENDS,
    "implements": EdgeType.IMPLEMENTS,
    "method_overrides": EdgeType.METHOD_OVERRIDES,
    "contains": EdgeType.CONTAINS,
    "method": EdgeType.MEMBER_OF,
    "handles_route": EdgeType.HANDLES_ROUTE,
    "step_in_process": EdgeType.STEP_IN_PROCESS,
    "uses": EdgeType.USES,
    "references": EdgeType.REFERENCES,
    "rationale_for": EdgeType.RATIONALE_FOR,
    "semantically_similar_to": EdgeType.SEMANTICALLY_SIMILAR_TO,
    "depends_on": EdgeType.DEPENDS_ON,
    "configures": EdgeType.CONFIGURES,
    "informs": EdgeType.INFORMS,
    "inherits": EdgeType.INHERITS,
    "case_of": EdgeType.CASE_OF,
}

# Map from file extension → default language for typed nodes
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".go": "go", ".java": "java", ".rs": "rust",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".rb": "ruby",
    ".cs": "csharp", ".kt": "kotlin", ".scala": "scala", ".php": "php",
    ".swift": "swift", ".lua": "lua", ".zig": "zig",
}
```

### 2. Typed Data Classes

```python
@dataclass
class TypedNode:
    id: str
    label: str
    node_type: NodeType
    source_file: str = ""
    source_location: str = ""
    language: str = ""
    signature: str = ""
    docstring: str = ""
    visibility: str = "public"
    is_exported: bool = False
    community: int | None = None
    
    def to_dict(self) -> dict:
        """Convert to extraction-compatible dict for build.py."""
        d = {
            "id": self.id, "label": self.label,
            "node_type": self.node_type.name,
            "file_type": "code",
            "source_file": self.source_file,
            "source_location": self.source_location,
        }
        if self.language: d["language"] = self.language
        if self.signature: d["signature"] = self.signature
        if self.docstring: d["docstring"] = self.docstring
        if self.visibility != "public": d["visibility"] = self.visibility
        if self.is_exported: d["is_exported"] = True
        return d

@dataclass
class TypedEdge:
    source: str
    target: str
    edge_type: EdgeType
    confidence: str = "EXTRACTED"
    confidence_score: float = 1.0
    source_file: str = ""
    source_location: str = ""
    weight: float = 1.0
    
    def to_dict(self) -> dict:
        """Convert to extraction-compatible dict for build.py."""
        return {
            "source": self.source, "target": self.target,
            "relation": self.edge_type.name.lower(),
            "confidence": self.confidence,
            "confidence_score": self.confidence_score,
            "source_file": self.source_file,
            "source_location": self.source_location,
            "weight": self.weight,
        }
```

### 3. Code Emitter (`graphify/code_emitter.py` — NEW)

```python
"""Unified edge emission with confidence tiers."""

CONFIDENCE_SCORES = {
    "EXTRACTED": 1.0,
    "INFERRED": 0.5,
    "AMBIGUOUS": 0.2,
}

def emit_node(node: TypedNode) -> dict:
    """Emit a typed node as an extraction dict entry."""
    return node.to_dict()

def emit_edge(edge: TypedEdge) -> dict:
    """Emit a typed edge as an extraction dict entry."""
    return edge.to_dict()

def infer_node_type_from_extraction(extraction_node: dict, file_path: str = "") -> NodeType:
    """Guess node type from existing extraction node dict.
    Heuristics based on label patterns, file_type, etc.
    Falls back to NodeType.UNKNOWN."""
    label = extraction_node.get("label", "")
    file_type = extraction_node.get("file_type", "")
    
    if file_type != "code":
        return NodeType.CONCEPT
    
    if not label:
        return NodeType.UNKNOWN
    
    # Heuristic matching
    if label.endswith("()"):
        if label.startswith("."):
            return NodeType.METHOD
        return NodeType.FUNCTION
    if label[0].isupper():
        return NodeType.CLASS
    
    return NodeType.UNKNOWN

def extractor_to_typed(extraction_node: dict, extraction_edge: dict = None) -> tuple[TypedNode, TypedEdge | None]:
    """Convert legacy extraction dicts to typed versions. Backward compatible bridge."""
    node_type = infer_node_type_from_extraction(extraction_node)
    typed_node = TypedNode(
        id=extraction_node.get("id", ""),
        label=extraction_node.get("label", ""),
        node_type=node_type,
        source_file=extraction_node.get("source_file", ""),
        source_location=extraction_node.get("source_location", ""),
        language=EXTENSION_LANGUAGE_MAP.get(
            Path(extraction_node.get("source_file", "")).suffix, ""
        ),
    )
    
    typed_edge = None
    if extraction_edge:
        relation = extraction_edge.get("relation", "relates_to")
        edge_type = RELATION_MAP.get(relation, EdgeType.RELATES_TO)
        typed_edge = TypedEdge(
            source=extraction_edge.get("source", ""),
            target=extraction_edge.get("target", ""),
            edge_type=edge_type,
            confidence=extraction_edge.get("confidence", "EXTRACTED"),
            confidence_score=CONFIDENCE_SCORES.get(
                extraction_edge.get("confidence", "EXTRACTED"), 1.0
            ),
            source_file=extraction_edge.get("source_file", ""),
            source_location=extraction_edge.get("source_location", ""),
            weight=extraction_edge.get("weight", 1.0),
        )
    
    return typed_node, typed_edge
```

### 4. Build Integration (`graphify/build.py` — EXTEND)

No breaking changes. Typed nodes/edges are additive:
- Legacy extraction dicts still work
- New `node_type` field on nodes is optional
- New `edge_type` field (stored as relation) is compatible

Add validation:
```python
def _validate_typed_nodes(nodes: list[dict]) -> list[str]:
    """Validate that typed nodes have valid NodeType values."""
    valid_types = {t.name for t in NodeType}
    warnings = []
    for node in nodes:
        nt = node.get("node_type")
        if nt and nt not in valid_types:
            warnings.append(f"node {node.get('id', '?')}: unknown node_type '{nt}'")
    return warnings
```

### 5. Tests

**`tests/test_code_schema.py` (NEW, 6+ tests):**
```python
from graphify.code_schema import (
    NodeType, EdgeType, RELATION_MAP, EXTENSION_LANGUAGE_MAP,
    TypedNode, TypedEdge,
)

def test_node_type_enum_values():
    """All node types are valid enum members."""
    assert NodeType.FUNCTION.name == "FUNCTION"
    assert NodeType.CONCEPT.name == "CONCEPT"

def test_edge_type_enum_values():
    """All edge types are valid enum members."""
    assert EdgeType.CALLS.name == "CALLS"

def test_relation_map_coverage():
    """All existing relation strings map to edge types."""
    assert "calls" in RELATION_MAP
    assert "imports" in RELATION_MAP
    assert "contains" in RELATION_MAP

def test_typed_node_to_dict():
    node = TypedNode(id="test_id", label="myFunc", node_type=NodeType.FUNCTION,
                     source_file="src/main.py", source_location="L42")
    d = node.to_dict()
    assert d["id"] == "test_id"
    assert d["node_type"] == "FUNCTION"

def test_typed_edge_to_dict():
    edge = TypedEdge(source="a", target="b", edge_type=EdgeType.CALLS,
                     confidence="EXTRACTED", confidence_score=1.0)
    d = edge.to_dict()
    assert d["relation"] == "calls"
    assert d["confidence_score"] == 1.0

def test_extension_language_map():
    assert EXTENSION_LANGUAGE_MAP[".py"] == "python"
    assert EXTENSION_LANGUAGE_MAP[".go"] == "go"
    assert EXTENSION_LANGUAGE_MAP[".ts"] == "typescript"
```

**`tests/test_code_emitter.py` (NEW, 5+ tests):**
```python
from graphify.code_emitter import (
    infer_node_type_from_extraction, extractor_to_typed,
    emit_node, emit_edge,
)
from graphify.code_schema import NodeType, EdgeType, TypedNode, TypedEdge

def test_infer_function():
    node = {"label": "myFunc()", "file_type": "code", "id": "mod_myfunc"}
    assert infer_node_type_from_extraction(node) == NodeType.FUNCTION

def test_infer_method():
    node = {"label": ".myMethod()", "file_type": "code", "id": "cls_mymethod"}
    assert infer_node_type_from_extraction(node) == NodeType.METHOD

def test_infer_class():
    node = {"label": "MyClass", "file_type": "code", "id": "mod_myclass"}
    assert infer_node_type_from_extraction(node) == NodeType.CLASS

def test_infer_concept():
    node = {"label": "Design Doc", "file_type": "document", "id": "doc_design"}
    assert infer_node_type_from_extraction(node) == NodeType.CONCEPT

def test_extractor_to_typed_roundtrip():
    node = {"id": "a", "label": "func()", "file_type": "code", "source_file": "x.py"}
    edge = {"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"}
    typed_node, typed_edge = extractor_to_typed(node, edge)
    assert typed_node.node_type == NodeType.FUNCTION
    assert typed_edge.edge_type == EdgeType.CALLS
```

## Files Changed/Created

| File | Action | Purpose |
|------|--------|---------|
| `graphify/code_schema.py` | **New** | NodeType, EdgeType enums, TypedNode, TypedEdge dataclasses |
| `graphify/code_emitter.py` | **New** | Emit typed nodes/edges, heuristic type inference, backward compat bridge |
| `graphify/build.py` | **Extend** | Validate typed nodes, no-op on legacy extraction dicts |
| `tests/test_code_schema.py` | **New** | Schema enum + dataclass tests |
| `tests/test_code_emitter.py` | **New** | Emitter + inference tests |

## Compatibility
- Zero breaking changes. All existing extraction dicts work unchanged.
- `node_type` field is optional on nodes — absent = UNKNOWN (legacy behavior)
- `RELATION_MAP` maps existing relation strings to EdgeType — backward compatible
- graph.json format unchanged (new fields additive)
- All existing MCP tools unchanged

## Verification
```bash
pytest tests/test_code_schema.py tests/test_code_emitter.py -q
pytest tests/ -q  # full suite must pass
```

### Schema Coverage Validation

```bash
python -c "
from graphify.code_schema import NodeType, EdgeType, infer_node_type_from_extraction, RELATION_MAP
import json
G = json.load(open('graphify-out/graph.json'))
nodes = G.get('nodes', [])
edges = G.get('edges', [])

# Node type coverage
typed = sum(1 for n in nodes if n.get('node_type') not in (None, 'UNKNOWN'))
unknown = sum(1 for n in nodes if n.get('node_type') == 'UNKNOWN')
print(f'Node type coverage: {typed}/{len(nodes)} ({100*typed/len(nodes):.1f}%) typed')

# Edge type coverage
mapped = sum(1 for e in edges if e.get('relation', '') in RELATION_MAP)
print(f'Edge type coverage: {mapped}/{len(edges)} ({100*mapped/len(edges):.1f}%) mapped')
"
```

This gates Phase 8 completion: >90% of nodes should have a non-UNKNOWN type on real codebases.

### Commit

```bash
git add -A && git commit -m "feat(phase-8): typed code schema (17 node types, 21 edge types)"
```

---

## Code Review Checklist

Before merging this PR, verify:
- [ ] All tests pass: `pytest tests/ -q`
- [ ] Schema coverage validation shows >90% node type coverage on real codebase
- [ ] All existing extraction dicts work unchanged (legacy compat)
- [ ] TypedNode.to_dict() output is valid extraction dict
- [ ] TypedEdge.to_dict() maps edge_type.name.lower() → relation field
- [ ] RELATION_MAP covers all existing relation strings
- [ ] NodeType/EdgeType enums have correct number of members
- [ ] At least 1 other developer reviewed

---

## CI Verification
```bash
# Run automated verification for this PR:
bash docs/plans/verify-pr.sh 5

# Expected checks:
# - Full test suite passes
# - tests/test_code_schema.py + tests/test_code_emitter.py pass
# - Schema coverage >90% on real codebase
# - benchmark snapshot archived to graphify-out/benchmarks/phase-5-benchmark.json

# After passing, update PROGRESS.md:
# - Set PR 5 status to ✅ Done
# - Fill commit hash: git log -1 --format="%H"
# - Record benchmark data from graphify-out/benchmarks/phase-5-benchmark.json
```

---

## Prompt (paste into AI coding agent)

```
You are implementing Phase 8 of the Graphify fork enhancement plan.

Repository: ~/graphify
Branch: feat/phase-8-code-schema

TASK: Create typed code schema with enums and dataclasses for code-aware graph representation.

## PART A: Code Schema (graphify/code_schema.py)

Create graphify/code_schema.py:

1. Define NodeType enum with these members: FUNCTION, CLASS, METHOD, INTERFACE, ENUM, TYPE_ALIAS, CONSTRUCTOR, STRUCT, TRAIT, NAMESPACE, MODULE, ROUTE, TOOL, PROCESS, CONCEPT, FILE, UNKNOWN.

2. Define EdgeType enum with these members: CALLS, IMPORTS, IMPORTS_FROM, EXTENDS, IMPLEMENTS, METHOD_OVERRIDES, CONTAINS, MEMBER_OF, HANDLES_ROUTE, STEP_IN_PROCESS, USES, REFERENCES, RATIONALE_FOR, SEMANTICALLY_SIMILAR_TO, DEPENDS_ON, CONFIGURES, INFORMS, INHERITS, CASE_OF, RELATES_TO.

3. Define RELATION_MAP: dict[str, EdgeType] — maps existing relation strings ("calls", "imports", "contains", etc.) to EdgeType enum members.

4. Define EXTENSION_LANGUAGE_MAP: dict[str, str] — file extension (.py, .ts, .go, .java, .rs, etc.) → language string.

5. Define TypedNode dataclass with fields: id, label, node_type (NodeType), source_file, source_location, language, signature, docstring, visibility, is_exported, community. Add to_dict() method returning extraction-compatible dict (with node_type field).

6. Define TypedEdge dataclass with fields: source, target, edge_type (EdgeType), confidence, confidence_score, source_file, source_location, weight. Add to_dict() method returning extraction-compatible dict.

7. TypedNode.to_dict() should generate the existing format PLUS new optional fields (node_type, language, signature, etc.). TypedEdge.to_dict() generates standard extraction edge dict with relation = edge_type.name.lower().

## PART B: Code Emitter (graphify/code_emitter.py)

Create graphify/code_emitter.py:

8. emit_node(node: TypedNode) → dict: Calls node.to_dict().

9. emit_edge(edge: TypedEdge) → dict: Calls edge.to_dict().

10. infer_node_type_from_extraction(node: dict, file_path="") → NodeType: Heuristic type inference from existing extraction node dicts. Rules:
    - file_type != "code" → CONCEPT
    - label ends with "()" and starts with "." → METHOD
    - label ends with "()" → FUNCTION  
    - label[0].isupper() → CLASS
    - falls back to UNKNOWN

11. extractor_to_typed(node: dict, edge: dict = None) → tuple[TypedNode, TypedEdge | None]: Convert legacy extraction dicts to typed versions. Uses infer_node_type_from_extraction for node type, RELATION_MAP for edge type.

## PART C: Build Integration

12. In graphify/build.py, add _validate_typed_nodes(nodes) that checks node_type values are valid NodeType members. Call it from build_from_json (warn only, don't reject).

## PART D: Tests

13. Create tests/test_code_schema.py with 6+ tests covering: enum values exist, relation map coverage, TypedNode.to_dict output, TypedEdge.to_dict output, extension language map correctness.

14. Create tests/test_code_emitter.py with 5+ tests covering: infer FUNCTION, infer METHOD, infer CLASS, infer CONCEPT, roundtrip extractor_to_typed.

ZERO BREAKING CHANGES. Existing extraction dicts work unchanged. node_type field is OPTIONAL. All MCP tools unchanged.

MATCH EXISTING CODE STYLE. Use same patterns (from __future__ import annotations, etc.).

RUN `pytest tests/ -q` after implementation. All existing tests must pass.

RUN the schema coverage validation above. >90% of code nodes should type correctly.

RUN `git add -A && git commit -m "feat(phase-8): typed code schema (17 node types, 21 edge types)"`
```

"""Static analysis enhancement for Graphify - LSP-lite alternative.

This module provides enhanced call graph extraction using static analysis
when full LSP servers are not available. It focuses on code repository
use cases by extracting:

1. Complete function call chains (including indirect calls)
2. Method/attribute access chains (obj.method().prop)
3. String-based require/include/imports
4. Event handler patterns
5. Callback registrations
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from networkx.readwrite import json_graph
    import networkx as nx
except ImportError:
    nx = None
    json_graph = None


@dataclass
class CallSite:
    """Represents a function/method call site in code."""

    caller: str  # Calling function/node ID
    callee: str  # Called function/method name
    file_path: str
    line: int
    column: int
    call_type: str  # direct, indirect, method, chain, callback
    confidence: float = 1.0


@dataclass
class Reference:
    """Represents a symbol reference."""

    referrer: str  # Node that references
    referenced: str  # Node being referenced
    ref_type: str  # variable, function, class, method
    file_path: str
    line: int


class StaticAnalyzer:
    """Static analysis for enhanced call graph extraction."""

    # Language-specific patterns
    PATTERNS = {
        "lua": {
            "function_def": r'^\s*function\s+(\w+)\s*\(',
            "method_def": r'^\s*function\s+(\w+):(\w+)\s*\(',
            "local_function": r'^\s*local\s+function\s+(\w+)\s*\(',
            "direct_call": r'(\w+)\s*\(',
            "method_call": r'(\w+):(\w+)\s*\(',
            "chain_call": r'(\w+)\.(\w+)\s*\(',
            "string_require": r'require\s*\(\s*["\']([^"\']+)["\']',
        },
        "python": {
            "function_def": r'^\s*def\s+(\w+)\s*\(',
            "method_def": r'^\s*def\s+(\w+)\s*\(',
            "direct_call": r'(\w+)\s*\(',
            "method_call": r'(\w+)\.(\w+)\s*\(',
            "chain_call": r'(\w+)\.(\w+)\.(\w+)\s*\(',
            "string_import": r'from\s+(\w+)\s+import|import\s+(\w+)',
        },
        "javascript": {
            "function_def": r'function\s+(\w+)\s*\(',
            "arrow_def": r'(\w+)\s*=\s*(?:\([^)]*\)\s*=>|\w+\s*\()',
            "direct_call": r'(\w+)\s*\(',
            "method_call": r'(\w+)\.(\w+)\s*\(',
            "chain_call": r'(\w+)\.(\w+)\.(\w+)\s*\(',
            "require_call": r'require\s*\(\s*["\']([^"\']+)["\']',
        },
    }

    # Callback/event patterns
    CALLBACK_PATTERNS = {
        "lua": [
            r'(\w+)\.on\(\s*["\'](\w+)["\']\s*,\s*(\w+)',  # obj.on('event', callback)
            r'(\w+)\.Add\((\w+)',  # obj:Add(callback)
            r'(\w+)\.Connect\((\w+)',  # signal:Connect(callback)
        ],
        "javascript": [
            r'(\w+)\.on\(\s*["\'](\w+)["\']\s*,\s*(\w+)',  # obj.on('event', callback)
            r'(\w+)\.addEventListener\(\s*["\'](\w+)["\']\s*,\s*(\w+)',
            r'(\w+)\.then\((\w+)',  # promise.then(callback)
        ],
    }

    def __init__(self, root_path: Path, language: str = "auto"):
        self.root_path = root_path
        self.language = language
        self.calls: list[CallSite] = []
        self.references: list[Reference] = []
        self.defined_symbols: dict[str, set[str]] = {}  # file -> symbols

    def detect_language(self, file_path: Path) -> str | None:
        """Detect programming language from file extension."""
        if self.language != "auto":
            return self.language

        ext_map = {
            ".lua": "lua",
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".go": "go",
            ".rs": "rust",
        }
        return ext_map.get(file_path.suffix.lower())

    def extract_from_file(self, file_path: Path) -> list[CallSite]:
        """Extract call sites from a single file."""
        language = self.detect_language(file_path)
        if not language or language not in self.PATTERNS:
            return []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            return []

        calls = []
        lines = content.split("\n")
        patterns = self.PATTERNS[language]

        # Track defined symbols in this file
        defined = set()
        file_stem = file_path.stem
        current_function = None  # Track current function scope

        for line_num, line in enumerate(lines, 1):
            # Extract function definitions
            for pattern_name, pattern in patterns.items():
                if "def" in pattern_name:
                    match = re.search(pattern, line)
                    if match:
                        func_name = match.group(1)
                        node_id = f"{file_stem}_{func_name.lower()}"
                        defined.add(func_name)
                        if pattern_name == "method_def":
                            # Class.method
                            class_name = match.group(1)
                            method_name = match.group(2)
                            node_id = f"{file_stem}_{class_name.lower()}_{method_name.lower()}"
                            defined.add(f"{class_name}.{method_name}")
                        current_function = node_id

            # Extract calls
            for pattern_name, pattern in patterns.items():
                if "call" in pattern_name or "require" in pattern_name or "import" in pattern_name:
                    matches = re.finditer(pattern, line)
                    for match in matches:
                        groups = match.groups()
                        if not groups:
                            continue

                        caller = current_function or f"{file_stem}_file"
                        callee = groups[0]
                        call_type = "direct"

                        # Determine call type and target
                        if pattern_name == "method_call":
                            # obj:method()
                            obj, method = groups[0], groups[1]
                            callee = f"{obj.lower()}:{method}"
                            call_type = "method"
                        elif pattern_name == "chain_call":
                            # obj.method().prop()
                            callee = ".".join(g for g in groups if g)
                            call_type = "chain"
                        elif pattern_name == "string_require" or pattern_name == "string_import":
                            # require("module")
                            callee = groups[1] if len(groups) > 1 else groups[0]
                            call_type = "import"

                        if callee and callee not in ["if", "while", "for", "function"]:
                            calls.append(CallSite(
                                caller=caller,
                                callee=callee,
                                file_path=str(file_path.relative_to(self.root_path)),
                                line=line_num,
                                column=match.start(),
                                call_type=call_type,
                            ))

            # Extract callback registrations
            if language in self.CALLBACK_PATTERNS:
                for callback_pattern in self.CALLBACK_PATTERNS[language]:
                    for match in re.finditer(callback_pattern, line):
                        groups = match.groups()
                        if len(groups) >= 3:
                            caller = current_function or f"{file_stem}_file"
                            # obj.on('event', callback)
                            obj, event, callback = groups[0], groups[1], groups[2]
                            callee = f"{obj.lower()}.{event.lower()}"
                            calls.append(CallSite(
                                caller=caller,
                                callee=callee,
                                file_path=str(file_path.relative_to(self.root_path)),
                                line=line_num,
                                column=match.start(),
                                call_type="callback",
                            ))

        self.defined_symbols[str(file_path.relative_to(self.root_path))] = defined
        return calls

    def extract_all(self, file_pattern: str | None = None) -> list[CallSite]:
        """Extract call sites from all relevant files."""
        all_calls = []

        for file_path in self.root_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self.root_path)
                # Skip common non-source directories
                if any(part.startswith('.') for part in rel_path.parts):
                    continue
                if "node_modules" in rel_path.parts or "vendor" in rel_path.parts:
                    continue

                calls = self.extract_from_file(file_path)
                all_calls.extend(calls)

        return all_calls

    def resolve_targets(
        self, calls: list[CallSite], all_symbols: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Resolve call targets to node IDs."""
        edges = []

        for call in calls:
            # Try to find the callee in defined symbols
            callee_key = call.callee.lower()

            # Direct match
            if callee_key in all_symbols:
                edges.append({
                    "source": call.caller,
                    "target": all_symbols[callee_key],
                    "relation": "calls",
                    "confidence": "EXTRACTED",
                    "confidence_score": call.confidence,
                    "source_file": call.file_path,
                    "source_location": f"L{call.line}",
                    "weight": 1.0,
                    "_enhanced_by": "static",
                    "_call_type": call.call_type,
                })
            else:
                # Create an unresolved reference node
                target_id = f"external_{callee_key}"
                edges.append({
                    "source": call.caller,
                    "target": target_id,
                    "relation": "calls",
                    "confidence": "INFERRED",
                    "confidence_score": 0.6,
                    "source_file": call.file_path,
                    "source_location": f"L{call.line}",
                    "weight": 0.6,
                    "_enhanced_by": "static",
                    "_call_type": call.call_type,
                    "_unresolved": True,
                })

        return edges


class GraphEnhancer:
    """Enhance existing graph with static analysis results."""

    def __init__(self, graph_path: Path, root_path: Path):
        self.graph_path = graph_path
        self.root_path = root_path
        self.graph_data = None
        self.load_graph()

    def load_graph(self) -> None:
        """Load existing graph."""
        if not self.graph_path.exists():
            raise FileNotFoundError(f"Graph not found: {self.graph_path}")

        with open(self.graph_path, encoding="utf-8") as f:
            self.graph_data = json.load(f)

    def get_symbol_map(self) -> dict[str, str]:
        """Build a map of symbol names to node IDs."""
        symbol_map = {}
        nodes = self.graph_data.get("nodes", [])

        for node in nodes:
            label = node.get("label", "")
            node_id = node.get("id", "")
            if label and node_id:
                # Map by various forms
                label_lower = label.lower().rstrip("()")
                symbol_map[label_lower] = node_id
                symbol_map[label] = node_id

        return symbol_map

    def add_edges(self, new_edges: list[dict[str, Any]]) -> dict[str, Any]:
        """Add new edges to the graph."""
        existing_links = self.graph_data.get("links", [])
        existing_nodes = self.graph_data.get("nodes", [])

        # Build lookup for deduplication
        existing_edges = set()
        for edge in existing_links:
            key = (edge.get("source"), edge.get("target"), edge.get("relation"))
            existing_edges.add(key)

        # Filter duplicates and add nodes for unresolved targets
        added_edges = []
        added_nodes = []

        for edge in new_edges:
            key = (edge.get("source"), edge.get("target"), edge.get("relation"))
            if key in existing_edges:
                continue

            # Check if target node exists
            target_id = edge.get("target")
            target_exists = any(n.get("id") == target_id for n in existing_nodes + added_nodes)

            if not target_exists and edge.get("_unresolved"):
                # Create a placeholder node for unresolved references
                added_nodes.append({
                    "id": target_id,
                    "label": edge.get("target", "").replace("external_", ""),
                    "file_type": "external",
                    "_enhanced_by": "static",
                    "_unresolved": True,
                })

            added_edges.append(edge)
            existing_edges.add(key)

        # Merge into graph
        self.graph_data["nodes"].extend(added_nodes)
        self.graph_data["links"].extend(added_edges)

        # Update metadata
        metadata = self.graph_data.get("_metadata", {})
        metadata["static_enhanced"] = True
        metadata["static_edges_added"] = metadata.get("static_edges_added", 0) + len(added_edges)
        metadata["static_nodes_added"] = metadata.get("static_nodes_added", 0) + len(added_nodes)
        self.graph_data["_metadata"] = metadata

        return {
            "edges_added": len(added_edges),
            "nodes_added": len(added_nodes),
            "total_edges": len(self.graph_data["links"]),
            "total_nodes": len(self.graph_data["nodes"]),
        }

    def save(self, output_path: Path | None = None) -> None:
        """Save enhanced graph."""
        output_path = output_path or self.graph_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.graph_data, f, indent=2)


def run_static_enhancement(
    root_path: Path,
    graph_path: Path | None = None,
    language: str = "auto",
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run static analysis enhancement.

    Args:
        root_path: Project root directory
        graph_path: Path to existing graph.json
        language: Programming language (auto-detect if 'auto')
        output_path: Output path (default: overwrite input)

    Returns:
        Statistics about the enhancement
    """
    graph_path = graph_path or root_path / "graphify-out" / "graph.json"

    print(f"Static analysis enhancement for: {root_path}")
    print(f"Graph: {graph_path}")

    # Load and enhance graph
    enhancer = GraphEnhancer(graph_path, root_path)

    # Get symbol map for resolution
    symbol_map = enhancer.get_symbol_map()
    print(f"Loaded {len(symbol_map)} symbols from graph")

    # Run static analysis
    analyzer = StaticAnalyzer(root_path, language=language)
    calls = analyzer.extract_all()
    print(f"Extracted {len(calls)} call sites")

    # Resolve targets and create edges
    edges = analyzer.resolve_targets(calls, symbol_map)
    print(f"Resolved to {len(edges)} edges")

    # Add edges to graph
    stats = enhancer.add_edges(edges)
    enhancer.save(output_path)

    print(f"\nEnhancement complete:")
    print(f"  Edges added: {stats['edges_added']}")
    print(f"  Nodes added: {stats['nodes_added']}")
    print(f"  Total edges: {stats['total_edges']}")
    print(f"  Total nodes: {stats['total_nodes']}")

    # Print breakdown by call type
    call_types = {}
    for edge in edges:
        ctype = edge.get("_call_type", "unknown")
        call_types[ctype] = call_types.get(ctype, 0) + 1

    if call_types:
        print(f"\nEdges by call type:")
        for ctype, count in sorted(call_types.items(), key=lambda x: -x[1]):
            print(f"  {ctype}: {count}")

    return stats


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Enhance graphify graph with static analysis"
    )
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Project root (default: current directory)",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help="Path to graph.json",
    )
    parser.add_argument(
        "--language",
        "-l",
        default="auto",
        choices=["auto", "lua", "python", "javascript", "typescript"],
        help="Programming language",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output path",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show detailed statistics",
    )

    args = parser.parse_args()

    try:
        stats = run_static_enhancement(
            root_path=args.path,
            graph_path=args.graph,
            language=args.language,
            output_path=args.output,
        )

        if args.stats:
            print("\nDetailed statistics available in graph metadata")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nPlease run '/graphify' first to create the initial graph.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

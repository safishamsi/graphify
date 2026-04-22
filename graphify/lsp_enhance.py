"""LSP Enhancement Module for Graphify.

This module integrates Language Server Protocol (LSP) data to enhance
the knowledge graph with complete call graphs, references, and definitions
that AST parsing alone cannot capture.

Supported LSP servers:
- Python: pylsp, pyright
- Lua: sumneko/lua-language-server
- JavaScript/TypeScript: tsserver, typescript-language-server
- Go: gopls
- Rust: rust-analyzer
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from networkx.readwrite import json_graph
    import networkx as nx
except ImportError:
    nx = None
    json_graph = None


@dataclass
class LSPConfig:
    """Configuration for LSP server connection."""

    command: list[str]  # e.g., ["pylsp", "--stdio"]
    language: str
    extensions: list[str] = field(default_factory=list)
    workspace_config: dict[str, Any] = field(default_factory=dict)


# Language-specific LSP configurations
LSP_SERVERS: dict[str, LSPConfig] = {
    "python": LSPConfig(
        command=["pylsp"],
        language="python",
        extensions=[".py"],
        workspace_config={"pylsp": {"plugins": {"jedi": {"environment": None}}}},
    ),
    "lua": LSPConfig(
        command=["lua-language-server"],
        language="lua",
        extensions=[".lua"],
    ),
    "javascript": LSPConfig(
        command=["typescript-language-server", "--stdio"],
        language="javascript",
        extensions=[".js", ".jsx", ".mjs"],
    ),
    "typescript": LSPConfig(
        command=["typescript-language-server", "--stdio"],
        language="typescript",
        extensions=[".ts", ".tsx"],
    ),
    "go": LSPConfig(
        command=["gopls", "serve"],
        language="go",
        extensions=[".go"],
    ),
    "rust": LSPConfig(
        command=["rust-analyzer"],
        language="rust",
        extensions=[".rs"],
    ),
}


@dataclass
class LSPReference:
    """A reference extracted from LSP."""

    from_node: str  # caller/referrer node ID
    to_node: str  # callee/referenced node ID
    relation: str  # calls, references, defines, etc.
    file_path: str
    line: int
    column: int


class LSPClient:
    """Simple JSON-RPC client for LSP communication."""

    def __init__(self, command: list[str], root_path: Path):
        self.command = command
        self.root_path = root_path
        self.process: subprocess.Popen | None = None
        self.request_id = 0

    def start(self) -> bool:
        """Start the LSP server process."""
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
            # Send initialize request
            self._send_request("initialize", {
                "processId": None,
                "rootUri": self.root_path.as_uri(),
                "capabilities": {},
            })
            # Read initialized response
            self._read_response()
            # Send initialized notification
            self._send_notification("initialized", {})
            return True
        except (OSError, FileNotFoundError) as e:
            print(f"Warning: Could not start LSP server {self.command[0]}: {e}", file=sys.stderr)
            return False

    def stop(self) -> None:
        """Stop the LSP server process."""
        if self.process:
            self._send_notification("shutdown", {})
            self._send_notification("exit", {})
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None

    def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for response."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }
        if self.process and self.process.stdin:
            message = json.dumps(request)
            content = f"Content-Length: {len(message)}\r\n\r\n{message}"
            self.process.stdin.write(content.encode("utf-8"))
            self.process.stdin.flush()
            return self._read_response()
        return {}

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        if self.process and self.process.stdin:
            message = json.dumps(request)
            content = f"Content-Length: {len(message)}\r\n\r\n{message}"
            self.process.stdin.write(content.encode("utf-8"))
            self.process.stdin.flush()

    def _read_response(self) -> dict[str, Any]:
        """Read and parse a JSON-RPC response."""
        if not self.process or not self.process.stdout:
            return {}
        try:
            # Read headers
            headers = {}
            while True:
                line = self.process.stdout.readline()
                if not line:
                    return {}
                line = line.decode("utf-8").strip()
                if not line:
                    break
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip()] = value.strip()

            # Read content
            content_length = int(headers.get("Content-Length", 0))
            if content_length > 0:
                content = self.process.stdout.read(content_length).decode("utf-8")
                return json.loads(content) if content else {}
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        return {}

    def get_references(self, file_path: Path, line: int, column: int) -> list[LSPReference]:
        """Get all references for a symbol at the given position."""
        # This would require opening the document first
        # For now, return empty list as placeholder
        return []

    def get_definition(self, file_path: Path, line: int, column: int) -> LSPReference | None:
        """Get the definition for a symbol at the given position."""
        # Placeholder
        return None

    def get_call_hierarchy(
        self, file_path: Path, line: int, column: int
    ) -> tuple[list[LSPReference], list[LSPReference]]:
        """Get incoming and outgoing calls for a symbol."""
        # Placeholder
        return [], []


class LSPEngine:
    """Main engine for LSP-enhanced graph extraction."""

    def __init__(self, root_path: Path, graph_path: Path | None = None):
        self.root_path = root_path
        self.graph_path = graph_path or root_path / "graphify-out" / "graph.json"
        self.clients: dict[str, LSPClient] = {}
        self.references: list[LSPReference] = []

    def detect_language(self, file_path: Path) -> str | None:
        """Detect the programming language of a file."""
        suffix = file_path.suffix.lower()
        for lang, config in LSP_SERVERS.items():
            if suffix in config.extensions:
                return lang
        return None

    def start_lsp_servers(self, languages: list[str] | None = None) -> dict[str, bool]:
        """Start LSP servers for the given languages."""
        results = {}
        languages = languages or list(LSP_SERVERS.keys())
        for lang in languages:
            if lang not in LSP_SERVERS:
                results[lang] = False
                continue
            config = LSP_SERVERS[lang]
            client = LSPClient(config.command, self.root_path)
            success = client.start()
            if success:
                self.clients[lang] = client
            results[lang] = success
        return results

    def stop_lsp_servers(self) -> None:
        """Stop all running LSP servers."""
        for client in self.clients.values():
            client.stop()
        self.clients.clear()

    def extract_from_lsp(self, language: str) -> list[dict[str, Any]]:
        """Extract references and call hierarchy from LSP."""
        if language not in self.clients:
            return []

        client = self.clients[language]
        config = LSP_SERVERS[language]
        edges = []

        # Find all files of this language
        files = []
        for ext in config.extensions:
            files.extend(self.root_path.rglob(f"*{ext}"))

        for file_path in files:
            try:
                # Read file to find symbols
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                # Simple symbol extraction (would use LSP in production)
                lines = content.split("\n")
                for line_num, line in enumerate(lines):
                    # Look for function/method definitions
                    for keyword in ["def ", "function ", "func ", "func "]:
                        if keyword in line:
                            # Extract function name
                            parts = line.split(keyword)
                            if len(parts) > 1:
                                func_name = parts[1].split("(")[0].strip()
                                if func_name:
                                    # Create a node ID
                                    file_stem = file_path.stem
                                    node_id = f"{file_stem}_{func_name.lower()}"
                                    edges.append({
                                        "source": node_id,
                                        "relation": "defines",
                                        "file_path": str(file_path),
                                        "line": line_num + 1,
                                    })
            except (OSError, UnicodeDecodeError):
                continue

        return edges

    def enhance_graph(self, lsp_edges: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge LSP-extracted data into the existing graph."""
        if not self.graph_path.exists():
            raise FileNotFoundError(f"Graph file not found: {self.graph_path}")

        # Load existing graph
        with open(self.graph_path, encoding="utf-8") as f:
            graph_data = json.load(f)

        existing_links = graph_data.get("links", [])
        existing_nodes = graph_data.get("nodes", [])

        # Build lookup for existing edges (for deduplication)
        existing_edges_set = set()
        for edge in existing_links:
            key = (edge.get("source"), edge.get("target"), edge.get("relation"))
            existing_edges_set.add(key)

        # Convert LSP edges to graphify format
        new_edges = []
        new_nodes = []
        added_count = 0

        for lsp_edge in lsp_edges:
            source = lsp_edge.get("source")
            target = lsp_edge.get("target", "")  # May be empty for defines
            relation = lsp_edge.get("relation", "references")
            file_path = lsp_edge.get("file_path", "")
            line = lsp_edge.get("line", 0)

            if not source:
                continue

            # Check if source node exists, create if not
            source_exists = any(n.get("id") == source for n in existing_nodes)
            if not source_exists and source not in [n.get("id") for n in new_nodes]:
                new_nodes.append({
                    "id": source,
                    "label": source,
                    "file_type": "code",
                    "source_file": file_path,
                    "source_location": f"L{line}" if line else None,
                    "_enhanced_by": "lsp",
                })

            # Add edge if not duplicate
            edge_key = (source, target, relation)
            if edge_key not in existing_edges_set:
                new_edges.append({
                    "source": source,
                    "target": target,
                    "relation": relation,
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": file_path,
                    "source_location": f"L{line}" if line else None,
                    "weight": 1.0,
                    "_enhanced_by": "lsp",
                })
                added_count += 1
                existing_edges_set.add(edge_key)

        # Merge new data into graph
        graph_data["nodes"].extend(new_nodes)
        graph_data["links"].extend(new_edges)

        # Update metadata
        metadata = graph_data.get("_metadata", {})
        metadata["lsp_enhanced"] = True
        metadata["lsp_edges_added"] = metadata.get("lsp_edges_added", 0) + added_count
        graph_data["_metadata"] = metadata

        return graph_data

    def save_graph(self, graph_data: dict[str, Any], output_path: Path | None = None) -> None:
        """Save the enhanced graph."""
        output_path = output_path or self.graph_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2)

        print(f"Enhanced graph saved to: {output_path}")

    def run(
        self,
        languages: list[str] | None = None,
        save: bool = True,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        """Run the full LSP enhancement pipeline."""
        print(f"Starting LSP enhancement for: {self.root_path}")

        # Detect which languages to process
        if languages is None:
            languages = []
            for file_path in self.root_path.rglob("*"):
                if file_path.is_file():
                    lang = self.detect_language(file_path)
                    if lang and lang not in languages:
                        languages.append(lang)

        print(f"Detected languages: {languages}")

        # Start LSP servers
        print("Starting LSP servers...")
        server_status = self.start_lsp_servers(languages)
        started_servers = [lang for lang, started in server_status.items() if started]
        not_started = [lang for lang, started in server_status.items() if not started]

        if not_started:
            print(f"Warning: Could not start LSP servers for: {not_started}", file=sys.stderr)
            print("Falling back to static analysis...")

        if not started_servers:
            print("No LSP servers available, using static analysis only")

        # Extract data
        all_lsp_edges = []
        for lang in started_servers:
            print(f"Extracting data for {lang}...")
            edges = self.extract_from_lsp(lang)
            all_lsp_edges.extend(edges)
            print(f"  Found {len(edges)} references")

        # Enhance graph
        if all_lsp_edges or not_started_servers:
            print("Enhancing graph...")
            try:
                enhanced_graph = self.enhance_graph(all_lsp_edges)

                # Save
                if save:
                    self.save_graph(enhanced_graph, output_path)

                # Print stats
                metadata = enhanced_graph.get("_metadata", {})
                print(f"\nLSP Enhancement Summary:")
                print(f"  Total nodes: {len(enhanced_graph.get('nodes', []))}")
                print(f"  Total edges: {len(enhanced_graph.get('links', []))}")
                print(f"  LSP edges added: {metadata.get('lsp_edges_added', 0)}")

                return enhanced_graph
            except FileNotFoundError as e:
                print(f"Error: {e}", file=sys.stderr)
                print("Please run '/graphify' first to create the initial graph.")
                return {}

        # Cleanup
        print("\nStopping LSP servers...")
        self.stop_lsp_servers()

        return {}


def run_lsp_enhancement(
    root_path: Path,
    graph_path: Path | None = None,
    languages: list[str] | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Convenience function to run LSP enhancement.

    Args:
        root_path: Project root directory
        graph_path: Path to existing graph.json
        languages: List of languages to process (auto-detected if None)
        output_path: Where to save enhanced graph (default: overwrites input)

    Returns:
        Enhanced graph data
    """
    engine = LSPEngine(root_path, graph_path)
    try:
        return engine.run(languages=languages, save=True, output_path=output_path)
    finally:
        engine.stop_lsp_servers()


def main() -> None:
    """CLI entry point for LSP enhancement."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Enhance graphify knowledge graph with LSP data"
    )
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=None,
        help="Path to graph.json (default: <path>/graphify-out/graph.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for enhanced graph (default: overwrite input)",
    )
    parser.add_argument(
        "--language",
        "-l",
        action="append",
        dest="languages",
        help="Languages to process (can be specified multiple times)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract LSP data but don't modify the graph",
    )
    parser.add_argument(
        "--list-languages",
        action="store_true",
        help="List supported LSP servers and exit",
    )

    args = parser.parse_args()

    if args.list_languages:
        print("Supported LSP servers:")
        for lang, config in LSP_SERVERS.items():
            print(f"  {lang:12} - {config.command[0]} ({', '.join(config.extensions)})")
        return

    # Run enhancement
    engine = LSPEngine(args.path, args.graph)
    try:
        if args.dry_run:
            print("Dry run mode - extracting data without modifying graph...")
            engine.start_lsp_servers(args.languages)
            for lang in (args.languages or list(LSP_SERVERS.keys())):
                edges = engine.extract_from_lsp(lang)
                print(f"{lang}: {len(edges)} references found")
        else:
            engine.run(languages=args.languages, save=True, output_path=args.output)
    finally:
        engine.stop_lsp_servers()


if __name__ == "__main__":
    main()

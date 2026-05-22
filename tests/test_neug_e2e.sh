#!/usr/bin/env bash
#
# End-to-end test for graphify + NeuG integration.
#
# Tests the full flow:
#   1. graphify extract (AST-only, no LLM) → graph.json + graph.db
#   2. graphify cypher  → query against graph.db
#   3. Incremental re-extract → graph.db updated
#   4. MCP server tool registration (smoke test)
#
# Prerequisites:
#   - pip install neug
#   - graphify installed from current source (pip install -e .)
#
# Usage:
#   bash tests/test_neug_e2e.sh
#
set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

pass() { echo -e "  ${GREEN}PASS${NC}: $1"; ((PASS++)); }
fail() { echo -e "  ${RED}FAIL${NC}: $1"; ((FAIL++)); }
skip() { echo -e "  ${YELLOW}SKIP${NC}: $1"; ((SKIP++)); }

echo "======================================"
echo " graphify + NeuG E2E Integration Test"
echo "======================================"
echo ""

# --- Check prerequisites ---
if ! python3 -c "import neug" 2>/dev/null; then
    echo "ERROR: neug not installed. Run: pip install neug"
    exit 1
fi

if ! python3 -c "import graphify" 2>/dev/null; then
    echo "ERROR: graphify not importable. Run: pip install -e . from graphify root"
    exit 1
fi

# --- Setup test project ---
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

PROJECT="$TMPDIR/sample_project"
mkdir -p "$PROJECT/src"

cat > "$PROJECT/src/main.py" << 'PYEOF'
"""Main application module."""

class Database:
    """Database connection manager."""
    def __init__(self, url: str):
        self.url = url
        self.conn = None

    def connect(self):
        """Establish connection."""
        from src.utils import validate_url
        validate_url(self.url)
        self.conn = True
        return self

    def query(self, sql: str):
        """Execute a query."""
        if not self.conn:
            raise RuntimeError("Not connected")
        return []


class App:
    """Main application."""
    def __init__(self):
        self.db = Database("localhost:5432")

    def run(self):
        self.db.connect()
        results = self.db.query("SELECT 1")
        return results
PYEOF

cat > "$PROJECT/src/utils.py" << 'PYEOF'
"""Utility functions."""

def validate_url(url: str) -> bool:
    """Validate a database URL."""
    if not url:
        raise ValueError("Empty URL")
    return ":" in url


def format_result(row: dict) -> str:
    """Format a query result row."""
    return ", ".join(f"{k}={v}" for k, v in row.items())


class Logger:
    """Simple logger."""
    def __init__(self, name: str):
        self.name = name

    def info(self, msg: str):
        print(f"[{self.name}] {msg}")
PYEOF

cat > "$PROJECT/src/models.py" << 'PYEOF'
"""Data models."""
from src.utils import Logger

class User:
    """User model."""
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email
        self.logger = Logger("User")

    def save(self):
        self.logger.info(f"Saving user {self.name}")

class Session:
    """Session model."""
    def __init__(self, user: User):
        self.user = user
        self.active = True

    def close(self):
        self.active = False
PYEOF

echo "Test project created at $PROJECT"
echo ""

# ============================================================
# TEST 1: First extract (AST-only, no cluster)
# ============================================================
echo "[Test 1] graphify extract (first build, no-semantic, no-cluster)"

OUTPUT=$(cd "$PROJECT" && GEMINI_API_KEY=dummy python3 -m graphify extract . --no-semantic --no-cluster 2>&1)

CLEAN_OUTPUT=$(echo "$OUTPUT" | grep -v "^INFO\|^E20")
if echo "$CLEAN_OUTPUT" | grep -q "graph.db written"; then
    pass "graph.db written message present"
else
    if [ -d "$PROJECT/graphify-out/graph.db" ]; then
        pass "graph.db created (message may be suppressed)"
    else
        fail "graph.db NOT created"
        echo "    Output: $(echo "$CLEAN_OUTPUT" | grep -i 'neug\|graph.db\|warning\|error' | head -5)"
    fi
fi

if [ -f "$PROJECT/graphify-out/graph.json" ]; then
    pass "graph.json created"
else
    fail "graph.json NOT created"
fi

# Verify graph.json has nodes
NODE_COUNT=$(python3 -c "
import json
d = json.load(open('$PROJECT/graphify-out/graph.json'))
print(len(d.get('nodes', [])))
")
if [ "$NODE_COUNT" -gt 0 ]; then
    pass "graph.json has $NODE_COUNT nodes"
else
    fail "graph.json has 0 nodes"
fi

echo ""

# ============================================================
# TEST 2: graphify cypher — query the database
# ============================================================
echo "[Test 2] graphify cypher — Cypher queries against graph.db"

DB_PATH="$PROJECT/graphify-out/graph.db"

if [ ! -e "$DB_PATH" ]; then
    skip "graph.db not available, skipping cypher tests"
else
    # Count all nodes
    CYPHER_COUNT=$(python3 -m graphify cypher "MATCH (n:code) RETURN count(n)" --db "$DB_PATH" 2>/dev/null | grep -v "^INFO\|^E20")
    if [ -n "$CYPHER_COUNT" ] && [ "$CYPHER_COUNT" != "0" ]; then
        pass "cypher count query returned: $CYPHER_COUNT"
    else
        fail "cypher count query returned empty or zero"
    fi

    # Query node labels
    CYPHER_LABELS=$(python3 -m graphify cypher "MATCH (n:code) RETURN n.label LIMIT 5" --db "$DB_PATH" 2>/dev/null | grep -v "^INFO\|^E20")
    if [ -n "$CYPHER_LABELS" ]; then
        pass "cypher label query returned results"
    else
        fail "cypher label query returned empty"
    fi

    # Query edges
    CYPHER_EDGES=$(python3 -m graphify cypher "MATCH (a:code)-[e:edge_code_code]->(b:code) RETURN a.label, e.relation, b.label LIMIT 5" --db "$DB_PATH" 2>/dev/null | grep -v "^INFO\|^E20")
    if [ -n "$CYPHER_EDGES" ]; then
        pass "cypher edge query returned results"
    else
        fail "cypher edge query returned empty (may have no code->code edges)"
    fi

    # Error case: bad query
    BAD_RESULT=$(python3 -m graphify cypher "INVALID CYPHER" --db "$DB_PATH" 2>&1 | grep -v "^INFO\|^E20" || true)
    if echo "$BAD_RESULT" | grep -qi "error\|fail\|traceback"; then
        pass "bad cypher query properly errors"
    else
        fail "bad cypher query did not error"
    fi

    # Error case: missing db
    MISS_RESULT=$(python3 -m graphify cypher "MATCH (n) RETURN n" --db "/nonexistent/path.db" 2>&1 | grep -v "^INFO\|^E20" || true)
    if echo "$MISS_RESULT" | grep -qi "not found\|error"; then
        pass "missing db properly errors"
    else
        fail "missing db did not error"
    fi
fi

echo ""

# ============================================================
# TEST 3: Incremental extract (modify a file, re-run)
# ============================================================
echo "[Test 3] Incremental extract (modify file, re-run)"

# Modify a file
cat >> "$PROJECT/src/utils.py" << 'PYEOF'

def new_function():
    """A newly added function."""
    return 42
PYEOF

OUTPUT2=$(cd "$PROJECT" && GEMINI_API_KEY=dummy python3 -m graphify extract . --no-semantic --no-cluster 2>&1)

CLEAN_OUTPUT2=$(echo "$OUTPUT2" | grep -v "^INFO\|^E20")
if echo "$CLEAN_OUTPUT2" | grep -q "incremental"; then
    pass "incremental mode detected"
else
    skip "incremental mode not detected in output"
fi

# Check that graph.db still exists and is queryable
if [ -e "$DB_PATH" ]; then
    CYPHER_INC=$(python3 -m graphify cypher "MATCH (n:code) RETURN count(n)" --db "$DB_PATH" 2>/dev/null | grep -v "^INFO\|^E20" || echo "ERROR")
    if [ "$CYPHER_INC" != "ERROR" ] && [ -n "$CYPHER_INC" ]; then
        pass "graph.db still queryable after incremental ($CYPHER_INC nodes)"
    else
        fail "graph.db not queryable after incremental"
    fi
else
    skip "graph.db not available for incremental test"
fi

echo ""

# ============================================================
# TEST 4: Python API — storage module direct test
# ============================================================
echo "[Test 4] Python API — storage module"

python3 << 'PYTEST'
import sys, json, tempfile, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath("__file__"))))
from graphify.storage import init_db, ingest_extraction, ingest_communities, execute_cypher, close_db

# Small extraction (under 4096 limit)
extraction = {
    "nodes": [
        {"id": "fn_main", "label": "main()", "file_type": "code", "source_file": "app.py", "source_location": "L1"},
        {"id": "fn_helper", "label": "helper()", "file_type": "code", "source_file": "app.py", "source_location": "L10"},
        {"id": "concept_arch", "label": "architecture", "file_type": "concept", "source_file": "docs.md"},
    ],
    "edges": [
        {"source": "fn_main", "target": "fn_helper", "relation": "calls", "confidence": "EXTRACTED", "source_file": "app.py", "weight": 1.0},
        {"source": "fn_main", "target": "concept_arch", "relation": "implements", "confidence": "INFERRED", "source_file": "app.py", "weight": 0.8},
    ],
}

d = tempfile.mkdtemp()
db_path = os.path.join(d, "test.db")
db, conn = init_db(db_path)

# First build
ingest_extraction(conn, extraction, incremental=False)
nodes = execute_cypher(conn, "MATCH (n:code) RETURN count(n)")
assert nodes[0][0] == 2, f"Expected 2 code nodes, got {nodes[0][0]}"

edges = execute_cypher(conn, "MATCH ()-[e:edge_code_code]->() RETURN count(e)")
assert edges[0][0] == 1, f"Expected 1 code-code edge, got {edges[0][0]}"

# Communities
ingest_communities(conn, {0: ["fn_main", "fn_helper"], 1: ["concept_arch"]})
comm = execute_cypher(conn, "MATCH (n:code {id: 'fn_main'}) RETURN n.community")
assert comm[0][0] == 0, f"Expected community 0, got {comm[0][0]}"

# Incremental update
extraction["nodes"][0]["label"] = "main_v2()"
ingest_extraction(conn, extraction, incremental=True)
updated = execute_cypher(conn, "MATCH (n:code {id: 'fn_main'}) RETURN n.label")
assert updated[0][0] == "main_v2()", f"Expected 'main_v2()', got {updated[0][0]}"

close_db(db, conn)
print("  All Python API assertions passed")
PYTEST

if [ $? -eq 0 ]; then
    pass "Python API test passed"
else
    fail "Python API test failed"
fi

echo ""

# ============================================================
# TEST 5: MCP server tool registration (smoke test)
# ============================================================
echo "[Test 5] MCP server — cypher_query tool registered"

python3 << 'MCPTEST'
import sys
# Check that serve.py has cypher_query in its tool list
import importlib.util
spec = importlib.util.find_spec("graphify.serve")
if spec is None:
    print("  graphify.serve not found")
    sys.exit(1)

source = open(spec.origin).read()
if "cypher_query" in source and "_tool_cypher_query" in source:
    print("  cypher_query tool found in serve.py")
    sys.exit(0)
else:
    print("  cypher_query tool NOT found in serve.py")
    sys.exit(1)
MCPTEST

if [ $? -eq 0 ]; then
    pass "cypher_query tool registered in MCP server"
else
    fail "cypher_query tool not found in MCP server"
fi

echo ""

# ============================================================
# TEST 6: Graceful fallback when neug not installed
# ============================================================
echo "[Test 6] Graceful fallback (simulated)"

python3 << 'FALLBACK'
import sys, importlib, types

# Simulate neug not being importable by temporarily removing it
saved = sys.modules.pop("neug", None)
saved_storage = sys.modules.pop("graphify.storage", None)

# Create a fake module that raises ImportError
blocker = types.ModuleType("neug")
blocker.__spec__ = None

class NeuGBlocker:
    def find_module(self, name, path=None):
        if name == "neug" or name.startswith("neug."):
            return self
    def load_module(self, name):
        raise ImportError("simulated: neug not installed")

sys.meta_path.insert(0, NeuGBlocker())

try:
    # This should raise ImportError (caught by __main__.py)
    from graphify.storage import init_db
    print("  ERROR: import should have failed")
    sys.exit(1)
except ImportError:
    print("  ImportError correctly raised when neug missing")
    sys.exit(0)
finally:
    sys.meta_path.pop(0)
    if saved:
        sys.modules["neug"] = saved
    if saved_storage:
        sys.modules["graphify.storage"] = saved_storage
FALLBACK

if [ $? -eq 0 ]; then
    pass "graceful fallback when neug not installed"
else
    fail "fallback test failed"
fi

echo ""

# ============================================================
# Summary
# ============================================================
echo "======================================"
TOTAL=$((PASS + FAIL + SKIP))
echo -e " Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$SKIP skipped${NC} / $TOTAL total"
echo "======================================"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
exit 0

"""Cross-language Tauri bridge: TS invoke("X", ...) ↔ Rust #[tauri::command] fn X."""

from pathlib import Path

from graphify.extract import (
    _collect_js_tauri_invokes,
    _collect_rust_tauri_commands,
    _TS_CONFIG,
    extract,
    extract_rust,
)


def _write_rust(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def _write_ts(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


# ── Rust attribute detection ─────────────────────────────────────────────────

def test_rust_extractor_attaches_tauri_commands(tmp_path):
    """extract_rust must populate result['tauri_commands'] for #[tauri::command] fns."""
    src = _write_rust(tmp_path, "commands.rs", """
#[tauri::command]
pub async fn cmd_health_check() -> Result<String, String> {
    Ok("ok".to_string())
}

fn not_a_command() {}
""")
    result = extract_rust(src)
    cmds = result.get("tauri_commands", [])
    names = {c["name"] for c in cmds}
    assert "cmd_health_check" in names, f"expected cmd_health_check in {names}"
    assert "not_a_command" not in names, f"unattributed fn leaked: {names}"


def test_rust_extractor_handles_bare_command_attribute(tmp_path):
    """`#[command]` (after `use tauri::command`) must also be detected."""
    src = _write_rust(tmp_path, "lib.rs", """
use tauri::command;

#[command]
pub fn cmd_simple() -> String { "hi".into() }
""")
    result = extract_rust(src)
    names = {c["name"] for c in result.get("tauri_commands", [])}
    assert "cmd_simple" in names


def test_rust_extractor_skips_other_attributes(tmp_path):
    """`#[derive(Debug)]` or `#[cfg(test)]` decorated fns must not be flagged."""
    src = _write_rust(tmp_path, "noise.rs", """
#[derive(Debug)]
struct Foo;

#[cfg(test)]
fn helper() {}

#[tauri::command]
fn real_cmd() -> u32 { 1 }
""")
    result = extract_rust(src)
    names = {c["name"] for c in result.get("tauri_commands", [])}
    assert names == {"real_cmd"}


# ── TS invoke detection ──────────────────────────────────────────────────────

def test_ts_extractor_collects_simple_invoke(tmp_path):
    src = _write_ts(tmp_path, "client.ts", """
import { invoke } from "@tauri-apps/api/core";

export async function fetchHealth() {
    return await invoke("cmd_health_check");
}
""")
    invokes = _collect_js_tauri_invokes(src, _TS_CONFIG)
    cmd_names = {inv["command_name"] for inv in invokes}
    assert "cmd_health_check" in cmd_names


def test_ts_extractor_collects_generic_invoke(tmp_path):
    """`invoke<Type>(...)` parses with `await invoke` as the function field;
    detection must reach inside the await_expression."""
    src = _write_ts(tmp_path, "typed.ts", """
import { invoke } from "@tauri-apps/api/core";

export async function getReport() {
    const r = await invoke<{status: string}>("cmd_get_report");
    return r;
}
""")
    invokes = _collect_js_tauri_invokes(src, _TS_CONFIG)
    cmd_names = {inv["command_name"] for inv in invokes}
    assert "cmd_get_report" in cmd_names


def test_ts_extractor_skips_dynamic_invoke(tmp_path):
    """invoke(variable, ...) cannot be statically resolved — must be skipped."""
    src = _write_ts(tmp_path, "dynamic.ts", """
import { invoke } from "@tauri-apps/api/core";

export async function dispatch(cmd: string) {
    return await invoke(cmd);
}
""")
    invokes = _collect_js_tauri_invokes(src, _TS_CONFIG)
    assert invokes == []


# ── End-to-end bridge resolution ─────────────────────────────────────────────

def test_extract_bridges_ts_invoke_to_rust_command(tmp_path):
    """TS invoke("X") + Rust #[tauri::command] fn X must produce an `invokes` edge."""
    rust = _write_rust(tmp_path, "commands.rs", """
#[tauri::command]
pub async fn cmd_ping() -> String { "pong".into() }
""")
    ts = _write_ts(tmp_path, "api.ts", """
import { invoke } from "@tauri-apps/api/core";

export async function ping() {
    return await invoke<string>("cmd_ping");
}
""")
    result = extract([ts, rust])
    invoke_edges = [e for e in result["edges"] if e.get("relation") == "invokes"]
    assert len(invoke_edges) == 1, (
        f"Expected exactly one bridge edge, got {invoke_edges}"
    )
    edge = invoke_edges[0]
    assert edge["context"] == "tauri_command"
    assert edge["confidence"] == "EXTRACTED"

    nodes_by_id = {n["id"]: n for n in result["nodes"]}
    src_label = nodes_by_id[edge["source"]]["label"]
    tgt_label = nodes_by_id[edge["target"]]["label"]
    assert src_label == "ping()"
    assert tgt_label == "cmd_ping()"


def test_extract_skips_ambiguous_commands(tmp_path):
    """If the same #[tauri::command] name exists in two files, skip the bridge."""
    _write_rust(tmp_path, "a.rs", """
#[tauri::command]
pub fn cmd_dup() {}
""")
    _write_rust(tmp_path, "b.rs", """
#[tauri::command]
pub fn cmd_dup() {}
""")
    ts = _write_ts(tmp_path, "client.ts", """
import { invoke } from "@tauri-apps/api/core";
export async function call() { await invoke("cmd_dup"); }
""")
    rust_files = sorted(tmp_path.glob("*.rs"))
    result = extract([ts, *rust_files])
    invoke_edges = [e for e in result["edges"] if e.get("relation") == "invokes"]
    assert invoke_edges == []


def test_extract_no_op_without_rust_side(tmp_path):
    """TS-only project (no Rust commands) must not synthesize invokes edges."""
    ts = _write_ts(tmp_path, "client.ts", """
import { invoke } from "@tauri-apps/api/core";
export async function call() { await invoke("cmd_missing"); }
""")
    result = extract([ts])
    invoke_edges = [e for e in result["edges"] if e.get("relation") == "invokes"]
    assert invoke_edges == []


def test_extract_no_op_without_ts_side(tmp_path):
    """Rust-only project (no TS invokes) must not synthesize invokes edges."""
    rust = _write_rust(tmp_path, "lib.rs", """
#[tauri::command]
pub fn cmd_alone() {}
""")
    result = extract([rust])
    invoke_edges = [e for e in result["edges"] if e.get("relation") == "invokes"]
    assert invoke_edges == []

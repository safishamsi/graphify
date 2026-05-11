from __future__ import annotations

import argparse
from collections import deque
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse


LANGUAGE_IDS = {
    "javascript": "javascript",
    "python": "python",
    "ruby": "ruby",
    "typescript": "typescript",
}

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def path_to_uri(path: Path) -> str:
    return path.resolve().as_uri()


def initialize_capabilities() -> dict:
    """Capabilities kept intentionally small for broad stdio LSP compatibility."""
    return {
        "textDocument": {
            "definition": {"linkSupport": True},
        },
    }


def uri_to_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def command_label(command: list[str]) -> str:
    if not command:
        return "lsp"
    return " ".join(sanitized_command(command))


def sanitized_command(command: list[str]) -> list[str]:
    return [_sanitize_command_token(part) for part in command]


def _sanitize_command_token(token: object) -> str:
    value = str(token)
    if "/" in value or "\\" in value:
        return re.split(r"[\\/]+", value.rstrip("\\/"))[-1] or "<path>"
    return value


def sanitize_text(value: object, root: Path) -> str:
    text = str(value)
    replacements = [
        (str(root.resolve()), "<workspace>"),
        (str(Path.home().resolve()), "<home>"),
    ]
    for raw, replacement in replacements:
        if raw:
            text = text.replace(raw, replacement)
    return text


class LspClient:
    def __init__(self, command: list[str], cwd: Path):
        self.cwd = cwd
        self.root_uri = path_to_uri(cwd)
        self.proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._next_id = 1
        self._send_lock = threading.Lock()
        self._messages: queue.Queue[dict] = queue.Queue()
        self._stderr: deque[str] = deque(maxlen=200)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._err_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._err_reader.start()

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        for raw in iter(self.proc.stderr.readline, b""):
            text = raw.decode("utf-8", errors="replace").rstrip()
            if text:
                self._stderr.append(text)

    def _read_message(self) -> dict | None:
        assert self.proc.stdout is not None
        headers: dict[str, str] = {}
        while True:
            line = self.proc.stdout.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            text = line.decode("ascii", errors="replace").strip()
            if ":" in text:
                key, value = text.split(":", 1)
                headers[key.lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        if length <= 0:
            return None
        body = self.proc.stdout.read(length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    def _read_loop(self) -> None:
        while self.proc.poll() is None:
            try:
                message = self._read_message()
            except Exception as exc:
                self._messages.put({"method": "$/graphifyReadError", "params": {"error": str(exc)}})
                return
            if message is None:
                return
            self._messages.put(message)

    def _send(self, payload: dict) -> None:
        assert self.proc.stdin is not None
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        with self._send_lock:
            self.proc.stdin.write(header + body)
            self.proc.stdin.flush()

    def notify(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

    def _handle_server_request(self, message: dict) -> None:
        method = message.get("method")
        params = message.get("params")
        result = None
        if method == "workspace/configuration":
            items = params.get("items", []) if isinstance(params, dict) else []
            result = [{} for _ in items]
        elif method == "workspace/workspaceFolders":
            result = [{"uri": self.root_uri, "name": self.cwd.name}]
        self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def send_request(self, method: str, params: dict | None = None) -> int:
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)
        return request_id

    def read_protocol_message(self, *, timeout: float) -> dict:
        try:
            message = self._messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("LSP response timed out") from exc
        if "id" in message and "method" in message:
            self._handle_server_request(message)
            return self.read_protocol_message(timeout=timeout)
        return message

    def request(self, method: str, params: dict | None = None, *, timeout: float = 20.0) -> dict:
        request_id = self.send_request(method, params)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"LSP request timed out: {method}")
            message = self.read_protocol_message(timeout=remaining)
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result")

    def close(self) -> None:
        if self.proc.poll() is not None:
            return
        try:
            self.request("shutdown", {}, timeout=5.0)
            self.notify("exit")
        except Exception:
            self.proc.terminate()

    def stderr_tail(self, limit: int = 50) -> list[str]:
        return list(self._stderr)[-limit:]

def load_exchange(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("LSP exchange JSON must be an object")
    return data


def rel_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def project_key(path: Path, root: Path) -> tuple[str, bool]:
    try:
        return str(path.resolve().relative_to(root.resolve())), True
    except ValueError:
        return str(path), False


def symbol_lookup(symbols: list[dict], root: Path) -> dict[str, list[dict]]:
    by_file: dict[str, list[dict]] = {}
    for symbol in symbols:
        source_file = symbol.get("source_file")
        if not source_file:
            continue
        path = Path(str(source_file))
        key, _inside_project = project_key(path if path.is_absolute() else root / path, root)
        by_file.setdefault(key, []).append(symbol)
    for bucket in by_file.values():
        bucket.sort(key=lambda item: item.get("source_line") or 0)
    return by_file


def _definition_line(range_obj: dict) -> int | None:
    try:
        return int(range_obj.get("start", {}).get("line", 0)) + 1
    except (TypeError, ValueError):
        return None


def _symbol_summary(symbol: dict) -> dict:
    return {
        "id": symbol.get("id"),
        "label": symbol.get("label"),
        "source_line": symbol.get("source_line"),
    }


def nearest_symbols(candidates: list[dict], line: int | None, *, limit: int = 3) -> list[dict]:
    if line is None:
        return []
    positioned = [
        symbol for symbol in candidates
        if isinstance(symbol.get("source_line"), int)
    ]
    positioned.sort(key=lambda symbol: abs(int(symbol["source_line"]) - line))
    return [_symbol_summary(symbol) for symbol in positioned[:limit]]


def pick_symbol(
    uri: str,
    range_obj: dict,
    symbols_by_file: dict[str, list[dict]],
    root: Path,
) -> tuple[dict | None, str, dict]:
    path = uri_to_path(uri)
    if path is None:
        return None, "non_file_uri", {}
    key, inside_project = project_key(path, root)
    candidates = symbols_by_file.get(key, [])
    line = _definition_line(range_obj)
    details = {
        "definition_in_project": inside_project,
        "definition_line": line,
    }
    if inside_project:
        details["definition_file"] = key
    if not candidates:
        return None, "external_definition" if not inside_project else "no_symbol_file", details
    exact = [symbol for symbol in candidates if symbol.get("source_line") == line]
    if exact:
        return exact[0], "exact_line", details
    previous = [
        symbol for symbol in candidates
        if isinstance(symbol.get("source_line"), int)
        and 0 <= line - int(symbol["source_line"]) <= 3
    ]
    if previous:
        return previous[-1], "near_previous_line", details
    details["nearest_symbols"] = nearest_symbols(candidates, line)
    return None, "no_symbol_near_line", details


def definition_locations(result: object) -> list[tuple[str, dict]]:
    if result is None:
        return []
    items = result if isinstance(result, list) else [result]
    locations: list[tuple[str, dict]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "targetUri" in item:
            range_obj = item.get("targetSelectionRange") or item.get("targetRange") or {}
            locations.append((item["targetUri"], range_obj))
        elif "uri" in item:
            locations.append((item["uri"], item.get("range", {})))
    return locations


def call_debug(call: dict) -> dict:
    return {
        "caller": call.get("caller"),
        "callee": call.get("callee"),
        "receiver": call.get("receiver"),
        "call_shape": call.get("call_shape"),
        "source_file": call.get("source_file"),
        "source_location": call.get("source_location"),
        "callee_range": call.get("callee_range"),
    }


def under_limit(items: list, limit: int) -> bool:
    if limit == 0:
        return False
    if limit < 0:
        return True
    return len(items) < limit


def safe_filename(value: str) -> str:
    normalized = _SAFE_FILENAME_RE.sub("_", value.strip()).strip("._")
    return normalized or "resolver"


def output_path(enrichment_dir: Path, language: str, output: dict) -> Path:
    resolver = output.get("metadata", {}).get("resolver_name")
    if resolver:
        return enrichment_dir / f"{language}_{safe_filename(str(resolver))}_lsp_edges.json"
    return enrichment_dir / f"{language}_lsp_edges.json"


def write_output(enrichment_dir: Path, language: str, output: dict) -> Path:
    path = output_path(enrichment_dir, language, output)
    path.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )
    return path


def progress(message: str) -> None:
    print(f"[graphify lsp] {message}", flush=True)


def progress_snapshot(language: str, output: dict, *, index: int, total: int, started_at: float) -> None:
    metadata = output["metadata"]
    elapsed = max(time.monotonic() - started_at, 0.001)
    rate = metadata["requests_sent"] / elapsed
    progress(
        f"{language}: {index}/{total} calls, "
        f"requests={metadata['requests_sent']}, defs={metadata['definitions_seen']}, "
        f"evidence={len(output.get('lsp_evidence', []))}, edges={len(output['edges'])}, empty={metadata['empty_definition_results']}, "
        f"errors={len(metadata['errors'])}, {rate:.1f} req/s"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("language")
    parser.add_argument("--limit", type=int, default=0, help="maximum callsites to query; 0 means unlimited")
    parser.add_argument("--settle-seconds", type=float, default=5.0)
    parser.add_argument("--request-timeout", type=float, default=20.0)
    parser.add_argument("--request-concurrency", type=int, default=1, help="definition requests in flight per server")
    parser.add_argument("--max-errors", type=int, default=10, help="maximum LSP errors before stopping; 0 means unlimited")
    parser.add_argument("--debug-unmapped", type=int, default=25, help="maximum unmapped definitions to record; 0 disables, -1 means unlimited")
    parser.add_argument("--debug-errors", type=int, default=25, help="maximum request errors to record with call context; 0 disables, -1 means unlimited")
    parser.add_argument("--progress-every", type=int, default=100, help="print progress every N requests; 0 disables count-based progress")
    parser.add_argument("--progress-seconds", type=float, default=5.0, help="print progress at least every N seconds; 0 disables time-based progress")
    args, server = parser.parse_known_args()

    if server and server[0] == "--":
        server = server[1:]
    if not server:
        raise SystemExit("missing LSP server command")

    root = Path(os.environ["GRAPHIFY_ROOT"]).resolve()
    exchange_path = Path(os.environ["GRAPHIFY_UNRESOLVED_CALLS"])
    enrichment_dir = Path(os.environ["GRAPHIFY_ENRICHMENT_DIR"])
    enrichment_dir.mkdir(parents=True, exist_ok=True)
    hook_name = os.environ.get("GRAPHIFY_HOOK_NAME", "").strip()
    resolver_name = hook_name.split(":")[-1] if hook_name else ""
    progress_label = f"{args.language}/{resolver_name}" if resolver_name else args.language

    exchange = load_exchange(exchange_path)
    language_calls = [
        call for call in exchange.get("unresolved_calls", [])
        if call.get("language") == args.language
    ]
    candidate_calls = [
        call for call in exchange.get("unresolved_calls", [])
        if call.get("language") == args.language
        and call.get("callee_range")
        and call.get("source_file")
    ]
    calls = candidate_calls if args.limit <= 0 else candidate_calls[:args.limit]
    symbols_by_file = symbol_lookup(exchange.get("symbols", []), root)
    progress(
        f"{progress_label}: server={command_label(server)!r}, "
        f"language_calls={len(language_calls)}, candidate_calls={len(candidate_calls)}, "
        f"limit={'unlimited' if args.limit <= 0 else args.limit}"
    )

    output = {
        "generated_by": "graphify-lsp-definition-hook",
        "language": args.language,
        "lsp_server": command_label(server),
        "edges": [],
        "lsp_evidence": [],
        "metadata": {
            "hook_name": hook_name or None,
            "resolver_name": resolver_name or None,
            "server_command": sanitized_command(server),
            "transport": "stdio",
            "root": sanitize_text(root, root),
            "root_uri": sanitize_text(path_to_uri(root), root),
            "server_cwd": sanitize_text(root, root),
            "calls_seen": len(calls),
            "language_calls": len(language_calls),
            "candidate_calls": len(candidate_calls),
            "call_limit": None if args.limit <= 0 else args.limit,
            "settle_seconds": max(args.settle_seconds, 0),
            "request_timeout": args.request_timeout,
            "max_errors": None if args.max_errors <= 0 else args.max_errors,
            "debug_unmapped_limit": args.debug_unmapped,
            "debug_errors_limit": args.debug_errors,
            "request_concurrency": max(args.request_concurrency, 1),
            "requests_sent": 0,
            "started_at": time.time(),
            "definitions_seen": 0,
            "mapped_edges": 0,
            "evidence_records": 0,
            "duplicate_edges": 0,
            "self_edges": 0,
            "empty_definition_results": 0,
            "missing_source_files": 0,
            "errors": [],
            "error_details": [],
            "empty_definition_calls": [],
            "missing_source_file_details": [],
            "unmapped_definitions": [],
            "server_returncode": None,
            "server_stderr_tail": [],
        },
    }
    if not calls:
        write_output(enrichment_dir, args.language, output)
        progress(f"{progress_label}: no candidate calls")
        return 0

    try:
        progress(f"{progress_label}: starting LSP server")
        client = LspClient(server, root)
    except Exception as exc:
        error = sanitize_text(exc, root)
        output["metadata"]["startup_failed"] = True
        output["metadata"]["errors"].append(error)
        output["metadata"]["error_details"].append({
            "phase": "startup",
            "error_type": type(exc).__name__,
            "error": error,
        })
        write_output(enrichment_dir, args.language, output)
        progress(f"{progress_label}: startup failed: {error}")
        return 0

    opened: set[str] = set()
    processed_calls = 0

    def maybe_progress(call_index: int) -> None:
        nonlocal last_progress_at
        now = time.monotonic()
        count_due = (
            args.progress_every > 0
            and output["metadata"]["requests_sent"] > 0
            and output["metadata"]["requests_sent"] % args.progress_every == 0
        )
        time_due = args.progress_seconds > 0 and now - last_progress_at >= args.progress_seconds
        if count_due or time_due:
            progress_snapshot(progress_label, output, index=call_index, total=len(calls), started_at=started_at)
            last_progress_at = now

    try:
        root_uri = path_to_uri(root)
        try:
            progress(f"{progress_label}: initialize")
            client.request(
                "initialize",
                {
                    "processId": os.getpid(),
                    "rootUri": root_uri,
                    "workspaceFolders": [{"uri": root_uri, "name": root.name}],
                    "capabilities": initialize_capabilities(),
                },
                timeout=args.request_timeout,
            )
        except Exception as exc:
            error = sanitize_text(exc, root)
            output["metadata"]["initialize_failed"] = True
            output["metadata"]["errors"].append(error)
            output["metadata"]["error_details"].append({
                "phase": "initialize",
                "error_type": type(exc).__name__,
                "error": error,
            })
            client.close()
            output["metadata"]["server_returncode"] = client.proc.poll()
            output["metadata"]["server_stderr_tail"] = [
                sanitize_text(line, root) for line in client.stderr_tail()
            ]
            write_output(enrichment_dir, args.language, output)
            progress(f"{progress_label}: initialize failed: {error}")
            return 0
        client.notify("initialized", {})
        time.sleep(max(args.settle_seconds, 0))
        started_at = time.monotonic()
        last_progress_at = started_at
        progress(f"{progress_label}: initialized; querying {len(calls)} callsite(s)")

        def record_definition_error(call: dict, exc: Exception) -> bool:
            error = sanitize_text(exc, root)
            output["metadata"]["errors"].append(error)
            if under_limit(output["metadata"]["error_details"], args.debug_errors):
                detail = {
                    "phase": "definition",
                    "error_type": type(exc).__name__,
                    "error": error,
                }
                detail.update(call_debug(call))
                output["metadata"]["error_details"].append(detail)
            return (
                client.proc.poll() is not None
                or (
                    args.max_errors > 0
                    and len(output["metadata"]["errors"]) >= args.max_errors
                )
            )

        def enqueue_definition_request(call_index: int, call: dict) -> tuple[int, int, dict, float] | None:
            nonlocal processed_calls
            processed_calls = max(processed_calls, call_index)
            source_file = Path(str(call["source_file"]))
            path = source_file if source_file.is_absolute() else root / source_file
            if not path.exists():
                output["metadata"]["missing_source_files"] += 1
                if under_limit(output["metadata"]["missing_source_file_details"], args.debug_errors):
                    output["metadata"]["missing_source_file_details"].append(call_debug(call))
                maybe_progress(call_index)
                return None
            uri = path_to_uri(path)
            if uri not in opened:
                client.notify(
                    "textDocument/didOpen",
                    {
                        "textDocument": {
                            "uri": uri,
                            "languageId": LANGUAGE_IDS.get(args.language, args.language),
                            "version": 1,
                            "text": path.read_text(encoding="utf-8", errors="replace"),
                        }
                    },
                )
                opened.add(uri)
            position = call["callee_range"]["start"]
            try:
                output["metadata"]["requests_sent"] += 1
                request_id = client.send_request(
                    "textDocument/definition",
                    {"textDocument": {"uri": uri}, "position": position},
                )
            except Exception as exc:
                record_definition_error(call, exc)
                maybe_progress(call_index)
                return None
            return request_id, call_index, call, time.monotonic() + args.request_timeout

        def handle_definition_result(call_index: int, call: dict, result: object) -> None:
            locations = definition_locations(result)
            if not locations:
                output["metadata"]["empty_definition_results"] += 1
                if under_limit(output["metadata"]["empty_definition_calls"], args.debug_unmapped):
                    output["metadata"]["empty_definition_calls"].append(call_debug(call))
                maybe_progress(call_index)
                return
            evidence_definitions: list[dict] = []
            for def_uri, def_range in locations:
                output["metadata"]["definitions_seen"] += 1
                target, reason, details = pick_symbol(def_uri, def_range, symbols_by_file, root)
                definition = {
                    "range": def_range,
                    "mapping_reason": reason,
                }
                definition.update(details)
                if not target:
                    if under_limit(output["metadata"]["unmapped_definitions"], args.debug_unmapped):
                        sample = {
                            "reason": reason,
                            "caller": call.get("caller"),
                            "callee": call.get("callee"),
                            "receiver": call.get("receiver"),
                            "source_file": call.get("source_file"),
                            "source_location": call.get("source_location"),
                            "definition_file": details.get("definition_file"),
                            "definition_range": def_range,
                        }
                        sample.update(details)
                        output["metadata"]["unmapped_definitions"].append(sample)
                    evidence_definitions.append(definition)
                    continue
                definition["target_id"] = target["id"]
                definition["target"] = _symbol_summary(target)
                evidence_definitions.append(definition)
            if evidence_definitions:
                output["lsp_evidence"].append({
                    "call_id": call.get("call_id"),
                    "caller": call.get("caller"),
                    "callee": call.get("callee"),
                    "receiver": call.get("receiver"),
                    "receiver_node_type": call.get("receiver_node_type"),
                    "call_shape": call.get("call_shape"),
                    "source_file": call.get("source_file"),
                    "source_location": call.get("source_location"),
                    "callee_range": call.get("callee_range"),
                    "language": args.language,
                    "lsp_server": output["lsp_server"],
                    "lsp_resolver": resolver_name or None,
                    "definitions": evidence_definitions,
                })
            maybe_progress(call_index)

        pending: dict[int, tuple[int, dict, float]] = {}
        request_concurrency = max(args.request_concurrency, 1)
        next_call = 0
        stop = False
        while (next_call < len(calls) or pending) and not stop:
            while next_call < len(calls) and len(pending) < request_concurrency and not stop:
                call_index = next_call + 1
                call = calls[next_call]
                next_call += 1
                prepared = enqueue_definition_request(call_index, call)
                if prepared is None:
                    continue
                request_id, prepared_index, prepared_call, deadline = prepared
                pending[request_id] = (prepared_index, prepared_call, deadline)

            if not pending:
                continue

            now = time.monotonic()
            nearest_deadline = min(deadline for _idx, _call, deadline in pending.values())
            timeout = max(nearest_deadline - now, 0.001)
            try:
                message = client.read_protocol_message(timeout=timeout)
            except TimeoutError:
                now = time.monotonic()
                expired = [
                    request_id for request_id, (_idx, _call, deadline) in pending.items()
                    if deadline <= now
                ]
                for request_id in expired:
                    call_index, call, _deadline = pending.pop(request_id)
                    stop = record_definition_error(call, TimeoutError("textDocument/definition timed out"))
                    maybe_progress(call_index)
                    if stop:
                        break
                continue

            request_id = message.get("id")
            if request_id not in pending:
                continue
            call_index, call, _deadline = pending.pop(request_id)
            if "error" in message:
                stop = record_definition_error(call, RuntimeError(f"textDocument/definition: {message['error']}"))
                maybe_progress(call_index)
                continue
            handle_definition_result(call_index, call, message.get("result"))
        output["metadata"]["mapped_edges"] = len(output["edges"])
        output["metadata"]["evidence_records"] = len(output.get("lsp_evidence", []))
    finally:
        client.close()
        output["metadata"]["server_returncode"] = client.proc.poll()
        output["metadata"]["server_stderr_tail"] = [
            sanitize_text(line, root) for line in client.stderr_tail()
        ]

    written = write_output(enrichment_dir, args.language, output)
    progress_snapshot(progress_label, output, index=processed_calls, total=len(calls), started_at=started_at)
    progress(f"{progress_label}: wrote {rel_path(written, root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

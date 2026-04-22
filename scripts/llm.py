"""Direct LLM backend for semantic extraction.

Bypasses the Claude Code Agent tool and calls any OpenAI-compatible API directly.
Supports Kimi (Moonshot AI), OpenAI, and Anthropic (via openai-compat proxy).

Usage:
    from graphify.llm import extract_files_direct

    result = extract_files_direct(
        files=[Path("docs/design.md"), Path("src/auth.py")],
        backend="kimi",
        api_key="sk-...",
    )
    # result: {"nodes": [...], "edges": [...], "hyperedges": [...],
    #           "input_tokens": N, "output_tokens": N}
"""
from __future__ import annotations

import json
import time
from pathlib import Path


# ── Backend configs ────────────────────────────────────────────────────────────

BACKENDS: dict[str, dict] = {
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "default_model": "kimi-k2.5",  # 256K context, vision + reasoning
        "context_window": 256_000,
        # Kimi k2.5 pricing (approximate USD — verify at platform.moonshot.ai):
        "input_cost_per_1k": 0.0006,
        "output_cost_per_1k": 0.0028,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "context_window": 128_000,
        "input_cost_per_1k": 0.0025,
        "output_cost_per_1k": 0.01,
    },
    "claude": {
        # Claude via official Anthropic SDK (different interface, handled separately)
        "base_url": None,
        "default_model": "claude-sonnet-4-6",
        "context_window": 200_000,
        "input_cost_per_1k": 0.003,
        "output_cost_per_1k": 0.015,
    },
}

# ── Extraction prompt ──────────────────────────────────────────────────────────

_FEW_SHOT_EXAMPLE = """
Example input:
=== FILE: auth/login.py ===
from db import UserDB
def login(username, password):
    user = UserDB.find(username)
    if user and user.check_password(password):
        return generate_token(user)

Example output:
{"nodes":[{"id":"login_login","label":"login","file_type":"code","source_file":"auth/login.py","source_location":null,"source_url":null,"captured_at":null,"author":null,"contributor":null},{"id":"login_userdb","label":"UserDB","file_type":"code","source_file":"auth/login.py","source_location":null,"source_url":null,"captured_at":null,"author":null,"contributor":null}],"edges":[{"source":"login_login","target":"login_userdb","relation":"calls","confidence":"EXTRACTED","confidence_score":1.0,"source_file":"auth/login.py","source_location":null,"weight":1.0}],"hyperedges":[],"input_tokens":0,"output_tokens":0}

Now extract from the files below using the same schema:
"""

_SYSTEM_PROMPT = """You are a graphify extraction agent. Your task: read the file contents and extract a knowledge graph as JSON.
Output ONLY valid JSON — no explanation, no markdown fences, no preamble, no trailing text after the closing brace.

Rules:
- EXTRACTED: relationship explicit in source (import, call, citation, "see §3.2")
- INFERRED: reasonable inference (shared data structure, implied dependency)
- AMBIGUOUS: uncertain - flag for review, do not omit

Code files: focus on semantic edges AST cannot find (call relationships, shared data, arch patterns).
  Do not re-extract imports - AST already has those.
Doc/paper files: extract named concepts, entities, citations. Also extract rationale — sections that explain WHY a decision was made, trade-offs chosen, or design intent. These become nodes with `rationale_for` edges pointing to the concept they explain.
Image files: use vision to understand what the image IS - do not just OCR.
  UI screenshot: layout patterns, design decisions, key elements, purpose.
  Chart: metric, trend/insight, data source.
  Tweet/post: claim as node, author, concepts mentioned.
  Diagram: components and connections.
  Research figure: what it demonstrates, method, result.
  Handwritten/whiteboard: ideas and arrows, mark uncertain readings AMBIGUOUS.

Semantic similarity: if two concepts in this chunk solve the same problem or represent the same idea without any structural link (no import, no call, no citation), add a `semantically_similar_to` edge marked INFERRED with a confidence_score reflecting how similar they are (0.6-0.95). Only add these when the similarity is genuinely non-obvious and cross-cutting.

Hyperedges: if 3 or more nodes clearly participate together in a shared concept, flow, or pattern that is not captured by pairwise edges alone, add a hyperedge to a top-level `hyperedges` array. Use sparingly — maximum 3 hyperedges per chunk.

If a file has YAML frontmatter (--- ... ---), copy source_url, captured_at, author, contributor onto every node from that file.

confidence_score is REQUIRED on every edge:
- EXTRACTED edges: confidence_score must be 1.0
- INFERRED edges: score 0.4-0.9 based on how certain you are. Strong structural inference: 0.8-0.9. Reasonable but not certain: 0.6-0.7. Weak: 0.4-0.5.
- AMBIGUOUS edges: score 0.1-0.3

Output exactly this JSON (no other text):
{"nodes":[{"id":"filestem_entityname","label":"Human Readable Name","file_type":"code|document|paper|image","source_file":"relative/path","source_location":null,"source_url":null,"captured_at":null,"author":null,"contributor":null}],"edges":[{"source":"node_id","target":"node_id","relation":"calls|implements|references|cites|conceptually_related_to|shares_data_with|semantically_similar_to|rationale_for","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","confidence_score":1.0,"source_file":"relative/path","source_location":null,"weight":1.0}],"hyperedges":[{"id":"snake_case_id","label":"Human Readable Label","nodes":["node_id1","node_id2","node_id3"],"relation":"participate_in|implement|form","confidence":"EXTRACTED|INFERRED","confidence_score":0.75,"source_file":"relative/path"}],"input_tokens":0,"output_tokens":0}"""


def _build_user_message(files: list[Path], root: Path | None = None) -> str:
    """Read files and build the user message for extraction."""
    parts = []
    for f in files:
        try:
            rel = f.relative_to(root) if root else f
        except ValueError:
            rel = f
        try:
            # Skip binary files (PDFs, images handled separately via vision)
            if f.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
                parts.append(f"=== FILE: {rel} ===\n[Binary file — skipped in text extraction]")
                continue
            content = f.read_text(encoding="utf-8", errors="replace")
            # Truncate very large files — LLM has context limits even at 128K
            if len(content) > 80_000:
                content = content[:80_000] + f"\n... [truncated at 80K chars]"
            parts.append(f"=== FILE: {rel} ===\n{content}")
        except OSError as exc:
            parts.append(f"=== FILE: {rel} ===\n[Could not read: {exc}]")
    return "\n\n".join(parts)


def _parse_response(text: str) -> dict:
    """Extract JSON from LLM response, tolerating markdown fences."""
    text = text.strip()
    # Strip ```json fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
        inner = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        text = "\n".join(inner).strip()
    return json.loads(text)


# ── OpenAI-compatible backends (Kimi, OpenAI) ─────────────────────────────────

def _extract_openai_compat(
    files: list[Path],
    backend_cfg: dict,
    api_key: str,
    model: str,
    root: Path | None,
) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package required: pip install openai")

    timeout = 2400 if "k2.6" in model else 120
    client = OpenAI(api_key=api_key, base_url=backend_cfg["base_url"], timeout=timeout)
    user_msg = _build_user_message(files, root)

    t0 = time.time()
    # kimi-k2.x reasoning models only accept temperature=1
    temperature = 1 if "k2" in model else 0.1
    # Prepend few-shot example to user message for reasoning models
    full_user_msg = (_FEW_SHOT_EXAMPLE + user_msg) if "k2" in model else user_msg
    # K2.6 does not support response_format=json_object — it handles JSON via prompt
    use_json_format = "k2.6" not in model
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": full_user_msg},
        ],
        temperature=temperature,
        max_tokens=32768 if "k2.6" in model else 16384,
    )
    if use_json_format:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    elapsed = time.time() - t0

    msg = response.choices[0].message
    raw = msg.content or ""

    # Reasoning models (kimi-k2.5) may put the answer in reasoning_content
    # and leave content empty — fall back to it
    if not raw.strip():
        raw = getattr(msg, "reasoning_content", "") or ""

    # Some providers wrap JSON in a finish_reason=stop with content in tool_calls
    if not raw.strip() and response.choices[0].finish_reason:
        import pprint
        raise ValueError(
            f"Empty response from model.\n"
            f"finish_reason={response.choices[0].finish_reason!r}\n"
            f"message fields: {[k for k in vars(msg) if getattr(msg, k)]}"
        )

    usage = response.usage

    try:
        result = _parse_response(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Backend returned invalid JSON: {exc}\nRaw response (first 500 chars):\n{raw[:500]}")

    result["input_tokens"] = usage.prompt_tokens if usage else 0
    result["output_tokens"] = usage.completion_tokens if usage else 0
    result["elapsed_seconds"] = round(elapsed, 2)
    result["model"] = model
    result["backend"] = backend_cfg.get("base_url", "unknown")
    return result


# ── Claude via claude CLI (no API key needed inside Claude Code) ───────────────

def _extract_claude(
    files: list[Path],
    api_key: str | None,
    model: str,
    root: Path | None,
) -> dict:
    """Extract using claude CLI subprocess — works inside Claude Code without an API key."""
    import subprocess
    import tempfile

    user_msg = _build_user_message(files, root)
    prompt = _SYSTEM_PROMPT + "\n\n" + user_msg

    t0 = time.time()
    # Pass prompt via stdin to avoid OS arg length limits
    proc = subprocess.run(
        ["claude", "-p", "-", "--model", model, "--output-format", "text"],
        input=prompt,
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    raw = proc.stdout.strip()
    if proc.returncode != 0 and not raw:
        raise RuntimeError(f"claude CLI failed (exit {proc.returncode}): {proc.stderr[:300]}")

    elapsed = time.time() - t0

    try:
        result = _parse_response(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Backend returned invalid JSON: {exc}\nRaw response (first 500 chars):\n{raw[:500]}")

    # Estimate tokens (claude CLI doesn't return usage counts)
    result["input_tokens"] = len(prompt) // 4
    result["output_tokens"] = len(raw) // 4
    result["elapsed_seconds"] = round(elapsed, 2)
    result["model"] = model
    result["backend"] = "claude-cli"
    return result


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_files_direct(
    files: list[Path],
    backend: str,
    api_key: str,
    model: str | None = None,
    root: Path | None = None,
) -> dict:
    """Extract knowledge graph from files using a direct LLM API call.

    Args:
        files: list of file paths to extract from (one API call per batch)
        backend: "kimi", "openai", or "claude"
        api_key: API key for the backend
        model: override the default model for this backend
        root: project root for relative path display

    Returns:
        dict with nodes, edges, hyperedges, input_tokens, output_tokens,
        elapsed_seconds, model, backend
    """
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}. Choose from: {list(BACKENDS)}")

    cfg = BACKENDS[backend]
    chosen_model = model or cfg["default_model"]

    if backend == "claude":
        return _extract_claude(files, api_key, chosen_model, root)
    else:
        return _extract_openai_compat(files, cfg, api_key, chosen_model, root)


def estimate_cost(backend: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a completed extraction call."""
    cfg = BACKENDS.get(backend, {})
    input_cost = (input_tokens / 1000) * cfg.get("input_cost_per_1k", 0)
    output_cost = (output_tokens / 1000) * cfg.get("output_cost_per_1k", 0)
    return round(input_cost + output_cost, 6)


def _chunk_files(files: list[Path], chunk_size: int) -> list[list[Path]]:
    return [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg"}


def _split_into_chunks(files: list[Path], chunk_size: int = 22) -> list[list[Path]]:
    """Mirror graphify skill chunking: 20-25 files per chunk, images get their own chunk."""
    images = [f for f in files if f.suffix.lower() in _IMAGE_EXTENSIONS]
    non_images = [f for f in files if f.suffix.lower() not in _IMAGE_EXTENSIONS]
    chunks = _chunk_files(non_images, chunk_size)
    # Each image is its own chunk (vision needs isolated context)
    chunks += [[img] for img in images]
    return chunks


def extract_corpus_parallel(
    files: list[Path],
    backend: str,
    api_key: str,
    model: str | None = None,
    root: Path | None = None,
    chunk_size: int = 22,
    max_workers: int = 5,
    on_chunk_done: "callable | None" = None,
) -> dict:
    """Extract a full corpus in parallel — mirrors graphify's multi-subagent dispatch.

    Splits files into chunks of 20-25 (images solo), fires all chunks simultaneously
    via ThreadPoolExecutor (max_workers parallel API calls), then merges results.

    Args:
        files: all files to extract from
        backend: "kimi", "openai", or "claude"
        api_key: API key for the backend
        model: override default model
        root: project root for relative path display
        chunk_size: non-image files per API call (default 22, matching graphify skill)
        max_workers: max parallel API calls (default 5)
        on_chunk_done: optional callback(chunk_idx, total, result) for progress reporting

    Returns:
        merged dict with nodes, edges, hyperedges, input_tokens, output_tokens
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    chunks = _split_into_chunks(files, chunk_size)
    total = len(chunks)

    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    all_hyperedges: list[dict] = []
    total_input = 0
    total_output = 0
    failed = 0

    def _call(idx_chunk: tuple[int, list[Path]]) -> tuple[int, dict | Exception]:
        idx, chunk = idx_chunk
        try:
            result = extract_files_direct(chunk, backend, api_key, model, root)
            return idx, result
        except Exception as exc:
            return idx, exc

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_call, (i, chunk)): i for i, chunk in enumerate(chunks)}
        for future in as_completed(futures):
            idx, result = future.result()
            if isinstance(result, Exception):
                print(f"  [chunk {idx+1}/{total}] FAILED: {result}", flush=True)
                failed += 1
            else:
                # Deduplicate nodes by id
                seen = {n["id"] for n in all_nodes}
                for n in result.get("nodes", []):
                    if n["id"] not in seen:
                        all_nodes.append(n)
                        seen.add(n["id"])
                all_edges.extend(result.get("edges", []))
                all_hyperedges.extend(result.get("hyperedges", []))
                total_input += result.get("input_tokens", 0)
                total_output += result.get("output_tokens", 0)
                if on_chunk_done:
                    on_chunk_done(idx, total, result)

    if failed > total // 2:
        raise RuntimeError(f"More than half the chunks failed ({failed}/{total}). Aborting.")

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "hyperedges": all_hyperedges,
        "input_tokens": total_input,
        "output_tokens": total_output,
        "chunks_total": total,
        "chunks_failed": failed,
    }

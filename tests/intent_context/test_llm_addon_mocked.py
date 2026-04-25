"""LLM add-on path with OpenAIProvider mocked."""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from depos.analysis.config import IntelligenceConfig
from depos.intent_context.build import run_intent_context_build
from depos.intent_context.json_util import parse_json_object, strip_llm_json


def test_strip_llm_json_fenced() -> None:
    raw = '```json\n{"units": []}\n```'
    assert '"units"' in strip_llm_json(raw)


def test_parse_json_object() -> None:
    d = parse_json_object('  {"a": 1}  ')
    assert d["a"] == 1


@patch("depos.intent_context.build.summarize_repo")
@patch("depos.intent_context.build.summarize_files")
@patch("depos.intent_context.llm_v0.OpenAIProvider")
def test_build_llm_addon_skips_network_when_mocked(
    mock_provider_cls,
    mock_summarize_files,
    mock_summarize_repo,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parent / "fixtures" / "minimal_repo"
    cfg = IntelligenceConfig()
    cfg.reasoner.openai_api_key = "test-key-not-used-on-network-if-mock-works"
    cfg.intent_context.llm_mode = "auto"

    mock_summarize_files.return_value = ([], 0, 0, 0)
    mock_summarize_repo.return_value = (None, 0, 0, 0)

    mock_inst = MagicMock()

    def _complete(prompt: str, *, max_tokens: int = 1000):
        if "CHUNKS_JSON" in prompt:
            m = re.search(r'"chunk_id"\s*:\s*"([^"]+)"', prompt)
            cid = m.group(1) if m else "unknown"
            body = {
                "units": [
                    {
                        "unit_id": "llm-u-1",
                        "kind": "invariant",
                        "natural_language": "Mocked LLM claim.",
                        "scope_hints": ["auth"],
                        "evidence": [{"chunk_id": cid, "start_line": 1, "end_line": 2}],
                        "confidence": 0.9,
                    }
                ]
            }
            return json.dumps(body), {"model": "mock"}
        return json.dumps({"units": []}), {"model": "mock"}

    mock_inst.complete.side_effect = _complete
    mock_provider_cls.return_value = mock_inst

    out = tmp_path / "out"
    assert run_intent_context_build(repo, out, cfg) == 0

    manifest = json.loads((out / "intent_manifest.json").read_text(encoding="utf-8"))
    assert manifest["llm_enabled"] is True
    units = json.loads((out / "intent_units.json").read_text(encoding="utf-8"))
    extractors = {u.get("extractor") for u in units}
    assert "rules_v0" in extractors
    assert "llm_v0" in extractors

"""Tests for LLM JSON parsing robustness.

Validates the retry + repair + artifact-save behavior of call_llm_json
and the _try_parse_json helper.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from codegate.llm import _save_malformed_response, _try_parse_json, call_llm_json

# ---------------------------------------------------------------------------
# _try_parse_json unit tests
# ---------------------------------------------------------------------------


class TestTryParseJson:
    """Test the JSON repair helper."""

    def test_valid_json_object(self):
        result = _try_parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_valid_json_array(self):
        result = _try_parse_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_json_with_leading_text(self):
        result = _try_parse_json('Here is the result: {"key": "value"}')
        assert result == {"key": "value"}

    def test_json_with_trailing_text(self):
        result = _try_parse_json('{"key": "value"} end of response')
        assert result == {"key": "value"}

    def test_json_array_with_surrounding_text(self):
        result = _try_parse_json('Result: [{"a": 1}] done')
        assert result == [{"a": 1}]

    def test_pure_array_extraction(self):
        # Array extraction works when no standalone {} is found
        result = _try_parse_json('Result: [1, 2, 3] done')
        assert result == [1, 2, 3]

    def test_completely_invalid(self):
        result = _try_parse_json("This is not JSON at all")
        assert result is None

    def test_empty_string(self):
        result = _try_parse_json("")
        assert result is None

    def test_nested_json(self):
        text = '{"findings": [{"msg": "test"}], "count": 1}'
        result = _try_parse_json(text)
        assert result["count"] == 1
        assert len(result["findings"]) == 1

    def test_json_with_unicode(self):
        result = _try_parse_json('{"message": "写作工作台"}')
        assert result == {"message": "写作工作台"}

    def test_malformed_json_no_repair(self):
        # Missing closing brace — repair should fail
        result = _try_parse_json('{"key": "value"')
        assert result is None

    def test_json_object_preferred_over_array(self):
        # Object is the outermost JSON block here, so it should win.
        text = '{"items": [1, 2, 3]}'
        result = _try_parse_json(text)
        assert isinstance(result, dict)

    def test_earliest_outer_json_block_wins(self):
        assert _try_parse_json('prefix [1, {"a": 2}] suffix') == [1, {"a": 2}]
        assert _try_parse_json('prefix {"items": [1, 2]} suffix') == {
            "items": [1, 2]
        }


# ---------------------------------------------------------------------------
# _save_malformed_response tests
# ---------------------------------------------------------------------------


class TestSaveMalformedResponse:
    """Test artifact saving for malformed responses."""

    def test_saves_to_file(self, tmp_path: Path):
        with patch("codegate.config.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.store_dir = str(tmp_path)
            mock_config.return_value = mock_cfg

            result = _save_malformed_response(
                raw="not json", context="test"
            )

            assert result is not None
            assert result.exists()
            data = json.loads(result.read_text())
            assert data["raw_response"] == "not json"
            assert data["context"] == "test"
            assert data["raw_response_length"] == 8

    def test_truncates_large_response(self, tmp_path: Path):
        with patch("codegate.config.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.store_dir = str(tmp_path)
            mock_config.return_value = mock_cfg

            large_raw = "x" * 20000
            result = _save_malformed_response(raw=large_raw)

            assert result is not None
            data = json.loads(result.read_text())
            assert len(data["raw_response"]) == 10000
            assert data["raw_response_length"] == 20000

    def test_handles_config_failure_gracefully(self, tmp_path: Path, monkeypatch):
        # When get_config fails, should fallback to ./artifacts
        monkeypatch.chdir(tmp_path)
        with patch("codegate.config.get_config", side_effect=RuntimeError("no config")):
            result = _save_malformed_response(raw="test")
            assert result is not None
            assert "artifacts" in str(result)


# ---------------------------------------------------------------------------
# call_llm_json integration tests (mocked LLM)
# ---------------------------------------------------------------------------


class TestCallLlmJsonRetry:
    """Test call_llm_json retry behavior."""

    @patch("codegate.llm.call_llm")
    def test_first_attempt_success(self, mock_call):
        mock_call.return_value = ('{"result": "ok"}', 100)

        parsed, tokens = call_llm_json(
            model="test-model",
            system_prompt="test",
            user_message="test",
        )

        assert parsed == {"result": "ok"}
        assert tokens == 100
        assert mock_call.call_count == 1

    @patch("codegate.llm.call_llm")
    def test_code_fence_stripped(self, mock_call):
        mock_call.return_value = ('```json\n{"result": "ok"}\n```', 100)

        parsed, tokens = call_llm_json(
            model="test-model",
            system_prompt="test",
            user_message="test",
        )

        assert parsed == {"result": "ok"}
        assert tokens == 100

    @patch("codegate.llm._save_malformed_response", return_value=Path("/fake/path"))
    @patch("codegate.llm.call_llm")
    def test_retry_on_parse_failure(self, mock_call, mock_save):
        # First call returns invalid JSON, second returns valid
        mock_call.side_effect = [
            ("not json at all", 50),
            ('{"result": "retry_ok"}', 75),
        ]

        parsed, tokens = call_llm_json(
            model="test-model",
            system_prompt="test",
            user_message="test",
        )

        assert parsed == {"result": "retry_ok"}
        assert tokens == 125  # 50 + 75
        assert mock_call.call_count == 2
        assert mock_save.call_count == 1

    @patch("codegate.llm._save_malformed_response", return_value=Path("/fake/path"))
    @patch("codegate.llm.call_llm")
    def test_raises_after_both_attempts_fail(self, mock_call, mock_save):
        mock_call.side_effect = [
            ("invalid json 1", 50),
            ("invalid json 2", 75),
        ]

        with pytest.raises(ValueError, match="Could not parse JSON"):
            call_llm_json(
                model="test-model",
                system_prompt="test",
                user_message="test",
            )

        assert mock_call.call_count == 2
        assert mock_save.call_count == 2  # saved both attempts

    @patch("codegate.llm.call_llm")
    def test_repair_extracts_json_from_text(self, mock_call):
        mock_call.return_value = (
            'Here is my analysis:\n{"decision": "approve", "score": 95}\nEnd.',
            100,
        )

        parsed, tokens = call_llm_json(
            model="test-model",
            system_prompt="test",
            user_message="test",
        )

        assert parsed == {"decision": "approve", "score": 95}

    @patch("codegate.llm.call_llm")
    def test_array_response(self, mock_call):
        mock_call.return_value = ('[{"id": 1}, {"id": 2}]', 100)

        parsed, tokens = call_llm_json(
            model="test-model",
            system_prompt="test",
            user_message="test",
        )

        assert isinstance(parsed, list)
        assert len(parsed) == 2

    @patch("codegate.llm.call_llm")
    def test_unicode_json(self, mock_call):
        mock_call.return_value = ('{"message": "安全验证通过"}', 100)

        parsed, tokens = call_llm_json(
            model="test-model",
            system_prompt="test",
            user_message="test",
        )

        assert parsed["message"] == "安全验证通过"

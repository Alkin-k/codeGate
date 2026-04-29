"""Deterministic baseline-diff behavior tests."""

from __future__ import annotations

import codegate.analysis.baseline_diff as baseline_diff
import codegate.config as codegate_config


def test_compute_baseline_diff_uses_deterministic_extractor_by_default(
    monkeypatch,
) -> None:
    """Default runs must not call the LLM extractor."""
    monkeypatch.delenv("CODEGATE_EXTRACT_MODEL", raising=False)
    codegate_config._config = None

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM extractor should not run without CODEGATE_EXTRACT_MODEL")

    monkeypatch.setattr(baseline_diff, "call_llm_json", fail_if_called)

    result = baseline_diff.compute_baseline_diff(
        {
            "ConvertController.java": (
                "public class ConvertController {\n"
                "    public void convert(@Min(72) Integer dpi) {}\n"
                "}\n"
            )
        },
        {
            "ConvertController.java": (
                "public class ConvertController {\n"
                "    public void convert(Integer dpi) {}\n"
                "}\n"
            )
        },
    )

    removed = {(p.pattern, p.kind) for p in result.removed_from_baseline}
    assert ("@Min(72)", "annotation") in removed


def test_compute_baseline_diff_preserves_moved_method_signature(
    monkeypatch,
) -> None:
    """Line movement should not count as removal when the signature remains."""
    monkeypatch.delenv("CODEGATE_EXTRACT_MODEL", raising=False)
    codegate_config._config = None

    result = baseline_diff.compute_baseline_diff(
        {
            "Service.java": (
                "public class Service {\n"
                "    public void keepMe() {}\n"
                "    public void other() {}\n"
                "}\n"
            )
        },
        {
            "Service.java": (
                "public class Service {\n"
                "    public void other() {}\n"
                "    // moved below\n"
                "    public void keepMe() {}\n"
                "}\n"
            )
        },
    )

    removed = {(p.pattern, p.kind) for p in result.removed_from_baseline}
    preserved = {(p.pattern, p.kind) for p in result.unchanged_baseline}

    assert ("public void keepMe(...)", "method_signature") not in removed
    assert ("public void keepMe(...)", "method_signature") in preserved

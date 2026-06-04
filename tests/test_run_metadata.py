"""RunMetadata / run_id tests — Phase 1 of v0.7 Governance Contract Runtime."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codegate.schemas.run import (
    RunArtifactBundle,
    RunMetadata,
    generate_run_id,
)

RUN_ID_RE = re.compile(r"^run_\d{8}_\d{6}_[0-9a-f]{1,6}_[0-9a-f]{6}$")


class TestGenerateRunId:
    def test_format(self):
        run_id = generate_run_id("abcdef123456")
        assert RUN_ID_RE.match(run_id), run_id

    def test_not_equal_to_work_item_id(self):
        wid = "abcdef123456"
        run_id = generate_run_id(wid)
        assert run_id != wid
        assert wid[:6] in run_id  # shortid embedded

    def test_handles_missing_work_item_id(self):
        run_id = generate_run_id(None)
        assert RUN_ID_RE.match(run_id), run_id

    def test_unique_within_same_second(self):
        # Same work item, generated back-to-back: the random suffix must keep
        # the ids distinct even when the second-resolution timestamp matches.
        wid = "abcdef123456"
        ids = {generate_run_id(wid) for _ in range(50)}
        assert len(ids) == 50


class TestRunMetadata:
    def test_defaults(self):
        md = RunMetadata(run_id="run_x", work_item_id="wi1")
        assert md.status == "completed"
        assert md.completed_at is None
        assert md.executor_name is None
        assert md.started_at  # auto-populated ISO string

    def test_json_roundtrip(self):
        md = RunMetadata(
            run_id="run_20260604_120000_abcdef",
            work_item_id="abcdef123456",
            codegate_version="0.7.0",
            completed_at="2026-06-04T12:01:00+00:00",
            project_dir="/tmp/project",
            executor_name="codex",
            sandbox_strategy="git_worktree",
            git_base_ref="deadbeef",
            git_head_ref="working",
            status="completed",
        )
        dumped = md.model_dump(mode="json")
        restored = RunMetadata(**dumped)
        assert restored == md

    def test_missing_optional_fields(self):
        # Only required fields supplied
        md = RunMetadata.model_validate({"run_id": "r", "work_item_id": "w"})
        assert md.project_dir is None
        assert md.git_base_ref is None


class TestRunArtifactBundle:
    def test_defaults(self):
        bundle = RunArtifactBundle(run_id="r", run_dir="/tmp/r")
        assert bundle.metadata is None
        assert bundle.verdict is None
        assert bundle.review_history == []
        assert bundle.present == []
        assert bundle.missing == []
        assert bundle.completeness_score == 0.0

    def test_roundtrip(self):
        bundle = RunArtifactBundle(
            run_id="r",
            run_dir="/tmp/r",
            metadata=RunMetadata(run_id="r", work_item_id="w"),
            present=["verdict.json"],
            missing=["candidate.diff"],
            completeness_score=0.5,
        )
        restored = RunArtifactBundle(**bundle.model_dump(mode="json"))
        assert restored.run_id == "r"
        assert restored.metadata is not None
        assert restored.completeness_score == 0.5

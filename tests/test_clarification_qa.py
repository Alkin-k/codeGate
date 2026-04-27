"""Test that clarification Q&A is properly carried through the pipeline.

Two paths must work:
1. Interactive: questions + answers → "Clarification Q&A" section in prompt
2. Pre-provided: answers only (--answers / YAML) → "Pre-provided Clarification Answers" section
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow importing from src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_interactive_qa_in_contract_prompt():
    """Interactive path: questions + answers → Clarification Q&A section."""
    from codegate.workflow.state import GovernanceState
    from codegate.schemas.work_item import WorkItem
    from codegate.agents.spec_council import _build_contract_prompt

    state = GovernanceState(
        work_item=WorkItem(
            raw_request="Add file name validation to /api/convert",
            context="Spring Boot project",
        ),
        clarification_questions=[
            "[必答] Which characters are illegal in filenames?",
            "[可选] What error code should be used?",
        ],
        clarification_answers=[
            "Characters .. and /",
            "INVALID_FILENAME",
        ],
        clarification_round=1,
        clarification_mode="interactive",
    )

    prompt = _build_contract_prompt(state)

    # Must contain Q&A section (not fallback)
    assert "Clarification Q&A" in prompt, "Interactive path must use Q&A section"
    assert "Pre-provided" not in prompt, "Interactive path must NOT use pre-provided section"

    # Must contain questions
    assert "illegal in filenames" in prompt, "Must include question text"
    assert "error code" in prompt, "Must include second question"

    # Must contain answers
    assert "Characters .. and /" in prompt, "Must include first answer"
    assert "INVALID_FILENAME" in prompt, "Must include second answer"

    print("✅ test_interactive_qa_in_contract_prompt PASSED")


def test_pre_provided_answers_in_contract_prompt():
    """Pre-provided path: answers without questions → Pre-provided Clarification Answers section."""
    from codegate.workflow.state import GovernanceState
    from codegate.schemas.work_item import WorkItem
    from codegate.agents.spec_council import _build_contract_prompt

    state = GovernanceState(
        work_item=WorkItem(
            raw_request="Add file name validation",
        ),
        clarification_questions=[],  # No questions — this is the --answers / YAML path
        clarification_answers=[
            "抛出 IllegalArgumentException，由 GlobalExceptionHandler.handleBadRequest 统一处理。",
            "错误码 INVALID_FILENAME。",
        ],
        clarification_round=1,
        clarification_mode="pre_provided",
    )

    prompt = _build_contract_prompt(state)

    # Must contain pre-provided section (not Q&A)
    assert "Pre-provided Clarification Answers" in prompt, \
        "Pre-provided path must use Pre-provided section"
    assert "hard constraints" in prompt, \
        "Pre-provided section must tell LLM to treat as constraints"

    # Must NOT use Q&A format
    assert "Clarification Q&A" not in prompt, \
        "Pre-provided path must NOT use Q&A section (no questions to pair)"

    # Must contain the actual answers
    assert "IllegalArgumentException" in prompt, "Must include first answer"
    assert "INVALID_FILENAME" in prompt, "Must include second answer"

    print("✅ test_pre_provided_answers_in_contract_prompt PASSED")


def test_no_answers_no_section():
    """When neither questions nor answers exist, no clarification section appears."""
    from codegate.workflow.state import GovernanceState
    from codegate.schemas.work_item import WorkItem
    from codegate.agents.spec_council import _build_contract_prompt

    state = GovernanceState(
        work_item=WorkItem(raw_request="Simple requirement"),
        clarification_questions=[],
        clarification_answers=[],
        clarification_mode="none",
    )

    prompt = _build_contract_prompt(state)

    assert "Clarification" not in prompt, "No clarification section when no Q&A"

    print("✅ test_no_answers_no_section PASSED")


def test_state_carries_questions_through_pipeline_params():
    """Verify GovernanceState correctly holds all clarification fields."""
    from codegate.workflow.state import GovernanceState
    from codegate.schemas.work_item import WorkItem

    questions = ["Q1?", "Q2?"]
    answers = ["A1", "A2"]

    state = GovernanceState(
        work_item=WorkItem(raw_request="test"),
        clarification_questions=questions,
        clarification_answers=answers,
        clarification_mode="interactive",
    )

    assert state.clarification_questions == questions
    assert state.clarification_answers == answers
    assert state.clarification_mode == "interactive"

    print("✅ test_state_carries_questions_through_pipeline_params PASSED")


def test_clarification_mode_values():
    """Verify clarification_mode field accepts all expected values."""
    from codegate.workflow.state import GovernanceState
    from codegate.schemas.work_item import WorkItem

    for mode in ["none", "interactive", "pre_provided"]:
        state = GovernanceState(
            work_item=WorkItem(raw_request="test"),
            clarification_mode=mode,
        )
        assert state.clarification_mode == mode

    print("✅ test_clarification_mode_values PASSED")


if __name__ == "__main__":
    test_interactive_qa_in_contract_prompt()
    test_pre_provided_answers_in_contract_prompt()
    test_no_answers_no_section()
    test_state_carries_questions_through_pipeline_params()
    test_clarification_mode_values()
    print("\n🎉 All clarification tests passed!")

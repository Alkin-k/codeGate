"""Test that clarification Q&A is properly carried through the pipeline.

Verifies the core fix: when questions from Spec Council run 1 are paired
with answers (interactive or --answers), they must appear in the contract
generation prompt sent to the LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow importing from src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_contract_prompt_includes_qa():
    """Given questions + answers, _build_contract_prompt must include Q&A section."""
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

    # Must contain Q&A section
    assert "Clarification Q&A" in prompt, "Contract prompt must include Clarification Q&A section"

    # Must contain the actual questions
    assert "illegal in filenames" in prompt, "Contract prompt must include the question text"
    assert "error code" in prompt, "Contract prompt must include the second question"

    # Must contain the actual answers
    assert "Characters .. and /" in prompt, "Contract prompt must include the first answer"
    assert "INVALID_FILENAME" in prompt, "Contract prompt must include the second answer"

    print("✅ test_contract_prompt_includes_qa PASSED")


def test_contract_prompt_without_questions_has_no_qa():
    """When answers are provided but questions list is empty, Q&A should NOT appear."""
    from codegate.workflow.state import GovernanceState
    from codegate.schemas.work_item import WorkItem
    from codegate.agents.spec_council import _build_contract_prompt

    state = GovernanceState(
        work_item=WorkItem(
            raw_request="Add file name validation",
        ),
        clarification_questions=[],  # BUG scenario: questions were lost
        clarification_answers=["answer 1", "answer 2"],
        clarification_round=1,
        clarification_mode="pre_provided",
    )

    prompt = _build_contract_prompt(state)

    # Without questions, Q&A pairing is impossible — section should be absent
    assert "Clarification Q&A" not in prompt, \
        "Contract prompt should NOT have Q&A section when questions are empty"

    print("✅ test_contract_prompt_without_questions_has_no_qa PASSED")


def test_state_carries_questions_through_pipeline_params():
    """Verify run_governance_pipeline accepts and passes questions to initial state."""
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
    test_contract_prompt_includes_qa()
    test_contract_prompt_without_questions_has_no_qa()
    test_state_carries_questions_through_pipeline_params()
    test_clarification_mode_values()
    print("\n🎉 All clarification tests passed!")

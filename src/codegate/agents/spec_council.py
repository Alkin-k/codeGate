"""Spec Council Agent — requirement dissection, clarification, and contract generation.

This is the most critical node in the governance pipeline.
It implements the 4-layer questioning framework:
  Layer 1: Business intent (always ask)
  Layer 2: Business rules (always ask)
  Layer 3: Technical constraints (auto-infer from context)
  Layer 4: Edge cases (provide defaults, user confirms)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from codegate.config import get_config
from codegate.llm import call_llm_json, load_prompt
from codegate.schemas.contract import (
    AcceptanceCriterion,
    AssumedDefault,
    ImplementationContract,
    Risk,
)
from codegate.schemas.work_item import WorkflowStatus
from codegate.workflow.state import GovernanceState

logger = logging.getLogger(__name__)


def run_spec_council(state: GovernanceState) -> GovernanceState:
    """Run the Spec Council node.

    Depending on the current phase:
    - First call: Dissect requirements and ask clarification questions
    - With answers: Generate the Implementation Contract
    - With enough info: Finalize and self-challenge the contract
    """
    config = get_config()
    model = config.models.spec_model
    system_prompt = load_prompt("spec_council")
    system_prompt = system_prompt.replace("{max_rounds}", str(config.max_clarify_rounds))

    work_item = state.work_item

    # If answers are pre-provided, skip questioning → go straight to contract
    if state.clarification_answers and state.clarification_round == 0:
        state.clarification_round = 1  # Mark as having done clarification
        return _generate_contract(state, model, system_prompt)

    # If we already have enough clarification or hit max rounds, generate contract
    if (
        state.clarification_round > 0
        and state.clarification_answers
    ) or state.clarification_round >= config.max_clarify_rounds:
        return _generate_contract(state, model, system_prompt)

    # Otherwise, dissect and ask questions
    return _dissect_and_question(state, model, system_prompt)


def _dissect_and_question(
    state: GovernanceState, model: str, system_prompt: str
) -> GovernanceState:
    """Phase 1 & 2: Dissect the requirement and generate clarification questions."""

    user_message = _build_dissection_prompt(state)

    result, tokens = call_llm_json(
        model=model,
        system_prompt=system_prompt,
        user_message=user_message,
    )
    state.add_tokens("spec_council", tokens)

    # Extract questions from LLM response
    questions = result.get("questions", [])
    if isinstance(questions, list) and questions:
        # Separate blocking from optional
        blocking = [q for q in questions if isinstance(q, dict) and q.get("blocking", True)]
        optional = [q for q in questions if isinstance(q, dict) and not q.get("blocking", True)]

        # Flatten to string list for display
        all_questions = []
        for q in blocking:
            text = q.get("question", q) if isinstance(q, dict) else str(q)
            all_questions.append(f"[必答] {text}")
        for q in optional:
            text = q.get("question", q) if isinstance(q, dict) else str(q)
            all_questions.append(f"[可选] {text}")

        if not all_questions:
            # If questions are plain strings
            all_questions = [str(q) for q in questions]

        state.clarification_questions = all_questions
        state.clarification_round += 1
        state.work_item.transition_to(WorkflowStatus.SPEC_REVIEW)
    else:
        # No questions needed — go straight to contract generation
        return _generate_contract(state, model, system_prompt)

    return state


def _generate_contract(
    state: GovernanceState, model: str, system_prompt: str
) -> GovernanceState:
    """Phase 3 & 4: Generate the Implementation Contract with self-challenge."""

    user_message = _build_contract_prompt(state)

    result, tokens = call_llm_json(
        model=model,
        system_prompt=system_prompt,
        user_message=user_message,
    )
    state.add_tokens("spec_council", tokens)

    try:
        contract = _parse_contract(result, state.work_item.id)
        contract.clarification_rounds = state.clarification_round
        contract.approve()  # Auto-approve for MVP (human approval is V2)
        state.contract = contract
        state.work_item.transition_to(WorkflowStatus.SPEC_APPROVED)
        logger.info(f"Contract generated and approved: {len(contract.goals)} goals, "
                     f"{len(contract.acceptance_criteria)} criteria")
    except Exception as e:
        logger.error(f"Failed to parse contract: {e}")
        state.error = f"Contract parsing failed: {e}"

    return state


def _build_dissection_prompt(state: GovernanceState) -> str:
    """Build the user message for requirement dissection."""
    parts = [
        "## User Requirement\n",
        f"```\n{state.work_item.raw_request}\n```\n",
    ]

    if state.work_item.context:
        parts.append(f"## Project Context\n\n{state.work_item.context}\n")

    if state.work_item.constraints:
        parts.append("## User-Specified Constraints\n")
        for c in state.work_item.constraints:
            parts.append(f"- {c}")
        parts.append("")

    parts.append(
        "## Your Task\n\n"
        "1. Dissect this requirement into atomic intents.\n"
        "2. Identify what is clear, ambiguous, or missing.\n"
        "3. List hidden assumptions.\n"
        "4. Generate clarification questions.\n\n"
        "Respond with JSON:\n"
        "```json\n"
        "{\n"
        '  "intents": [\n'
        '    {"intent": "...", "clarity": "clear|ambiguous|missing", '
        '"hidden_assumptions": ["..."], "questions": [{"question": "...", "blocking": true}]}\n'
        "  ],\n"
        '  "questions": [\n'
        '    {"question": "...", "blocking": true}\n'
        "  ],\n"
        '  "risk_assessment": "low|medium|high"\n'
        "}\n"
        "```"
    )

    return "\n".join(parts)


def _build_contract_prompt(state: GovernanceState) -> str:
    """Build the user message for contract generation."""
    parts = [
        "## Original Requirement\n",
        f"```\n{state.work_item.raw_request}\n```\n",
    ]

    if state.work_item.context:
        parts.append(f"## Project Context\n\n{state.work_item.context}\n")

    if state.clarification_questions and state.clarification_answers:
        parts.append("## Clarification Q&A\n")
        for q, a in zip(state.clarification_questions, state.clarification_answers):
            parts.append(f"**Q:** {q}")
            parts.append(f"**A:** {a}\n")

    parts.append(
        "## Your Task\n\n"
        "Generate a complete ImplementationContract based on all information above.\n\n"
        "IMPORTANT:\n"
        "- goals: specific and verifiable (minimum 1)\n"
        "- non_goals: what NOT to do (minimum 1)\n"
        "- acceptance_criteria: each must have 'description', 'verification', 'priority'\n"
        "- assumed_defaults: track every decision the user didn't explicitly make\n\n"
        "After generating, do Phase 4 (Self-Challenge):\n"
        "- Can any goal be trivially satisfied without real value?\n"
        "- Can any criterion be gamed?\n"
        "- If yes, revise before outputting.\n\n"
        "Respond with JSON matching ImplementationContract schema:\n"
        "```json\n"
        "{\n"
        '  "goals": ["..."],\n'
        '  "non_goals": ["..."],\n'
        '  "acceptance_criteria": [{"description": "...", "verification": "...", "priority": "must"}],\n'
        '  "constraints": ["..."],\n'
        '  "risks": [{"description": "...", "probability": "low", "impact": "medium", "mitigation": "..."}],\n'
        '  "required_tests": ["..."],\n'
        '  "rollback_conditions": ["..."],\n'
        '  "assumed_defaults": [{"topic": "...", "assumed_value": "...", "reason": "..."}]\n'
        "}\n"
        "```"
    )

    return "\n".join(parts)


def _parse_contract(data: dict, work_item_id: str) -> ImplementationContract:
    """Parse LLM output into an ImplementationContract, with graceful fallbacks."""
    # Parse acceptance criteria
    criteria = []
    for ac in data.get("acceptance_criteria", []):
        if isinstance(ac, dict):
            criteria.append(AcceptanceCriterion(
                description=ac.get("description", ""),
                verification=ac.get("verification", "manual review"),
                priority=ac.get("priority", "must"),
            ))
        elif isinstance(ac, str):
            criteria.append(AcceptanceCriterion(
                description=ac, verification="manual review", priority="must"
            ))

    # Parse risks
    risks = []
    for r in data.get("risks", []):
        if isinstance(r, dict):
            risks.append(Risk(
                description=r.get("description", ""),
                probability=r.get("probability", "medium"),
                impact=r.get("impact", "medium"),
                mitigation=r.get("mitigation", "TBD"),
            ))

    # Parse assumed defaults
    defaults = []
    for d in data.get("assumed_defaults", []):
        if isinstance(d, dict):
            defaults.append(AssumedDefault(
                topic=d.get("topic", ""),
                assumed_value=d.get("assumed_value", ""),
                reason=d.get("reason", ""),
            ))

    return ImplementationContract(
        work_item_id=work_item_id,
        goals=data.get("goals", ["Implement the requested feature"]),
        non_goals=data.get("non_goals", ["No non-goals specified"]),
        acceptance_criteria=criteria or [AcceptanceCriterion(
            description="Feature works as described",
            verification="manual testing",
            priority="must",
        )],
        constraints=data.get("constraints", []),
        risks=risks,
        required_tests=data.get("required_tests", []),
        rollback_conditions=data.get("rollback_conditions", []),
        assumed_defaults=defaults,
    )

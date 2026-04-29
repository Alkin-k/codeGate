"""Policy engine validation-result enforcement tests."""

from __future__ import annotations

from codegate.policies.engine import evaluate_policies
from codegate.schemas.execution import ExecutionReport, ValidationResult
from codegate.schemas.gate import GateDecision
from codegate.schemas.work_item import WorkItem
from codegate.workflow.state import GovernanceState


def _state_with_validation(validation_result: ValidationResult) -> GovernanceState:
    work_item = WorkItem(raw_request="validation policy test")
    return GovernanceState(
        work_item=work_item,
        execution_report=ExecutionReport(
            work_item_id=work_item.id,
            code_output="implementation",
            validation_result=validation_result,
        ),
        gate_decision=GateDecision(
            work_item_id=work_item.id,
            decision="approve",
            drift_score=0,
            coverage_score=100,
        ),
    )


def test_missing_npm_test_script_is_warning_only() -> None:
    result = evaluate_policies(
        _state_with_validation(
            ValidationResult(
                type="npm",
                command="npm test",
                exit_code=1,
                passed=False,
                tests_run=0,
                tests_failed=0,
                stdout_tail='npm error Missing script: "test"',
            )
        )
    )

    assert result.violations == []
    assert result.override_decision is None
    assert result.warnings
    assert "no test script configured" in result.warnings[0]


def test_dependency_failure_blocks_approval_even_with_zero_tests() -> None:
    result = evaluate_policies(
        _state_with_validation(
            ValidationResult(
                type="npm",
                command="npm test",
                exit_code=1,
                passed=False,
                tests_run=0,
                tests_failed=0,
                error_summary="Cannot find module vitest",
            )
        )
    )

    assert result.override_decision == "revise_code"
    assert result.violations
    assert "validation failed" in result.violations[0]


def test_gradle_no_tests_found_is_not_missing_script() -> None:
    result = evaluate_policies(
        _state_with_validation(
            ValidationResult(
                type="gradle",
                command="gradle test",
                exit_code=1,
                passed=False,
                tests_run=0,
                tests_failed=0,
                stdout_tail="No tests found for given includes",
            )
        )
    )

    assert result.override_decision == "revise_code"
    assert result.violations
    assert "validation failed" in result.violations[0]


def test_real_test_failure_blocks_approval() -> None:
    result = evaluate_policies(
        _state_with_validation(
            ValidationResult(
                type="npm",
                command="npm test",
                exit_code=1,
                passed=False,
                tests_run=12,
                tests_failed=1,
                error_summary="1 failed",
            )
        )
    )

    assert result.override_decision == "revise_code"
    assert result.violations
    assert "1/12 tests failed" in result.violations[0]

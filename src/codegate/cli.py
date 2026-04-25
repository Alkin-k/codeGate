"""CodeGate CLI — the main entry point for running governance workflows."""

from __future__ import annotations

import json
import logging
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich import print as rprint

from codegate.config import init_config, get_config

app = typer.Typer(
    name="codegate",
    help="🛡️ CodeGate — An approval and quality gate layer for AI coding workflows.",
    add_completion=False,
)
console = Console()


def setup_logging(level: str = "INFO"):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def run(
    request: str = typer.Option(..., "--input", "-i", help="The requirement to govern"),
    context: str = typer.Option("", "--context", "-c", help="Project context"),
    answers: str = typer.Option(
        "",
        "--answers",
        "-a",
        help="Pre-provided clarification answers (JSON array string)",
    ),
    executor: str = typer.Option(
        "builtin_llm",
        "--executor",
        "-e",
        help="Executor adapter: builtin_llm, opencode",
    ),
    executor_model: str = typer.Option(
        "",
        "--executor-model",
        help="Model for executor (e.g., kimi-for-coding/k2p6)",
    ),
    project_dir: str = typer.Option(
        "",
        "--project-dir",
        help="Project directory for real executors (opencode)",
    ),
    timeout: int = typer.Option(
        600,
        "--timeout",
        help="Executor timeout in seconds (default 600 for real projects)",
    ),
    env_file: str = typer.Option(".env", "--env", help="Path to .env file"),
    output: str = typer.Option("", "--output", "-o", help="Output directory for artifacts"),
):
    """Run the full governance pipeline for a requirement."""
    init_config(env_file)
    config = get_config()
    setup_logging(config.log_level)

    console.print(Panel.fit(
        f"[bold blue]🛡️ CodeGate Governance Pipeline[/bold blue]\n"
        f"[dim]Requirement:[/dim] {request[:100]}{'...' if len(request) > 100 else ''}\n"
        f"[dim]Executor:[/dim] {executor}",
        border_style="blue",
    ))

    # Configure executor adapter
    if executor == "opencode":
        from codegate.adapters.opencode import OpenCodeAdapter
        from codegate.agents.executor import set_executor_adapter
        adapter = OpenCodeAdapter(
            model=executor_model,
            timeout=timeout,
            project_dir=project_dir if project_dir else None,
        )
        set_executor_adapter(adapter)
        console.print(f"[green]Using opencode executor[/green] (model={executor_model or 'default'}, timeout={timeout}s)")

    # Parse pre-provided answers
    clarification_answers = []
    if answers:
        try:
            clarification_answers = json.loads(answers)
        except json.JSONDecodeError:
            clarification_answers = [a.strip() for a in answers.split("|")]

    # Import here to avoid circular imports and slow startup
    from codegate.workflow.graph import run_governance_pipeline
    from codegate.policies.engine import apply_policy_override
    from codegate.store.artifact_store import ArtifactStore

    with console.status("[bold green]Running governance pipeline..."):
        state = run_governance_pipeline(
            raw_request=request,
            context=context,
            constraints=[],
            clarification_answers=clarification_answers if clarification_answers else None,
        )

    # Check if we stopped for clarification
    if state.clarification_questions and not state.contract:
        console.print("\n[bold yellow]⚠️ Clarification Needed[/bold yellow]\n")
        for i, q in enumerate(state.clarification_questions, 1):
            console.print(f"  {i}. {q}")
        console.print(
            "\n[dim]Provide answers with --answers 'answer1|answer2|...' "
            "and re-run.[/dim]"
        )
        raise typer.Exit(0)

    # Apply policy override
    state = apply_policy_override(state)

    # Save artifacts
    store = ArtifactStore()
    if output:
        from pathlib import Path
        store = ArtifactStore(Path(output))
    run_dir = store.save_run(state)

    # Display results
    _display_results(state, run_dir)


@app.command()
def ab(
    project: str = typer.Option(..., "--project", "-p", help="Path to source project (will be copied)"),
    request: str = typer.Option(..., "--input", "-i", help="The requirement to evaluate"),
    model: str = typer.Option(..., "--model", "-m", help="Executor model (e.g., kimi-for-coding/k2p6)"),
    answers: str = typer.Option("", "--answers", "-a", help="Pre-provided clarification answers"),
    timeout: int = typer.Option(600, "--timeout", help="Executor timeout in seconds"),
    output: str = typer.Option("ab_results", "--output", "-o", help="Output directory for results"),
    build_cmd: str = typer.Option("mvn test -B", "--build-cmd", help="Build/test command"),
    case_name: str = typer.Option("", "--case-name", help="Human-readable case name"),
    env_file: str = typer.Option(".env", "--env", help="Path to .env file"),
):
    """Run an automated A/B comparison: pure executor vs CodeGate+executor."""
    init_config(env_file)
    config = get_config()
    setup_logging(config.log_level)

    console.print(Panel.fit(
        f"[bold blue]🔬 CodeGate A/B Evaluation[/bold blue]\n"
        f"[dim]Case:[/dim] {case_name or 'unnamed'}\n"
        f"[dim]Project:[/dim] {project}\n"
        f"[dim]Model:[/dim] {model}\n"
        f"[dim]Requirement:[/dim] {request[:80]}{'...' if len(request) > 80 else ''}",
        border_style="blue",
    ))

    from codegate.eval.ab_runner import run_ab

    with console.status("[bold green]Running A/B evaluation..."):
        result = run_ab(
            project_dir=project,
            request=request,
            model=model,
            answers=answers,
            timeout=timeout,
            output_dir=output,
            build_cmd=build_cmd,
            case_name=case_name,
        )

    # Display summary
    a = result.line_a
    b = result.line_b
    cg = b.get("codegate", {})

    table = Table(title="A/B Results", border_style="blue")
    table.add_column("Dimension", style="bold")
    table.add_column("Line A (Pure)")
    table.add_column("Line B (CodeGate)")

    table.add_row("Duration", f"{a.get('duration', '?')}s", f"{b.get('duration', '?')}s")
    table.add_row(
        "Tests",
        "[green]PASS[/green]" if a.get("test_result", {}).get("pass") else "[red]FAIL[/red]",
        "[green]PASS[/green]" if b.get("test_result", {}).get("pass") else "[red]FAIL[/red]",
    )
    table.add_row(
        "Files changed",
        str(len(a.get("changes", {}).get("files", []))),
        str(len(b.get("changes", {}).get("files", []))),
    )

    heuristic = a.get("heuristic_analysis", {})
    flags = heuristic.get("heuristic_flags", [])
    table.add_row(
        "Heuristic flags",
        f"[yellow]{len(flags)} flag(s)[/yellow]" if flags else "[green]None[/green]",
        "N/A (governed)",
    )
    table.add_row(
        "Decision",
        "N/A",
        f"[bold]{(cg.get('decision') or 'N/A').upper()}[/bold]",
    )
    table.add_row(
        "Overhead",
        "N/A",
        f"{cg.get('governance_overhead_pct', 0)}%",
    )

    console.print(table)


    if result.report_path:
        console.print(f"\n[dim]Report: {result.report_path}[/dim]")


@app.command("ab-batch")
def ab_batch(
    cases: str = typer.Option(..., "--cases", "-c", help="Path to YAML cases definition file"),
    output: str = typer.Option("ab_results", "--output", "-o", help="Output directory"),
    env_file: str = typer.Option(".env", "--env", help="Path to .env file"),
):
    """Run a batch of A/B evaluations from a YAML cases file."""
    init_config(env_file)
    config = get_config()
    setup_logging(config.log_level)

    console.print(Panel.fit(
        f"[bold blue]🔬 CodeGate A/B Batch Evaluation[/bold blue]\n"
        f"[dim]Cases:[/dim] {cases}",
        border_style="blue",
    ))

    from codegate.eval.ab_batch import run_batch

    with console.status("[bold green]Running batch evaluation..."):
        result = run_batch(cases_file=cases, output_dir=output)

    # Display summary
    table = Table(title="Batch Results", border_style="blue")
    table.add_column("#", style="dim")
    table.add_column("Case", style="bold")
    table.add_column("Decision")
    table.add_column("Drift")
    table.add_column("Tests A/B")
    table.add_column("Overhead")

    for c in result.cases:
        if c.get("status") == "failed":
            table.add_row(
                str(c["index"]), c["name"],
                "[red]FAILED[/red]", "—", "—", "—",
            )
        else:
            decision = (c.get("decision") or "N/A").upper()
            dec_style = "[green]" if decision == "APPROVE" else "[red]"
            table.add_row(
                str(c["index"]), c["name"],
                f"{dec_style}{decision}[/{dec_style.strip('[')}",
                str(c.get("drift_score", "?")),
                f"{c.get('line_a_tests', 0)}/{c.get('line_b_tests', 0)}",
                f"{c.get('overhead_pct', 0)}%",
            )

    console.print(table)

    if result.report_path:
        console.print(f"\n[dim]Batch report: {result.report_path}[/dim]")


@app.command()
def history():
    """Show history of governance runs."""
    init_config()
    from codegate.store.artifact_store import ArtifactStore

    store = ArtifactStore()
    runs = store.list_runs()

    if not runs:
        console.print("[dim]No governance runs found.[/dim]")
        raise typer.Exit(0)

    table = Table(title="Governance Run History")
    table.add_column("ID", style="cyan")
    table.add_column("Request", max_width=40)
    table.add_column("Decision", style="bold")
    table.add_column("Drift", justify="right")
    table.add_column("Coverage", justify="right")
    table.add_column("Tokens", justify="right")

    for run in runs:
        decision = run.get("decision", "N/A")
        decision_style = {
            "approve": "[green]✅ approve[/green]",
            "revise_code": "[yellow]🔄 revise_code[/yellow]",
            "revise_spec": "[yellow]📝 revise_spec[/yellow]",
            "escalate_to_human": "[red]⚠️ escalate[/red]",
        }.get(decision, decision)

        table.add_row(
            run.get("work_item_id", "?")[:10],
            run.get("raw_request", "?")[:40],
            decision_style,
            str(run.get("drift_score", "?")),
            str(run.get("coverage_score", "?")),
            str(run.get("total_tokens", "?")),
        )

    console.print(table)


def _display_results(state, run_dir):
    """Display governance results in a rich format."""
    console.print("\n")

    # Contract summary
    if state.contract:
        contract = state.contract
        table = Table(title="📋 Implementation Contract", border_style="blue")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        table.add_row("Goals", "\n".join(f"• {g}" for g in contract.goals))
        table.add_row("Non-Goals", "\n".join(f"• {ng}" for ng in contract.non_goals))
        table.add_row(
            "Acceptance Criteria",
            "\n".join(f"• [{ac.priority}] {ac.description}" for ac in contract.acceptance_criteria),
        )
        if contract.assumed_defaults:
            table.add_row(
                "Assumed Defaults",
                "\n".join(f"• {d.topic}: {d.assumed_value}" for d in contract.assumed_defaults),
            )

        console.print(table)

    # Review findings
    if state.review_findings:
        table = Table(title="🔍 Review Findings", border_style="yellow")
        table.add_column("Severity", width=6)
        table.add_column("Category", width=14)
        table.add_column("Message")
        table.add_column("Ref", width=20)
        table.add_column("Disposition", width=10)

        for f in state.review_findings:
            sev_style = {"P0": "red bold", "P1": "yellow", "P2": "dim"}.get(f.severity, "")
            disp_display = {
                "blocking": "[red]🚫 block[/red]",
                "advisory": "[yellow]⚠ advise[/yellow]",
                "info": "[dim]ℹ info[/dim]",
            }.get(f.disposition, f.disposition)
            table.add_row(
                f"[{sev_style}]{f.severity}[/{sev_style}]",
                f.category,
                f.message[:60],
                f.contract_clause_ref,
                disp_display,
            )
        console.print(table)

    # Gate decision
    if state.gate_decision:
        decision = state.gate_decision
        emoji = {
            "approve": "✅",
            "revise_code": "🔄",
            "revise_spec": "📝",
            "escalate_to_human": "⚠️",
        }.get(decision.decision, "❓")

        color = {
            "approve": "green",
            "revise_code": "yellow",
            "revise_spec": "yellow",
            "escalate_to_human": "red",
        }.get(decision.decision, "white")

        console.print(Panel(
            f"[bold {color}]{emoji} Decision: {decision.decision.upper()}[/bold {color}]\n\n"
            f"Drift Score:    {decision.drift_score}/100\n"
            f"Coverage Score: {decision.coverage_score}/100\n\n"
            f"{decision.summary}\n\n"
            f"[dim]Next Action: {decision.next_action}[/dim]",
            title="🛡️ Gate Decision",
            border_style=color,
        ))

    # Token usage
    console.print(f"\n[dim]Total tokens: {state.total_tokens} | "
                   f"Artifacts saved to: {run_dir}[/dim]")


if __name__ == "__main__":
    app()

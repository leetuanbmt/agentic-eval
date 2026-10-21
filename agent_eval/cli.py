import glob
import json
import os
import sys
import time
import click
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from ruamel.yaml import YAMLError
from agent_eval import __version__
from agent_eval.config import EvalConfig
from agent_eval.evaluators import EVALUATORS, EvalResult
from agent_eval.models import TestCase
from agent_eval.report import build_report, compare as compare_reports, now, render_markdown, sha256_file, write_json
from agent_eval.runner import AgentRunner, ExecutionNotAllowed
from agent_eval.sandbox import SandboxManager
from agent_eval.security import redact

console = Console()

# Exit codes: 0 all cases passed, 1 some case failed / regressed, 2 invalid config, dataset or usage.
EXIT_FAILED = 1
EXIT_INVALID = 2


def _invalid(message: str):
    console.print(f"[bold red]Error:[/bold red] {message}", highlight=False)
    sys.exit(EXIT_INVALID)


def load_test_cases(dataset: str, known_evaluators: set):
    """Loads every *.yaml / *.yml in `dataset`, sorted by filename. Any bad file aborts the run."""
    files = sorted(glob.glob(os.path.join(dataset, "*.yaml")) + glob.glob(os.path.join(dataset, "*.yml")))
    cases, seen = [], set()
    for path in files:
        try:
            tc = TestCase.load_from_yaml(path)
        except (ValidationError, ValueError, OSError, YAMLError) as e:
            _invalid(f"Failed to load test case {path}:\n{e}")
        unknown = set(tc.evaluators or []) - known_evaluators
        if unknown:
            _invalid(f"Test case {path} references unknown evaluators: {', '.join(sorted(unknown))}")
        if tc.id in seen:
            _invalid(f"Duplicate test case id '{tc.id}' in {path}")
        seen.add(tc.id)
        cases.append((tc, path))
    return cases


def run_case(tc: TestCase, tc_path: str, eval_config: EvalConfig, runner: AgentRunner, evaluators) -> dict:
    case = {"id": tc.id, "name": tc.name, "category": tc.category, "dataset_file": tc_path,
            "dataset_sha256": sha256_file(tc_path), "status": "passed", "exit_code": None,
            "duration_seconds": 0.0, "output_truncated": False, "error": None, "output_excerpt": None,
            "evaluators": []}
    sandbox = SandboxManager(tc, eval_config)
    try:
        sandbox_path = sandbox.create()
        proc = runner.run_test_case(tc, tc_path, sandbox_path)
        case.update(exit_code=proc.exit_code, duration_seconds=round(proc.duration, 3),
                    output_truncated=proc.truncated, output_excerpt=proc.output[-2000:])
        if proc.timed_out:
            case.update(status="timeout", error=f"Agent timed out after {proc.duration:.1f}s")
            return case
        expected_exit = tc.expected_outputs.get("exit_code", 0)
        if proc.exit_code != expected_exit:
            case.update(status="error", error=f"Agent exit code {proc.exit_code}, expected {expected_exit}")
        for evaluator in evaluators:
            if tc.evaluators is not None and evaluator.evaluator_def.name not in tc.evaluators:
                continue
            try:
                res = evaluator.evaluate(tc, proc.output, proc.duration, sandbox_path)
            except ExecutionNotAllowed:
                raise
            except Exception as e:
                res = EvalResult(evaluator_name=evaluator.evaluator_def.name, score=0.0, passed=False,
                                 feedback=f"Evaluator crashed: {type(e).__name__}: {e}")
            case["evaluators"].append({"type": evaluator.evaluator_def.type, **res.model_dump()})
            label = "SKIP" if res.skipped else ("✔ PASS" if res.passed else "✘ FAIL")
            color = "dim" if res.skipped else ("green" if res.passed else "red")
            console.print(f"  {evaluator.evaluator_def.name}: [{color}]{label}[/{color}] ({res.score:.1f})",
                          highlight=False)
            if not res.passed and case["status"] == "passed":
                case["status"] = "failed"
    except ExecutionNotAllowed:
        raise
    except (OSError, ValueError, KeyError) as e:
        case.update(status="error", error=f"{type(e).__name__}: {e}")
    finally:
        sandbox.clean()
    return case


@click.group()
@click.version_option(__version__, prog_name="agent-eval")
def cli():
    """Agent-Eval: Automated Evaluation Pipeline for AI Agents"""


@cli.command()
@click.option("--config", default="eval-config.yaml", help="Path to project eval-config.yaml")
@click.option("--dataset", default="evaluation/dataset", help="Path to directory containing test case YAML files")
@click.option("--output-report", default="eval-report.md", help="Path to write MD evaluation report")
@click.option("--output-json", default=None, help="Path to write the machine-readable JSON report")
@click.option("--allow-exec", is_flag=True,
              help="Allow the config to run external commands (command adapter / command evaluators).")
def run(config: str, dataset: str, output_report: str, output_json: str, allow_exec: bool):
    """Runs the evaluation pipeline against the target dataset"""
    console.print(Panel.fit(f"[bold green]Agentic Evaluation Pipeline[/bold green] v{__version__}",
                            border_style="green"))
    try:
        eval_config = EvalConfig.load_from_yaml(config)
    except (ValidationError, ValueError, OSError, YAMLError) as e:
        _invalid(f"Invalid config {config}:\n{e}")
    if not os.path.isdir(dataset):
        _invalid(f"Dataset directory not found at {dataset}")
    test_cases = load_test_cases(dataset, {e.name for e in eval_config.evaluators})
    if not test_cases:
        _invalid(f"No test cases found in directory {dataset}")
    console.print(f"Project [bold cyan]{eval_config.project.name}[/bold cyan] · adapter "
                  f"[bold]{eval_config.agent.adapter}[/bold] · runtime {eval_config.runtime.mode} · "
                  f"{len(test_cases)} test cases", highlight=False)

    runner = AgentRunner(eval_config, config, allow_exec=allow_exec)
    evaluators = [EVALUATORS[ed.type](ed, eval_config, allow_exec=allow_exec) for ed in eval_config.evaluators]
    started_at, t0 = now(), time.monotonic()
    cases = []
    for tc, tc_path in test_cases:
        console.print(f"\n[bold blue]▶ {tc.id}[/bold blue] {tc.name}", highlight=False)
        try:
            case = run_case(tc, tc_path, eval_config, runner, evaluators)
        except ExecutionNotAllowed as e:
            _invalid(str(e))
        if case["error"]:
            console.print(f"  [red]{case['status'].upper()}:[/red] {redact(case['error'])}", highlight=False)
        cases.append(case)

    report = build_report(eval_config, config, cases, started_at, time.monotonic() - t0)
    _print_table(report)
    with open(output_report, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    console.print(f"\nSaved Markdown report to [bold]{output_report}[/bold]", highlight=False)
    if output_json:
        write_json(report, output_json)
        console.print(f"Saved JSON report to [bold]{output_json}[/bold]", highlight=False)

    if report["summary"]["passed"] != report["summary"]["total"]:
        console.print("[bold red]Evaluation failed: some test cases did not pass.[/bold red]")
        sys.exit(EXIT_FAILED)
    console.print("[bold green]All evaluation test cases passed.[/bold green]")


def _print_table(report: dict):
    table = Table(show_header=True, header_style="bold magenta")
    for col, kw in (("Test Case ID", {}), ("Name", {}), ("Runtime (s)", {"justify": "right"}),
                    ("Evaluators", {}), ("Verdict", {"justify": "center"})):
        table.add_column(col, **kw)
    colors = {"passed": "green", "failed": "red", "error": "yellow", "timeout": "yellow"}
    for c in report["cases"]:
        scores = ", ".join(f"{e['evaluator_name']}: {'skip' if e['skipped'] else format(e['score'], '.1f')}"
                           for e in c["evaluators"])
        color = colors[c["status"]]
        table.add_row(c["id"], c["name"], f"{c['duration_seconds']:.2f}", scores,
                      f"[bold {color}]{c['status'].upper()}[/bold {color}]")
    console.print(table)
    s = report["summary"]
    console.print(f"Total {s['total']} · passed {s['passed']} · failed {s['failed']} · "
                  f"errors {s['error']} · timeouts {s['timeout']}", highlight=False)


@cli.command()
@click.argument("baseline", type=click.Path(exists=True, dir_okay=False))
@click.argument("current", type=click.Path(exists=True, dir_okay=False))
@click.option("--score-tolerance", default=0.0, show_default=True,
              help="Allowed per-evaluator score drop before it counts as a regression.")
def compare(baseline: str, current: str, score_tolerance: float):
    """Compares two JSON reports; exits 1 if CURRENT regressed against BASELINE."""
    try:
        with open(baseline, encoding="utf-8") as f:
            base = json.load(f)
        with open(current, encoding="utf-8") as f:
            cur = json.load(f)
        diff = compare_reports(base, cur, score_tolerance)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        _invalid(f"Not a valid agent-eval JSON report: {e}")
    for label, key, color in (("Regressions", "regressions", "red"), ("Improvements", "improvements", "green"),
                              ("New cases", "new_cases", "cyan")):
        console.print(f"[bold {color}]{label}: {len(diff[key])}[/bold {color}]")
        for line in diff[key]:
            console.print(f"  - {line}", markup=False, highlight=False)
    if diff["regressions"]:
        sys.exit(EXIT_FAILED)


def main():
    # Loaded here, not at import, so importing the package never mutates the environment.
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True))  # Default lookup starts at this module's dir, i.e. site-packages.
    cli()


if __name__ == "__main__":
    main()

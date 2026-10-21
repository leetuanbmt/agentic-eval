import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from typing import List
from agent_eval import __version__
from agent_eval.config import EvalConfig
from agent_eval.security import redact

SCHEMA_VERSION = 1
STATUSES = ("passed", "failed", "error", "timeout")
OUTPUT_EXCERPT_CHARS = 2000


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def build_report(config: EvalConfig, config_path: str, cases: List[dict], started_at: datetime,
                 duration: float) -> dict:
    """Assembles the machine-readable report. Every string in it is passed through redact()."""
    cases = _redact_all(cases)
    summary = {"total": len(cases), **{s: sum(c["status"] == s for c in cases) for s in STATUSES}}
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "agentic-eval", "version": __version__},
        "project": {"name": config.project.name, "version": config.project.version},
        "started_at": started_at.isoformat(timespec="seconds"),
        "duration_seconds": round(duration, 3),
        "environment": {"python": platform.python_version(), "platform": sys.platform},
        "config": {"path": config_path, "sha256": sha256_file(config_path), "adapter": config.agent.adapter,
                   "runtime": config.runtime.mode,
                   "evaluators": [{"name": e.name, "type": e.type} for e in config.evaluators]},
        "summary": summary,
        "cases": cases,
    }


def _redact_all(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: _redact_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_all(v) for v in value]
    return value


def now() -> datetime:
    return datetime.now(timezone.utc)


def render_markdown(report: dict) -> str:
    s = report["summary"]
    md = [f"# Agent Evaluation Report: {report['project']['name']}",
          f"Version: {report['project']['version']}",
          "",
          f"- Started: {report['started_at']} · Duration: {report['duration_seconds']:.2f}s",
          f"- Adapter: `{report['config']['adapter']}` · Runtime: `{report['config']['runtime']}`"
          f" · agentic-eval {report['tool']['version']}",
          f"- **Total {s['total']}** · passed {s['passed']} · failed {s['failed']}"
          f" · errors {s['error']} · timeouts {s['timeout']}",
          "",
          "## Summary Scorecard",
          "",
          "| Test Case ID | Test Case Name | Runtime (s) | Verdict | Evaluators Detail |",
          "| --- | --- | --- | --- | --- |"]
    for c in report["cases"]:
        verdict = {"passed": "🟢 PASS", "failed": "🔴 FAIL", "error": "🟠 ERROR", "timeout": "⏱ TIMEOUT"}[c["status"]]
        scores = "<br>".join(f"**{e['evaluator_name']}**: "
                             + ("SKIP" if e["skipped"] else f"{e['score']:.1f} ({'PASS' if e['passed'] else 'FAIL'})")
                             for e in c["evaluators"]) or "-"
        md.append(f"| {c['id']} | {c['name']} | {c['duration_seconds']:.2f}s | {verdict} | {scores} |")
    md += ["", "## Detailed Evaluator Feedback", ""]
    for c in report["cases"]:
        md.append(f"### Test Case: {c['id']} - {c['name']}")
        if c.get("error"):
            md += [f"- **Error:** {c['error']}", ""]
        for e in c["evaluators"]:
            md += [f"#### Evaluator: {e['evaluator_name']}",
                   f"- **Score:** {e['score']:.1f} / 100.0",
                   f"- **Passed:** {'Skipped' if e['skipped'] else 'Yes' if e['passed'] else 'No'}",
                   "- **Feedback:**", "```", e["feedback"], "```", ""]
    return "\n".join(md) + "\n"


def compare(baseline: dict, current: dict, score_tolerance: float = 0.0) -> dict:
    """Deterministic diff keyed by case id. Regressions: a passing case no longer passes, a case
    disappeared, or an evaluator score dropped by more than `score_tolerance`."""
    base = {c["id"]: c for c in baseline["cases"]}
    cur = {c["id"]: c for c in current["cases"]}
    regressions, improvements = [], []
    for cid, b in base.items():
        c = cur.get(cid)
        if c is None:
            regressions.append(f"{cid}: missing from current run")
            continue
        if b["status"] == "passed" and c["status"] != "passed":
            regressions.append(f"{cid}: passed -> {c['status']}")
        elif b["status"] != "passed" and c["status"] == "passed":
            improvements.append(f"{cid}: {b['status']} -> passed")
        b_scores = {e["evaluator_name"]: e["score"] for e in b["evaluators"] if not e["skipped"]}
        for e in c["evaluators"]:
            old = b_scores.get(e["evaluator_name"])
            if old is not None and not e["skipped"] and old - e["score"] > score_tolerance:
                regressions.append(f"{cid}/{e['evaluator_name']}: score {old:.1f} -> {e['score']:.1f}")
    return {"regressions": regressions, "improvements": improvements,
            "new_cases": sorted(set(cur) - set(base))}


def write_json(report: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")

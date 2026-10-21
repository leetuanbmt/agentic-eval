<h1 align="center">agentic-eval</h1>

<p align="center">
  Offline-first CLI for evaluating AI coding agents.<br>
  YAML test cases, deterministic checks, JSON/Markdown reports and a regression gate for CI.
</p>

<p align="center">
  <a href="https://github.com/leetuanbmt/agentic-eval/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/leetuanbmt/agentic-eval/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="status" src="https://img.shields.io/badge/status-alpha-orange">
</p>

---

Agent changes (a new prompt, model, tool or workflow file) are easy to make and hard to verify.

You describe test cases in YAML and point `agent-eval` at your agent. It runs each case in a fresh
workspace, scores the result with deterministic checks (and optionally an LLM judge), and writes
JSON + Markdown reports with a CI-friendly exit code. Two reports can be diffed to catch regressions.
Agentic-Eval evaluates agents; it does not orchestrate them.

> Status: alpha (0.1.0). The workflow below is implemented and tested; interfaces may still change.

---

## Why

Agentic-Eval gives you a repeatable answer to "did this change make the agent better or worse?":

- the same dataset runs against any agent you can start from a command line;
- deterministic evaluators give the same verdict every run, so CI gates are stable;
- reports carry config and dataset hashes, so a result can be traced to exactly what produced it;
- `agent-eval compare` turns two runs into a pass/fail regression gate.

---

## Features

| Area | What exists today |
| --- | --- |
| Agent adapters | `mock` (canned output, offline), `command` (any local process, argv without a shell) |
| Runtime | `local` (temp working directory) or `docker` (throwaway container, network off by default) |
| Evaluators | `exact_match`, `contains`, `json` (subset match), `command` (exit code of e.g. your test suite), `llm_judge` (optional) |
| Reports | Markdown, JSON (`schema_version: 1`), exit code `0` pass / `1` fail / `2` invalid input |
| Regression | `agent-eval compare baseline.json current.json` |
| Safety | No command runs without `--allow-exec`; path containment; minimal child env; timeouts; secret redaction |

Not included: parallel execution, statistical benchmarking, a web UI, agent orchestration.

---

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/leetuanbmt/agentic-eval
cd agentic-eval
pip install -e .                 # core, offline
pip install -e '.[gemini]'       # optional: Gemini LLM judge
pip install -e '.[openai]'       # optional: OpenAI-compatible LLM judge (OpenAI, ollama, ...)
```

---

## Five-minute quickstart

The quickstart uses the `mock` adapter: no API keys, no external commands.

```bash
agent-eval run \
  --config examples/quickstart/eval-config.yaml \
  --dataset examples/quickstart/dataset \
  --output-json eval-report.json
echo $?   # 1 — one case is designed to fail
```

```
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ Test Case ID      ┃ Name                          ┃ Runtime (s) ┃ Evaluators                     ┃ Verdict ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ greeting          │ Agent prints the expected     │        0.00 │ invariants: 100.0, exact:      │ PASSED  │
│                   │ greeting                      │             │ 100.0                          │         │
│ structured-report │ Agent writes a structured     │        0.00 │ invariants: 100.0, exact:      │ PASSED  │
│                   │ JSON report                   │             │ skip, report-json: 100.0       │         │
│ missing-invariant │ Agent forgets to mention the  │        0.00 │ invariants: 50.0               │ FAILED  │
│                   │ safety verdict                │             │                                │         │
└───────────────────┴───────────────────────────────┴─────────────┴────────────────────────────────┴─────────┘
Total 3 · passed 2 · failed 1 · errors 0 · timeouts 0
```

The run writes `eval-report.md` and `eval-report.json`. Sample outputs are committed in
[`examples/quickstart/sample-report.md`](examples/quickstart/sample-report.md) and
[`sample-report.json`](examples/quickstart/sample-report.json).

Next, evaluate a real process. [`examples/local-agent`](examples/local-agent) runs a toy agent that writes
Python code, checks it with a unit-test command, and shows a pass, a failure and a timeout:

```bash
agent-eval run --config examples/local-agent/eval-config.yaml \
  --dataset examples/local-agent/dataset --allow-exec
```

---

## Configuration

`eval-config.yaml`:

```yaml
project:
  name: "my-agent"
  root: "."             # source_context paths resolve here (relative to this file)

agent:
  adapter: command      # or: mock
  command: ["{python}", "my_agent.py", "--task", "{task}", "--workspace", "{sandbox}"]
  timeout_seconds: 300
  env: [OPENAI_API_KEY] # extra env vars the agent may see; everything else is withheld

evaluators:
  - name: tests
    type: command
    command: ["{python}", "-m", "pytest", "-q"]
  - name: mentions-summary
    type: contains
```

A test case (`dataset/*.yaml`, one file per case, run in filename order):

```yaml
id: fix-off-by-one            # [A-Za-z0-9._-], unique
name: "Fix the off-by-one bug in paginate()"
inputs:
  task: fix-pagination        # available to the command template as {task}
  source_context:             # copied from project.root into the case workspace
    - path: src/
    - path: tests/
expected_outputs:
  invariants: ["paginate"]    # used by `contains`
  exit_code: 0                # expected agent exit code (default 0)
limits:
  timeout_seconds: 120        # overrides agent.timeout_seconds
evaluators: [tests]           # optional: only run these evaluators for this case
```

Command placeholders: `{python}` (current interpreter), `{sandbox}` (case workspace), `{test_case_path}`,
`{config}`, every key in `inputs`, and every key in `inputs.command_args`. Each placeholder is substituted
inside a single argv element, so values containing spaces or `;` cannot inject extra commands.

### Evaluators

| Type | Passes when | Reads |
| --- | --- | --- |
| `exact_match` | stripped target equals `expected_outputs.exact` | agent output, or `file:` in workspace |
| `contains` | every string in `expected_outputs.invariants` occurs; score = share found | same |
| `json` | target parses as JSON and contains `expected_outputs.json` (nested subset) | same |
| `command` | the command exits 0 in the workspace (`syntax_checker` is an alias) | requires `--allow-exec` |
| `llm_judge` | model score ≥ `threshold` (default 80) | output + `expected_outputs.generated_files` |

An evaluator whose expectation is missing from a test case is reported as `SKIP` and does not affect the verdict.
A case is `passed` only if the agent exits with the expected code and no applicable evaluator fails;
otherwise it is `failed`, `error` (crash, bad exit code, path violation) or `timeout`.

---

## Regression checks

```bash
agent-eval run ... --output-json baseline.json        # on main
agent-eval run ... --output-json current.json         # on your branch
agent-eval compare baseline.json current.json --score-tolerance 5
```

`compare` exits 1 if a previously passing case no longer passes, a case disappeared, or an evaluator score
dropped by more than the tolerance. It is a deterministic diff; it does not do statistics.

---

## Using it in CI

```yaml
- run: pip install "git+https://github.com/leetuanbmt/agentic-eval@main"   # not on PyPI yet
- run: agent-eval run --config eval-config.yaml --dataset evaluation/dataset --output-json eval-report.json
```

The job fails on any non-passing case (exit 1) or invalid config/dataset (exit 2).

---

## Offline execution and optional LLM evaluation

Everything except `llm_judge` and the Gemini example runs offline. The test suite needs no API keys.

`llm_judge` sends the (redacted) agent output and expected files to the configured provider:

```yaml
llm_judge:
  default_provider: openai          # google | openai | anthropic | ollama | custom
  default_model: "gpt-4.1-mini"
  temperature: 0.0
  custom_endpoint: null             # base URL for OpenAI-compatible servers
```

`OPENAI_API_KEY` is only sent to OpenAI's default endpoint. A `custom_endpoint` receives
`AGENT_EVAL_JUDGE_API_KEY` instead (or no key, which is fine for ollama), so a shared config cannot
redirect your OpenAI key to another host.

LLM grading is nondeterministic: the same output can get different scores. Each result records
`provider`, `model`, `temperature`, `nondeterministic: true`, and token `usage` when the provider returns it
(otherwise `null`). Cost is not estimated. Prefer deterministic evaluators for CI gates.

[`examples/gemini-agent`](examples/gemini-agent) shows a real LLM agent (Gemini function calling) under evaluation.
It makes paid API calls.

---

## Security model and limitations

Read this before evaluating an agent you do not trust.

- **Nothing executes without `--allow-exec`.** Configs and datasets that use the `command` adapter or `command`
  evaluators fail with exit code 2 unless you pass the flag.
- **`runtime.mode: local` is not a sandbox.** The agent runs as your user, in a temp directory, with a reduced
  environment. It can still read and write anything your user can. Use it only for agents you trust.
- **`runtime.mode: docker`** runs each command in a disposable container: `--network none`, `--cap-drop ALL`,
  `no-new-privileges`, memory and PID limits, only the workspace mounted read-write. This is a meaningful
  boundary but not a hardened one (shared kernel; your Docker daemon's configuration applies).
- **No shell by default.** Commands run as argv. `agent.shell: true` opts into `/bin/sh -c`; substituted
  values are passed as positional parameters (`"$1"`), so they are never parsed as shell code.
  Placeholders inside single quotes are rejected.
- **Paths are contained.** `source_context`, evaluator `file:` and generated-file paths must stay inside their
  root after resolving symlinks; copied symlinks pointing outside the workspace are removed.
- **Environment.** Child processes get `PATH`, `HOME`, locale and temp variables plus what you list in
  `agent.env`. `.env` in the working directory is loaded into agent-eval's own environment.
- **Secrets in reports.** Values of env vars whose names contain `KEY`, `TOKEN`, `SECRET`, `PASSW`,
  `CREDENTIAL` or `AUTH`, and common key formats (`sk-…`, `AIza…`, `ghp_…`, `AKIA…`), are replaced with
  `[REDACTED]` in console output, reports and LLM-judge prompts. Redaction is best-effort.
- **Timeouts** kill the whole process group (POSIX) or the container. Output is capped at
  `agent.max_output_bytes`. CPU and disk are not limited in local mode.
- **LLM judges can be prompt-injected** by the agent output they grade.
- Tested on macOS and Linux. Windows is untested.

Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

---

## Migrating from the pre-release CLI

`agent-eval run --config --dataset --output-report` and the `agent_commands.execute_command` config still work,
with these intentional changes:

- commands need `--allow-exec`, run without a shell, and only see the environment variables listed in `agent.env`;
- `agent_commands` has no `env` list, so an agent that needs an API key must move to the `agent:` section
  (`adapter: command`, `command:`, `env: [GEMINI_API_KEY]`);
- `project.root` is resolved relative to the config file, not the current directory;
- auto-answering `y` to approval prompts is off unless `agent.auto_approve: true`;
- workspaces are created in the system temp directory instead of `<dataset>/../sandbox`;
- an empty or invalid dataset, or an unknown evaluator type, now exits 2 instead of continuing;
- the agent's exit code now counts (`expected_outputs.exit_code`, default 0);
- `llm_judge` decides pass/fail from `threshold`, not from the model's own `passed` field;
- the Gemini SDK moved from the deprecated `google-generativeai` to `google-genai`, now an optional extra;
- the built-in Gemini simulator moved to `examples/gemini-agent/agent.py`.

---

## Testing

```bash
pip install -e '.[dev]'
pytest -q
```

```console
97 passed in 7.44s
```

The suite runs offline, blocks network access and provider SDK imports, and covers config validation,
dataset loading, every evaluator, timeouts and process cleanup, report redaction, regression comparison,
path/symlink escapes and shell-injection attempts. Three Docker isolation tests run when Docker and the
`python:3.12-slim` image are available, and are skipped otherwise.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: `pip install -e '.[dev]' && ruff check . && pytest`.

---

## Roadmap

Candidates, in rough priority order; none are promised:

1. Adapters for Codex CLI and Claude Code, if they can be driven non-interactively without special casing.
2. Repeat runs per case (`--repeat N`) to surface flaky agents and LLM-judge variance.
3. Parallel case execution.
4. JUnit XML output for CI test panels.

---

## License

[MIT](LICENSE)

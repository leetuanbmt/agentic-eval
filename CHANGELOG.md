# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - Unreleased

First public release.

### Added
- `mock` agent adapter for offline, deterministic runs.
- `exact_match`, `contains` and `json` evaluators; evaluators read agent output or a workspace `file:`.
- JSON report (`--output-json`, `schema_version: 1`) with summary counts, per-case status
  (`passed` / `failed` / `error` / `timeout`), durations, config and dataset SHA-256, tool and Python version.
- `agent-eval compare` for deterministic regression checks between two JSON reports.
- `runtime.mode: docker` with network disabled, dropped capabilities, memory and PID limits.
- Per-case `evaluators` selection, `limits.timeout_seconds`, `expected_outputs.exit_code`.
- `--allow-exec`, `--version`; exit code 2 for invalid config or dataset.
- Secret redaction in console output, reports and LLM-judge prompts.
- Examples: `quickstart` (mock), `local-agent` (command adapter), `gemini-agent` (live LLM).
- Test suite, GitHub Actions CI, MIT license, contributing and security docs.

### Changed
- Commands run as argv without a shell, require `--allow-exec`, have timeouts that kill the process group,
  and receive only a minimal environment plus `agent.env`.
- `project.root` resolves relative to the config file.
- Workspaces live in the system temp directory.
- `llm_judge` computes pass/fail from `threshold`; records model metadata and token usage.
- LLM provider SDKs are optional extras (`[gemini]` uses `google-genai`, `[openai]`).
- Approval auto-answering is opt-in (`agent.auto_approve`).

### Removed
- `setup.py` (metadata lives in `pyproject.toml`).
- Built-in `agent_eval.simulator`; it is now `examples/gemini-agent/agent.py`.
- Project-specific sample config and dataset.

### Security
- Fixed: a test-case `id` could make the sandbox step delete an arbitrary directory.
- Fixed: `source_context`, `generated_files` and simulator tool paths could escape their root
  (prefix check, `..`, absolute paths, symlinks).
- Fixed: test-case values were interpolated into `shell=True` commands.
- Background processes left by an agent are killed when it exits; output capture is bounded in bytes
  regardless of line length.
- Streamed console output is redacted per line, so secrets split across reads are still caught;
  test-case inputs cannot override reserved command placeholders such as `{sandbox}`.

# agentic-eval 0.1.0 (draft)

First public release of a small, offline-first CLI for evaluating AI coding agents.

## Highlights
- Run YAML test cases against a `mock` agent (offline) or any local `command`, optionally inside Docker
  with networking disabled.
- Deterministic evaluators: `exact_match`, `contains`, `json`, `command`; optional `llm_judge`
  (Gemini or OpenAI-compatible) that records model, temperature and token usage.
- JSON + Markdown reports, exit codes for CI, and `agent-eval compare` for regression gates.
- Safe by default: nothing executes without `--allow-exec`; no shell; contained paths; minimal child
  environment; timeouts; secret redaction.

## Upgrading from the pre-release
See "Migrating from the pre-release CLI" in the README. Commands now need `--allow-exec`, and only
environment variables listed in `agent.env` reach the agent.

## Known limitations
Local runtime is not a sandbox. Windows is untested. LLM judging is nondeterministic.

Full list: [CHANGELOG.md](../CHANGELOG.md).

# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
ruff check .
pytest -q
```

The test suite runs offline and needs no API keys. Tests marked for Docker are skipped when Docker is unavailable.

## Guidelines

- Open an issue first for new adapters, evaluators or config keys, so the scope can be agreed.
- Keep the core dependency-light; provider SDKs belong in optional extras and must be imported lazily.
- Every behaviour change needs a test. Never add tests that call a live LLM.
- Anything that executes commands or touches paths must go through `agent_eval.runner.execute` and
  `agent_eval.security.safe_join`.
- Update `CHANGELOG.md` under "Unreleased" and the README when user-visible behaviour changes.

## Reporting security issues

Do not open a public issue; see [SECURITY.md](SECURITY.md).

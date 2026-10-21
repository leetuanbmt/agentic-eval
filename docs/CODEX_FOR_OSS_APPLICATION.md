# Codex for Open Source — application draft

Status: **draft, not submitted.** The form page (https://openai.com/form/codex-for-oss/) could not be fetched
while preparing this (HTTP 403), so the field names below follow the maintainer's brief, not the live form.
Check each answer against the real questions and their limits before submitting.

## Facts (verifiable as of 2026-10-21)

| Item | Value | Source |
| --- | --- | --- |
| Repository | https://github.com/leetuanbmt/agentic-eval | GitHub |
| Visibility | Public; recreated with clean history on 2026-10-21 | `gh repo view` |
| Stars / forks | 0 / 0 | `gh repo view` |
| Contributors | 1 (maintainer) | git log |
| License | MIT | `LICENSE` |
| Releases | None yet; 0.1.0 prepared | `CHANGELOG.md` |
| Tests | 97 offline pytest tests incl. 3 Docker isolation tests; verified locally on Python 3.10, 3.14 (macOS) and 3.12 (Linux) | `tests/` |
| CI | Passing on Python 3.10 and 3.13: ruff, 97 tests incl. Docker isolation, build, pip-audit | GitHub Actions run 39550365153 |

There is no adoption yet. This application rests on the engineering problem and the maintenance plan,
not on usage numbers.

## Maintainer role

Sole author and maintainer: design, implementation, security fixes, reviews, releases.

## Project significance

Teams are changing agent prompts, models, tools and workflow files faster than they can check whether the
agent got better or worse. Most eval tooling is tied to one provider or one framework, or requires an LLM
to grade every run. Agentic-Eval is a small, vendor-neutral CLI: YAML test cases, any agent you can start from
a command, deterministic evaluators that give CI-stable verdicts, optional LLM judging with recorded model
metadata, JSON/Markdown reports with config and dataset hashes, and a `compare` command for regression gates.
It treats agent execution as untrusted: no command runs without `--allow-exec`, paths are contained, the child
environment is minimal, and an opt-in Docker runtime disables networking.

## Maintenance activity to date

- Hardened execution: removed `shell=True` interpolation of dataset values, added timeouts that kill the
  process group/container, fixed a test-case id that could delete an arbitrary directory, fixed path and
  symlink escapes (see `CHANGELOG.md` → Security).
- Made the core offline: provider SDKs moved to optional extras; migrated from the end-of-life
  `google-generativeai` SDK to `google-genai`.
- Removed project-specific defaults so the tool works for any agent.
- Added the test suite, CI, contribution and security policies.

## How Codex would help maintain the project

- Writing and extending tests for new adapters and evaluators (the 0.1.0 suite was drafted by Codex and
  reviewed/corrected by the maintainer, who also fixed the two bugs it surfaced).
- Reviewing pull requests for the security-sensitive paths (`runner.py`, `security.py`, `sandbox.py`).
- Building the roadmap items: Codex CLI / Claude Code adapters, repeat runs for flakiness, JUnit output.

## Intended use of API credits

Only for this open-source project:
- CI-adjacent maintenance runs: Codex-assisted test generation and PR review on this repository;
- live validation of the optional LLM paths before releases (`examples/gemini-agent`, and the Gemini and
  OpenAI-compatible `llm_judge` providers), which so far are only tested offline.

Not for: any private, client or commercial workload, including the maintainer's employer or other products.

## Current limitations and open blockers

- No users, stars or external contributors yet.
- v0.1.0 is tagged; no GitHub Release or PyPI package yet.
- The optional Gemini/OpenAI code paths have not been run against live APIs.
- Local runtime is not a sandbox; Docker isolation is basic. Windows is untested.

## Draft answers (English, each under 500 characters)

**1. What does your project do and why does it matter?** (452 chars)

> Agentic-Eval is a small, vendor-neutral CLI for evaluating AI coding agents. Developers write YAML test cases,
> run any agent from a command (or a mock, offline), and get deterministic scores, JSON/Markdown reports and a
> compare command that gates regressions in CI. No command runs without explicit opt-in; paths are contained,
> secrets redacted, and a Docker runtime disables networking. It answers: did this prompt or model change make
> my agent worse?

**2. What is your role and how do you maintain it?** (377 chars)

> I am the sole author and maintainer. v0.1.0 (October 2026) hardened command execution (no shell
> interpolation, process-group timeouts, path and symlink containment), made the core offline with optional
> LLM providers, and added 97 tests, CI on Python 3.10 and 3.13, and security and contribution policies. The
> project is new: it has no external users, stars or contributors yet.

**3. How would you use Codex and API credits?** (420 chars)

> Codex: drafting tests and reviewing changes to the security-sensitive runner and sandbox code (Codex drafted
> the 0.1.0 test suite; I reviewed and corrected it), plus roadmap work such as Codex CLI and Claude Code
> adapters and repeat runs to measure flakiness. Credits: only for this repository, including live validation
> of the optional Gemini and OpenAI judge paths before releases. None for private or commercial work.

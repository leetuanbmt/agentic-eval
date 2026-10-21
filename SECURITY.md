# Security Policy

## Supported versions

Only the latest release on `main` receives fixes while the project is pre-1.0.

## Reporting a vulnerability

Please report privately through GitHub's
[private vulnerability reporting](https://github.com/leetuanbmt/agentic-eval/security/advisories/new).
Include a minimal config/dataset that reproduces the issue. You should get a response within 7 days.

## Threat model

Agentic-Eval runs agents and commands defined in config and dataset files. Treat those files as code.

In scope (please report):
- a command executing without `--allow-exec`;
- a path in `source_context`, evaluator `file:` or `generated_files` reading or writing outside its root;
- test-case values altering the argv of a command beyond the single element they are substituted into;
- secrets from the environment appearing unredacted in reports, or sent to a host the user did not choose;
- a timeout failing to stop the agent's process group or container.

Out of scope:
- anything an agent does in `runtime.mode: local` with your user's permissions — local mode is not a sandbox;
- container escapes caused by the Docker daemon or kernel;
- prompt injection of the optional LLM judge.

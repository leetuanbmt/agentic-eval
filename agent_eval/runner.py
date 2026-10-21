import codecs
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Union
from rich.console import Console
from agent_eval.config import EvalConfig, RuntimeConfig
from agent_eval.models import TestCase
from agent_eval.security import redact, safe_join

console = Console()

# Variables every child process may see; anything else must be listed in agent.env.
BASE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "PYTHONIOENCODING")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
APPROVAL_PATTERNS = ("approve?", "do you want to proceed", "press enter to continue", "[y/n]", "approve the plan",
                     "xác nhận", "đồng ý")
# Container-side paths used when runtime.mode is docker.
DOCKER_WORKSPACE = "/workspace"
DOCKER_EVAL_DIR = "/eval"


class ExecutionNotAllowed(RuntimeError):
    """Raised when a config asks to run a command but the run was not started with --allow-exec."""


@dataclass
class ProcessResult:
    exit_code: Optional[int]
    output: str
    duration: float
    timed_out: bool = False
    truncated: bool = False


def build_env(extra_names: List[str]) -> Dict[str, str]:
    names = set(BASE_ENV) | set(extra_names)
    return {k: v for k, v in os.environ.items() if k in names}


def render_command(template: Union[str, List[str]], variables: Dict[str, str], shell: bool) -> List[str]:
    """Renders a command template into argv. Values are substituted per token, never re-split."""
    try:
        if shell:
            return _render_shell(template if isinstance(template, str) else " ".join(template), variables)
        tokens = shlex.split(template) if isinstance(template, str) else list(template)
        return [t.format(**variables) for t in tokens]
    except KeyError as e:
        raise KeyError(f"Missing template variable {e} in command: {template}") from None


def _render_shell(script: str, variables: Dict[str, str]) -> List[str]:
    """Replaces each {name} with a positional parameter, so values are never parsed as shell code.

    Unquoted placeholders become "$N" (one word); inside double quotes they become ${N}.
    Placeholders inside single quotes are rejected because the shell would not expand them.
    """
    out, args, quote, i = [], [], None, 0
    while i < len(script):
        ch = script[i]
        if script.startswith(("{{", "}}"), i):  # str.format-style escapes for literal braces
            out.append(ch)
            i += 2
            continue
        m = PLACEHOLDER.match(script, i) if ch == "{" else None
        if m:
            if quote == "'":
                raise ValueError(f"Placeholder {m.group(0)} inside single quotes in shell command: {script}")
            args.append(variables[m.group(1)])  # KeyError for unknown names, as in argv mode
            ref = f"${{{len(args)}}}"
            out.append(ref if quote == '"' else f'"{ref}"')
            i = m.end()
            continue
        if ch == "\\" and quote != "'":
            out.append(script[i:i + 2])
            i += 2
            continue
        if ch in "'\"" and quote in (None, ch):
            quote = None if quote else ch
        out.append(ch)
        i += 1
    return ["/bin/sh", "-c", "".join(out), "sh", *args]


def template_vars(test_case: TestCase) -> Dict[str, str]:
    variables = {}
    for k, v in test_case.inputs.items():
        variables[k] = str(v)
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                variables[f"{k}_{sub_k}"] = str(sub_v)
    # command_args keys are also exposed unprefixed, e.g. {workflow} for inputs.command_args.workflow.
    for k, v in (test_case.inputs.get("command_args") or {}).items():
        variables[k] = str(v)
    return variables


def wrap_docker(argv: List[str], runtime: RuntimeConfig, workspace: str, env: Dict[str, str],
                mounts: Dict[str, str], name: str) -> List[str]:
    cmd = ["docker", "run", "--rm", "--name", name, "--network", runtime.docker_network,
           "--memory", runtime.docker_memory, "--pids-limit", str(runtime.docker_pids_limit),
           "--security-opt", "no-new-privileges", "--cap-drop", "ALL",
           "-v", f"{workspace}:{DOCKER_WORKSPACE}", "-w", DOCKER_WORKSPACE]
    if hasattr(os, "getuid"):  # Files the agent writes stay owned by the host user, so cleanup can delete them.
        cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    for host, container in mounts.items():
        cmd += ["-v", f"{host}:{container}:ro"]
    for k in env:
        if k not in ("PATH", "HOME", "TMPDIR", "TEMP", "TMP"):  # The image's own values are the right ones.
            cmd += ["-e", k]  # Value is read from the docker client's env, so it never appears in argv.
    return cmd + [runtime.docker_image] + argv


def run_process(argv: List[str], cwd: str, env: Dict[str, str], timeout: float,
                max_output_bytes: int = 1_000_000, auto_approve: bool = False,
                stream: bool = False, on_timeout=None) -> ProcessResult:
    """Runs argv without a shell; on timeout kills the whole process group."""
    start = time.monotonic()
    posix = os.name == "posix"
    proc = subprocess.Popen(
        argv, cwd=cwd, env=env,
        stdin=subprocess.PIPE if auto_approve else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=posix,  # Own process group, so grandchildren die with it on timeout.
    )
    captured = bytearray()
    truncated = False

    def reader():
        nonlocal truncated
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        tail = ""  # Bounded window for prompt detection; output may contain no newlines at all.
        pending = ""  # Console text is printed per line so redact() sees whole secrets, not chunk halves.
        # Fixed-size reads keep memory bounded by max_output_bytes whatever the line lengths.
        while data := proc.stdout.read1(65536):
            room = max_output_bytes - len(captured)
            if len(data) > room:
                truncated = True  # Past the cap, keep draining so the child never blocks on a full pipe.
            if room > 0:
                captured.extend(data[:room])
            text = decoder.decode(data)
            if stream:
                pending += text
                cut = pending.rfind("\n") + 1 if len(pending) < 65536 else len(pending)
                if cut:
                    console.print(redact(pending[:cut]), end="", markup=False, highlight=False)
                    pending = pending[cut:]
            if auto_approve:
                tail = (tail + text)[-512:]
                if any(p in tail.lower() for p in APPROVAL_PATTERNS):
                    tail = ""
                    try:
                        proc.stdin.write(b"y\n")
                        proc.stdin.flush()
                    except OSError:
                        pass
        if stream and pending:
            console.print(redact(pending), end="", markup=False, highlight=False)

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if on_timeout:
            on_timeout()
        if posix:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        proc.wait()
    if posix and not timed_out:
        # Background children left by the agent must not keep running while evaluators inspect the workspace.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    t.join(timeout=5)
    return ProcessResult(None if timed_out else proc.returncode, captured.decode("utf-8", errors="ignore"),
                         time.monotonic() - start, timed_out, truncated)


def execute(argv: List[str], config: EvalConfig, workspace: str, env_names: List[str], timeout: float,
            mounts: Optional[Dict[str, str]] = None, **kwargs) -> ProcessResult:
    """Single choke point for running configured commands, locally or inside the docker runtime."""
    env = build_env(env_names)
    if config.runtime.mode != "docker":
        return run_process(argv, workspace, env, timeout, **kwargs)
    name = f"agent-eval-{uuid.uuid4().hex[:12]}"
    # Killing the docker client does not stop the container, so stop it explicitly.
    kill = lambda: subprocess.run(["docker", "kill", name], capture_output=True)  # noqa: E731
    docker_argv = wrap_docker(argv, config.runtime, workspace, env, mounts or {}, name)
    return run_process(docker_argv, workspace, env, timeout, on_timeout=kill, **kwargs)


class AgentRunner:
    def __init__(self, config: EvalConfig, config_path: str, allow_exec: bool = False):
        self.config = config
        self.config_path = os.path.abspath(config_path)
        self.allow_exec = allow_exec

    @property
    def adapter(self) -> str:
        return self.config.agent.adapter

    def _build_command(self, test_case: TestCase, test_case_path: str, sandbox_path: str):
        agent = self.config.agent
        docker = self.config.runtime.mode == "docker"
        tc_path = os.path.abspath(test_case_path)
        mounts = {}
        if docker:
            mounts = {tc_path: f"{DOCKER_EVAL_DIR}/test_case.yaml", self.config_path: f"{DOCKER_EVAL_DIR}/config.yaml"}
        variables = template_vars(test_case)
        variables.update({
            "python": "python" if docker else sys.executable,
            "test_case_path": mounts.get(tc_path, tc_path),
            "sandbox": DOCKER_WORKSPACE if docker else sandbox_path,
            "config": mounts.get(self.config_path, self.config_path),
        })
        return render_command(agent.command, variables, agent.shell), mounts

    def run_test_case(self, test_case: TestCase, test_case_path: str, sandbox_path: str) -> ProcessResult:
        if self.adapter == "mock":
            return self._run_mock(test_case, sandbox_path)
        if not self.allow_exec:
            raise ExecutionNotAllowed("agent.adapter 'command' runs external commands; re-run with --allow-exec")
        argv, mounts = self._build_command(test_case, test_case_path, sandbox_path)
        console.print(f"[bold blue]Executing agent:[/bold blue] {redact(shlex.join(argv))}", highlight=False)
        agent = self.config.agent
        timeout = float(test_case.limits.get("timeout_seconds", agent.timeout_seconds))
        return execute(argv, self.config, sandbox_path, agent.env, timeout, mounts=mounts,
                       max_output_bytes=agent.max_output_bytes, auto_approve=agent.auto_approve, stream=True)

    @staticmethod
    def _run_mock(test_case: TestCase, sandbox_path: str) -> ProcessResult:
        mock = test_case.mock
        if mock is None:
            raise ValueError(f"Test case {test_case.id} has no 'mock' section, required by agent.adapter 'mock'")
        for rel, content in mock.files.items():
            dest = safe_join(sandbox_path, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(content)
        return ProcessResult(mock.exit_code, mock.output, 0.0)

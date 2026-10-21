import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from agent_eval.cli import run_case
from agent_eval.runner import BASE_ENV, AgentRunner, build_env, render_command, run_process


@pytest.mark.parametrize('value', ['a value with spaces', 'a; rm -rf x'])
def test_render_argv_preserves_value(value):
    assert render_command(['program', '{value}'], {'value': value}, False) == ['program', value]


def test_shell_substitutions_are_positional_parameters():
    value = 'a; rm -rf x'
    argv = render_command(['printf', '%s', '{value}'], {'value': value}, True)
    assert argv == ['/bin/sh', '-c', 'printf %s "${1}"', 'sh', value]


@pytest.mark.parametrize('template', ['echo {v}', 'echo "{v}"', 'echo "pre {v} post"'])
def test_shell_values_never_execute(tmp_path, template):
    argv = render_command(template, {'v': '$(touch pwned) `touch pwned2` "; touch pwned3'}, shell=True)
    result = run_process(argv, str(tmp_path), build_env([]), timeout=5)
    assert result.exit_code == 0 and '$(touch pwned)' in result.output
    assert not list(tmp_path.glob('pwned*'))


def test_shell_placeholder_in_single_quotes_rejected():
    with pytest.raises(ValueError):
        render_command("echo '{v}'", {'v': 'x'}, shell=True)


def test_missing_template_variable():
    with pytest.raises(KeyError, match='Missing template variable'):
        render_command(['program', '{missing}'], {}, False)


@pytest.mark.skipif(os.name != 'posix', reason='Process groups require POSIX')
def test_timeout_kills_grandchild(tmp_path):
    pid_file = tmp_path / 'grandchild.pid'
    grandchild = (
        'import os, time; from pathlib import Path; '
        f'Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(60)'
    )
    child = f'import subprocess, sys, time; subprocess.Popen([sys.executable, "-c", {grandchild!r}]); time.sleep(60)'
    parent = f'import subprocess, sys, time; subprocess.Popen([sys.executable, "-c", {child!r}]); time.sleep(60)'
    result = run_process([sys.executable, '-c', parent], str(tmp_path), build_env([]), timeout=2)
    assert result.timed_out is True
    assert result.exit_code is None
    assert pid_file.exists(), 'Grandchild must start before the timeout for this test to be meaningful'
    pid = int(pid_file.read_text())
    try:
        deadline = time.monotonic() + 3
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            # Linux init may retain a terminated orphan as a zombie before reaping it.
            stat_file = Path(f'/proc/{pid}/stat')
            if stat_file.exists() and stat_file.read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                break
            if time.monotonic() >= deadline:
                pytest.fail(f'Grandchild {pid} survived process-group timeout')
            time.sleep(0.05)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_output_truncated(tmp_path):
    result = run_process([sys.executable, '-c', 'print("x" * 1000)'], str(tmp_path), build_env([]),
                         timeout=5, max_output_bytes=20)
    assert result.exit_code == 0
    assert result.truncated is True
    assert result.output == 'x' * 20


def test_output_limit_counts_bytes(tmp_path):
    result = run_process([sys.executable, '-c', 'print("é" * 100)'], str(tmp_path),
                         {**build_env([]), 'PYTHONIOENCODING': 'utf-8'}, timeout=5, max_output_bytes=20)
    assert result.truncated is True
    assert len(result.output.encode('utf-8')) <= 20


def test_build_env_allowlist(monkeypatch):
    monkeypatch.setenv('SECRET_TOKEN', 'private-token')
    monkeypatch.setenv('UNLISTED_VALUE', 'unlisted')
    monkeypatch.setenv('PATH', '/test/path')
    env = build_env([])
    assert env == {k: v for k, v in os.environ.items() if k in BASE_ENV}
    assert env['PATH'] == '/test/path'
    assert 'SECRET_TOKEN' not in env
    assert build_env(['SECRET_TOKEN']) == {**env, 'SECRET_TOKEN': 'private-token'}


def test_stdin_is_eof_without_auto_approve(tmp_path):
    script = 'import sys, json; print(json.dumps([sys.stdin.isatty(), sys.stdin.read()]))'
    result = run_process([sys.executable, '-c', script], str(tmp_path), build_env([]), timeout=3, auto_approve=False)
    assert not result.timed_out
    assert result.exit_code == 0
    assert json.loads(result.output) == [False, '']


def test_mock_writes_files(config, case, tmp_path):
    from agent_eval.models import MockResponse

    case.mock = MockResponse(output='done', files={'nested/result.txt': 'content'})
    runner = AgentRunner(config, str(tmp_path / 'config.yaml'))
    result = runner.run_test_case(case, 'case.yaml', str(tmp_path))
    assert result.output == 'done'
    assert result.exit_code == 0
    assert (tmp_path / 'nested/result.txt').read_text() == 'content'


def test_mock_rejects_traversal(config, case, tmp_path):
    from agent_eval.models import MockResponse

    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    case.mock = MockResponse(files={'../x': 'escaped'})
    runner = AgentRunner(config, str(tmp_path / 'config.yaml'))
    with pytest.raises(PermissionError):
        runner.run_test_case(case, 'case.yaml', str(workspace))
    assert not (tmp_path / 'x').exists()


@pytest.mark.parametrize('expected,status', [({}, 'error'), ({'exit_code': 7}, 'passed')])
def test_nonzero_agent_exit(config, case, tmp_path, expected, status):
    from agent_eval.models import MockResponse

    path = tmp_path / 'case.yaml'
    path.write_text('id: sample\nname: Sample')
    case.mock = MockResponse(exit_code=7)
    case.expected_outputs = expected
    result = run_case(case, str(path), config, AgentRunner(config, str(path)), [])
    assert result['status'] == status
    assert result['exit_code'] == 7
    assert (result['error'] is None) is (status == 'passed')


def test_shell_mode_keeps_template_quoting(tmp_path):
    argv = render_command('printf "%s|" "two words" {value}; echo done', {'value': 'a; touch pwned'}, shell=True)
    result = run_process(argv, str(tmp_path), build_env([]), timeout=5)
    assert result.output == "two words|a; touch pwned|done\n"
    assert not (tmp_path / 'pwned').exists()


def test_background_child_is_killed_after_normal_exit(tmp_path):
    pid_file = tmp_path / 'bg.pid'
    child = f'import os, time; open({str(pid_file)!r}, "w").write(str(os.getpid())); time.sleep(60)'
    parent = (f'import subprocess, sys, time; subprocess.Popen([sys.executable, "-c", {child!r}]); '
              f'[time.sleep(0.05) for _ in range(100) if not __import__("os").path.exists({str(pid_file)!r})]')
    started = time.monotonic()
    result = run_process([sys.executable, '-c', parent], str(tmp_path), build_env([]), timeout=10)
    assert result.exit_code == 0 and time.monotonic() - started < 4
    pid = int(pid_file.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_output_cap_holds_without_newlines(tmp_path):
    code = 'import sys; sys.stdout.write("x" * 5_000_000)'
    result = run_process([sys.executable, '-c', code], str(tmp_path), build_env([]), timeout=10, max_output_bytes=1000)
    assert result.truncated and len(result.output) == 1000


def test_streamed_secret_split_across_writes_is_redacted(tmp_path, monkeypatch):
    import agent_eval.runner as runner
    secret = 'split-secret-value-987654'
    monkeypatch.setenv('SPLIT_API_KEY', secret)
    printed = []
    monkeypatch.setattr(runner.console, 'print', lambda text, **kw: printed.append(text))
    code = (f'import sys, time; sys.stdout.write({secret[:9]!r}); sys.stdout.flush(); time.sleep(0.3); '
            f'sys.stdout.write({secret[9:]!r} + "\\n")')
    run_process([sys.executable, '-c', code], str(tmp_path), build_env([]), timeout=5, stream=True)
    shown = ''.join(printed)
    assert secret not in shown and '[REDACTED]' in shown

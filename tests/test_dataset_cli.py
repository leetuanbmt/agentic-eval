import json
import shutil
import sys

import pytest
from click.testing import CliRunner

from agent_eval import __version__
from agent_eval.cli import cli


def test_quickstart_reports(tmp_path, examples):
    demo = tmp_path / 'quickstart'
    shutil.copytree(examples / 'quickstart', demo)
    md, report = tmp_path / 'report.md', tmp_path / 'report.json'
    result = CliRunner().invoke(cli, ['run', '--config', str(demo / 'eval-config.yaml'),
                                     '--dataset', str(demo / 'dataset'), '--output-report', str(md),
                                     '--output-json', str(report)])
    assert result.exit_code == 1, result.output
    counts = json.loads(report.read_text())['summary']
    assert counts == {'total': 3, 'passed': 2, 'failed': 1, 'error': 0, 'timeout': 0}
    assert 'Total 3' in md.read_text()
    assert 'passed 2 · failed 1' in md.read_text()
    assert 'passed 2 · failed 1' in result.output


@pytest.mark.parametrize('content', ['[]', 'name: missing-id', 'id: ../evil\nname: Evil', 'id: /abs\nname: Evil'])
def test_invalid_dataset_case_exit_two(cli_project, content):
    _, dataset, invoke = cli_project
    (dataset / 'case.yaml').write_text(content)
    assert invoke().exit_code == 2


def test_malformed_dataset_yaml_exit_two(cli_project):
    _, dataset, invoke = cli_project
    (dataset / 'case.yaml').write_text('id: [unterminated')
    assert invoke().exit_code == 2


def test_duplicate_ids_exit_two(cli_project):
    _, dataset, invoke = cli_project
    (dataset / 'duplicate.yml').write_text((dataset / 'case.yaml').read_text())
    result = invoke()
    assert result.exit_code == 2
    assert 'Duplicate test case id' in result.output


def test_empty_dataset_exit_two(cli_project):
    _, dataset, invoke = cli_project
    (dataset / 'case.yaml').unlink()
    assert invoke().exit_code == 2


def test_unknown_evaluator_exit_two(cli_project):
    _, dataset, invoke = cli_project
    (dataset / 'case.yaml').write_text(json.dumps({'id': 'sample', 'name': 'Sample', 'evaluators': ['unknown']}))
    result = invoke()
    assert result.exit_code == 2
    assert 'unknown evaluators' in ' '.join(result.output.split())


def test_command_requires_allow_exec(cli_project, tmp_path):
    path, _, invoke = cli_project
    marker = tmp_path / 'executed'
    command = [sys.executable, '-c', f'from pathlib import Path; Path({str(marker)!r}).touch()']
    path.write_text(json.dumps({'project': {'name': 'Tests'}, 'agent': {'adapter': 'command', 'command': command}}))
    result = invoke()
    assert result.exit_code == 2
    assert '--allow-exec' in result.output
    assert not marker.exists()


def test_invalid_config_exit_two(cli_project):
    path, _, invoke = cli_project
    path.write_text('project: {}\nagent: {adapter: mock}\nunknown: true')
    assert invoke().exit_code == 2


def test_all_pass_exit_zero(cli_project):
    _, _, invoke = cli_project
    assert invoke().exit_code == 0


def test_version():
    result = CliRunner().invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert __version__ in result.output

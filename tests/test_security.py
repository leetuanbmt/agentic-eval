import json
import os
from pathlib import Path

import pytest

from agent_eval.sandbox import SandboxManager
from agent_eval.security import redact, safe_join


@pytest.mark.parametrize('path', ['..', '../outside', '/abs'])
def test_safe_join_rejects_escape(tmp_path, path):
    with pytest.raises(PermissionError):
        safe_join(str(tmp_path), path)


def test_safe_join_nested_path(tmp_path):
    assert safe_join(str(tmp_path), 'nested/file.txt') == str(tmp_path / 'nested/file.txt')


@pytest.mark.skipif(os.name != 'posix', reason='Symlink test requires POSIX')
def test_safe_join_rejects_external_symlink(tmp_path):
    root, outside = tmp_path / 'root', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    (root / 'link').symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError):
        safe_join(str(root), 'link/private')


def test_sandbox_copies_source_context(config, case, tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'source.txt').write_text('original')
    config.project.root = str(project)
    case.inputs = {'source_context': [{'path': 'source.txt'}]}
    sandbox = SandboxManager(case, config)
    try:
        root = Path(sandbox.create())
        assert root.is_relative_to(tmp_path)
        assert (root / 'source.txt').read_text() == 'original'
        (root / 'source.txt').write_text('modified')
        assert (project / 'source.txt').read_text() == 'original'
    finally:
        sandbox.clean()


def test_sandbox_rejects_source_traversal(config, case, tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    (tmp_path / 'outside.txt').write_text('private')
    config.project.root = str(project)
    case.inputs = {'source_context': [{'path': '../outside.txt'}]}
    sandbox = SandboxManager(case, config)
    try:
        with pytest.raises(PermissionError):
            sandbox.create()
    finally:
        sandbox.clean()


def test_source_traversal_cli_case_error(cli_project, tmp_path):
    config_path, dataset, invoke = cli_project
    project = tmp_path / 'project'
    project.mkdir()
    (tmp_path / 'outside.txt').write_text('private')
    config_path.write_text(json.dumps({'project': {'name': 'Tests', 'root': str(project)},
                                       'agent': {'adapter': 'mock'}}))
    (dataset / 'case.yaml').write_text(json.dumps({'id': 'sample', 'name': 'Sample', 'mock': {},
                                                 'inputs': {'source_context': [{'path': '../outside.txt'}]}}))
    result = invoke()
    assert result.exit_code == 1, result.output
    case = json.loads((tmp_path / 'report.json').read_text())['cases'][0]
    assert case['status'] == 'error'
    assert 'PermissionError' in case['error']


@pytest.mark.skipif(os.name != 'posix', reason='Symlink test requires POSIX')
def test_sandbox_removes_external_links_keeps_internal(config, case, tmp_path):
    project = tmp_path / 'project'
    source = project / 'source'
    source.mkdir(parents=True)
    outside = tmp_path / 'outside.txt'
    outside.write_text('private')
    (source / 'inside.txt').write_text('internal')
    (source / 'outside-link').symlink_to(outside)
    (source / 'original-root-link').symlink_to(source / 'inside.txt')
    (source / 'internal-link').symlink_to('inside.txt')
    config.project.root = str(project)
    case.inputs = {'source_context': [{'path': 'source'}]}
    sandbox = SandboxManager(case, config)
    try:
        copied = Path(sandbox.create()) / 'source'
        assert not os.path.lexists(copied / 'outside-link')
        assert not os.path.lexists(copied / 'original-root-link')
        assert (copied / 'internal-link').is_symlink()
        assert (copied / 'internal-link').read_text() == 'internal'
        assert (source / 'outside-link').is_symlink()
        assert (source / 'original-root-link').is_symlink()
    finally:
        sandbox.clean()


def test_clean_only_deletes_owned_temp_directory(config, case, tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    sentinel = project / 'keep.txt'
    sentinel.write_text('keep')
    sibling = tmp_path / 'agent-eval-sample-unrelated'
    sibling.mkdir()
    (sibling / 'keep.txt').write_text('keep sibling')
    config.project.root = str(project)
    sandbox = SandboxManager(case, config)
    sandbox.clean()
    root = Path(sandbox.create())
    (root / 'discard.txt').write_text('discard')
    sandbox.clean()
    sandbox.clean()
    assert not root.exists()
    assert sentinel.read_text() == 'keep'
    assert (sibling / 'keep.txt').read_text() == 'keep sibling'


def test_redact_preserves_short_values():
    assert redact('pin 1234567 true 1', {'API_KEY': '1234567', 'SECRET': 'true', 'TOKEN': '1'}) == 'pin 1234567 true 1'

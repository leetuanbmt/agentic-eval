import builtins
import json
import socket
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from agent_eval.cli import cli
from agent_eval.config import EvalConfig
from agent_eval.models import TestCase


@pytest.fixture(autouse=True)
def offline_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    original_import = builtins.__import__

    def offline_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'openai' or name.startswith('openai.') or name.startswith('google.genai'):
            raise AssertionError(f'Provider SDK import forbidden: {name}')
        if name == 'google' and 'genai' in (fromlist or ()):
            raise AssertionError('Provider SDK import forbidden: google.genai')
        return original_import(name, globals, locals, fromlist, level)

    def no_network(*args, **kwargs):
        raise AssertionError('Network access forbidden in offline tests')

    monkeypatch.setattr(builtins, '__import__', offline_import)
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(socket, 'create_connection', no_network)


@pytest.fixture
def config():
    return EvalConfig(project={'name': 'Tests'}, agent={'adapter': 'mock'})


@pytest.fixture
def case():
    return TestCase(id='sample', name='Sample')


@pytest.fixture
def cli_project(tmp_path):
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(json.dumps({'project': {'name': 'Tests'}, 'agent': {'adapter': 'mock'}}))
    dataset = tmp_path / 'dataset'
    dataset.mkdir()
    (dataset / 'case.yaml').write_text(json.dumps({'id': 'sample', 'name': 'Sample', 'mock': {'output': 'ok'}}))

    def invoke(*extra):
        return CliRunner().invoke(cli, [
            'run', '--config', str(config_path), '--dataset', str(dataset),
            '--output-report', str(tmp_path / 'report.md'),
            '--output-json', str(tmp_path / 'report.json'), *extra,
        ])

    return config_path, dataset, invoke


@pytest.fixture
def examples():
    return Path(__file__).resolve().parents[1] / 'examples'

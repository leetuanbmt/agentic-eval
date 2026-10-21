import json

import pytest
from pydantic import ValidationError

from agent_eval.config import EvalConfig


def test_minimal_mock_config(config):
    assert config.agent.adapter == 'mock'
    assert config.evaluators == []
    assert config.runtime.mode == 'local'


def test_legacy_command_config():
    config = EvalConfig(project={'name': 'Legacy'}, agent_commands={'execute_command': 'echo hello'})
    assert config.agent.adapter == 'command'
    assert config.agent.command == 'echo hello'


@pytest.mark.parametrize('override', [
    {'unknown': True},
    {'evaluators': [{'name': 'x', 'type': 'unknown'}]},
    {'evaluators': [{'name': 'x', 'type': 'contains'}, {'name': 'x', 'type': 'json'}]},
    {'agent': {'adapter': 'command'}},
    {'runtime': {'mode': 'docker'}},
])
def test_invalid_config_rejected(override):
    data = {'project': {'name': 'Tests'}, 'agent': {'adapter': 'mock'}}
    data.update(override)
    with pytest.raises(ValidationError):
        EvalConfig(**data)


def test_project_root_relative_to_config_dir(tmp_path):
    folder = tmp_path / 'config'
    folder.mkdir()
    path = folder / 'eval.yaml'
    path.write_text(json.dumps({'project': {'name': 'Tests', 'root': '../source'}, 'agent': {'adapter': 'mock'}}))
    assert EvalConfig.load_from_yaml(str(path)).project_root == str(tmp_path / 'source')

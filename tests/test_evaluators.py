import json

import pytest

from agent_eval.config import EvaluatorDef
from agent_eval.evaluators import EVALUATORS, LLMJudgeEvaluator
from agent_eval.runner import ExecutionNotAllowed


def evaluate(kind, config, case, tmp_path, output='', allow_exec=False, **definition):
    evaluator = EVALUATORS[kind](EvaluatorDef(name='check', type=kind, **definition), config, allow_exec=allow_exec)
    return evaluator.evaluate(case, output, 0.0, str(tmp_path))


@pytest.mark.parametrize('expected,output,passed,skipped', [
    ({'exact': 'hello'}, ' hello\n', True, False),
    ({'exact': 'hello'}, 'goodbye', False, False),
    ({}, 'anything', True, True),
])
def test_exact_match(config, case, tmp_path, expected, output, passed, skipped):
    case.expected_outputs = expected
    result = evaluate('exact_match', config, case, tmp_path, output)
    assert (result.passed, result.skipped) == (passed, skipped)
    assert result.score == (100.0 if passed and not skipped else 0.0)


def test_contains_partial_score(config, case, tmp_path):
    case.expected_outputs = {'invariants': ['present', 'absent']}
    result = evaluate('contains', config, case, tmp_path, 'present')
    assert not result.passed
    assert result.score == 50.0
    assert result.metrics['missing'] == ['absent']


@pytest.mark.parametrize('output,passed,feedback', [
    ('{"nested": {"ok": true, "extra": 2}, "other": 3}', True, 'matches'),
    ('{"nested": {"ok": false}}', False, '$.nested.ok'),
    ('not json', False, 'not valid JSON'),
])
def test_json_subset(config, case, tmp_path, output, passed, feedback):
    case.expected_outputs = {'json': {'nested': {'ok': True}}}
    result = evaluate('json', config, case, tmp_path, output)
    assert result.passed is passed
    assert feedback in result.feedback


def test_json_workspace_file(config, case, tmp_path):
    (tmp_path / 'answer.json').write_text('{"status": "ok", "extra": 1}')
    case.expected_outputs = {'json': {'status': 'ok'}}
    assert evaluate('json', config, case, tmp_path, 'not JSON', file='answer.json').passed


@pytest.mark.parametrize('kind,expected', [('exact_match', {'exact': 'private'}),
                                          ('contains', {'invariants': ['private']}),
                                          ('json', {'json': {'private': True}})])
@pytest.mark.parametrize('absolute', [False, True])
def test_evaluator_file_cannot_escape(config, case, tmp_path, monkeypatch, kind, expected, absolute):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    outside = tmp_path / 'private.json'
    outside.write_text('{"private": true}')
    case.expected_outputs = expected
    path = str(outside) if absolute else '../private.json'
    # Any attempt to open the outside file must fail the test, even if the evaluator catches it.
    opened = []
    monkeypatch.setattr('builtins.open', lambda *args, **kwargs: opened.append(args[0]))
    with pytest.raises(PermissionError):
        evaluate(kind, config, case, workspace, file=path)
    assert opened == []


@pytest.mark.parametrize('exit_code', [0, 7])
def test_command_evaluator(config, case, tmp_path, exit_code):
    result = evaluate('command', config, case, tmp_path, allow_exec=True,
                      command=['{python}', '-c', f'raise SystemExit({exit_code})'])
    assert result.passed is (exit_code == 0)
    assert result.metrics['exit_code'] == exit_code


def test_command_evaluator_execution_denied(config, case, tmp_path):
    with pytest.raises(ExecutionNotAllowed):
        evaluate('command', config, case, tmp_path, command=['{python}', '-c', 'raise SystemExit(0)'])


@pytest.mark.parametrize('score,claimed,expected_score,passed', [
    (79, True, 79.0, False), (80, False, 80.0, True),
    (-5, True, 0.0, False), (150, False, 100.0, True),
])
def test_llm_threshold_clamp_and_metadata(config, case, tmp_path, monkeypatch, score, claimed, expected_score, passed):
    monkeypatch.setattr(LLMJudgeEvaluator, '_call_llm',
                        lambda self, prompt: (json.dumps({'score': score, 'passed': claimed,
                                                          'feedback': 'stub'}), None))
    result = evaluate('llm_judge', config, case, tmp_path, threshold=80)
    assert result.score == expected_score
    assert result.passed is passed
    assert result.metrics['provider'] == config.llm_judge.default_provider
    assert result.metrics['model'] == config.llm_judge.default_model
    assert result.metrics['temperature'] == config.llm_judge.temperature
    assert result.metrics['nondeterministic'] is True


def test_llm_invalid_json_fails(config, case, tmp_path, monkeypatch):
    monkeypatch.setattr(LLMJudgeEvaluator, '_call_llm', lambda self, prompt: ('not JSON', None))
    result = evaluate('llm_judge', config, case, tmp_path)
    assert not result.passed
    assert 'LLM evaluation failed' in result.feedback


def test_llm_prompt_redacts_secret(config, case, tmp_path, monkeypatch):
    secret = 'long-private-api-key-value'
    monkeypatch.setenv('MY_API_KEY', secret)
    prompts = []

    def call(self, prompt):
        prompts.append(prompt)
        return '{"score": 100}', None

    monkeypatch.setattr(LLMJudgeEvaluator, '_call_llm', call)
    assert evaluate('llm_judge', config, case, tmp_path, f'output {secret}').passed
    assert len(prompts) == 1
    assert secret not in prompts[0]
    assert '[REDACTED]' in prompts[0]


def test_command_evaluator_sandbox_placeholder_not_overridable(tmp_path):
    from agent_eval.config import EvalConfig
    from agent_eval.evaluators import CommandEvaluator
    from agent_eval.models import TestCase
    config = EvalConfig(project={'name': 't'}, agent={'adapter': 'mock'},
                        evaluators=[{'name': 'c', 'type': 'command',
                                     'command': ['{python}', '-c', 'import sys; assert sys.argv[1] == sys.argv[2]',
                                                 '{sandbox}', str(tmp_path)]}])
    case = TestCase(id='c', name='c', inputs={'sandbox': '/etc'})
    res = CommandEvaluator(config.evaluators[0], config, allow_exec=True).evaluate(case, '', 0, str(tmp_path))
    assert res.passed, res.feedback


@pytest.mark.parametrize('endpoint, expected', [(None, 'openai-key'), ('https://evil.example/v1', 'judge-key')])
def test_openai_key_only_sent_to_default_endpoint(monkeypatch, endpoint, expected):
    import builtins
    import importlib
    import sys
    import types
    from agent_eval.config import EvalConfig
    monkeypatch.setattr(builtins, '__import__', importlib.__import__)  # Lift the SDK guard; openai is faked below.
    from agent_eval.evaluators import LLMJudgeEvaluator
    seen = {}
    fake = types.ModuleType('openai')
    fake.OpenAI = lambda base_url, api_key: seen.update(base_url=base_url, api_key=api_key)
    monkeypatch.setitem(sys.modules, 'openai', fake)
    monkeypatch.setenv('OPENAI_API_KEY', 'openai-key')
    monkeypatch.setenv('AGENT_EVAL_JUDGE_API_KEY', 'judge-key')
    config = EvalConfig(project={'name': 't'}, agent={'adapter': 'mock'},
                        llm_judge={'default_provider': 'openai', 'custom_endpoint': endpoint},
                        evaluators=[{'name': 'j', 'type': 'llm_judge'}])
    LLMJudgeEvaluator(config.evaluators[0], config)._setup_client()
    assert seen['api_key'] == expected

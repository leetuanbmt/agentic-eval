import json

import pytest
from click.testing import CliRunner

from agent_eval.cli import cli
from agent_eval.report import build_report, compare, now, render_markdown


def report_case(cid='sample', status='passed', score=100):
    return {'id': cid, 'name': cid, 'status': status, 'duration_seconds': 0.0,
            'error': None, 'output_excerpt': None,
            'evaluators': [{'evaluator_name': 'check', 'score': score, 'passed': status == 'passed',
                            'skipped': False, 'feedback': 'checked'}]}


@pytest.mark.parametrize('current,phrase', [
    ([report_case(status='failed')], 'passed -> failed'),
    ([], 'missing from current run'),
    ([report_case(score=89)], 'score 100.0 -> 89.0'),
])
def test_compare_regressions(current, phrase):
    result = compare({'cases': [report_case()]}, {'cases': current}, score_tolerance=10)
    assert len(result['regressions']) == 1
    assert phrase in result['regressions'][0]


@pytest.mark.parametrize('score', [90, 95, 100])
def test_compare_tolerates_small_drop(score):
    result = compare({'cases': [report_case()]}, {'cases': [report_case(score=score)]}, score_tolerance=10)
    assert result['regressions'] == []


def test_compare_improvements_and_new_cases():
    result = compare({'cases': [report_case(status='failed', score=0)]},
                     {'cases': [report_case(), report_case('new')]})
    assert result == {'regressions': [], 'improvements': ['sample: failed -> passed'], 'new_cases': ['new']}


@pytest.mark.parametrize('status,exit_code', [('failed', 1), ('passed', 0)])
def test_compare_cli(tmp_path, status, exit_code):
    baseline, current = tmp_path / 'baseline.json', tmp_path / 'current.json'
    baseline.write_text(json.dumps({'cases': [report_case()]}))
    current.write_text(json.dumps({'cases': [report_case(status=status)]}))
    result = CliRunner().invoke(cli, ['compare', str(baseline), str(current)])
    assert result.exit_code == exit_code, result.output


@pytest.mark.parametrize('malformed', ['not JSON', '{}', '{"cases": null}'])
def test_compare_cli_invalid_json(tmp_path, malformed):
    baseline, current = tmp_path / 'baseline.json', tmp_path / 'current.json'
    baseline.write_text(json.dumps({'cases': []}))
    current.write_text(malformed)
    assert CliRunner().invoke(cli, ['compare', str(baseline), str(current)]).exit_code == 2


def test_build_report_redacts_secrets(config, tmp_path, monkeypatch):
    secret, patterned = 'private-environment-secret', 'sk-' + 'x' * 24
    monkeypatch.setenv('MY_API_KEY', secret)
    path = tmp_path / 'config.yaml'
    path.write_text('config placeholder')
    case = report_case(status='error')
    text = f'output {secret} and {patterned}'
    case.update(error=text, output_excerpt=text)
    case['evaluators'][0]['feedback'] = text
    report = build_report(config, str(path), [case], now(), 1.0)
    result = report['cases'][0]
    for value in [result['error'], result['output_excerpt'], result['evaluators'][0]['feedback']]:
        assert secret not in value
        assert patterned not in value
        assert value.count('[REDACTED]') == 2


def test_markdown_summary_and_cases(config, tmp_path):
    path = tmp_path / 'config.yaml'
    path.write_text('config placeholder')
    cases = [report_case('first'), report_case('second', status='failed')]
    report = build_report(config, str(path), cases, now(), 1.0)
    markdown = render_markdown(report)
    assert '**Total 2** · passed 1 · failed 1 · errors 0 · timeouts 0' in markdown
    for case in cases:
        assert f"| {case['id']} |" in markdown
        assert f"### Test Case: {case['id']} -" in markdown


def test_secrets_in_evaluator_metrics_are_redacted(monkeypatch, tmp_path):
    secret = 'super-secret-value-123456'
    monkeypatch.setenv('MY_SERVICE_TOKEN', secret)
    from agent_eval.config import EvalConfig
    from agent_eval.evaluators import JsonEvaluator
    from agent_eval.models import TestCase
    config = EvalConfig(project={'name': 't'}, agent={'adapter': 'mock'}, evaluators=[{'name': 'j', 'type': 'json'}])
    case = TestCase(id='c', name='c', expected_outputs={'json': {'token': 'expected'}})
    res = JsonEvaluator(config.evaluators[0], config).evaluate(case, json.dumps({'token': secret}), 0, str(tmp_path))
    assert secret in json.dumps(res.metrics)  # Precondition: the leak path exists.
    path = tmp_path / 'c.yaml'
    path.write_text('id: c')
    config_path = tmp_path / 'cfg.yaml'
    config_path.write_text('x')
    cases = [{'id': 'c', 'name': 'c', 'status': 'failed', 'error': None, 'output_excerpt': None,
              'evaluators': [{'type': 'json', **res.model_dump()}]}]
    report = build_report(config, str(config_path), cases, now(), 0.0)
    assert secret not in json.dumps(report)

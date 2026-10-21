import json
from agent_eval.evaluators.base import BaseEvaluator, EvalResult
from agent_eval.models import TestCase


class ExactMatchEvaluator(BaseEvaluator):
    """Passes when the target equals expected_outputs.exact, ignoring surrounding whitespace."""

    def evaluate(self, test_case: TestCase, run_output: str, run_time: float, sandbox_path: str) -> EvalResult:
        if "exact" not in test_case.expected_outputs:
            return self.skip("no expected_outputs.exact")
        expected = str(test_case.expected_outputs["exact"]).strip()
        actual = self.read_target(run_output, sandbox_path).strip()
        if actual == expected:
            return self.result(True, "Output matches exactly.")
        return self.result(False, f"Expected:\n{expected}\nActual:\n{actual[:2000]}")


class ContainsEvaluator(BaseEvaluator):
    """Scores the share of expected_outputs.invariants found verbatim in the target; passes only if all are."""

    def evaluate(self, test_case: TestCase, run_output: str, run_time: float, sandbox_path: str) -> EvalResult:
        invariants = [str(i) for i in test_case.expected_outputs.get("invariants") or []]
        if not invariants:
            return self.skip("no expected_outputs.invariants")
        text = self.read_target(run_output, sandbox_path)
        missing = [i for i in invariants if i not in text]
        score = 100.0 * (len(invariants) - len(missing)) / len(invariants)
        feedback = "All invariants found." if not missing else "Missing:\n" + "\n".join(f"- {m}" for m in missing)
        return self.result(not missing, feedback, score=score, missing=missing)


def _subset_mismatches(expected, actual, path="$"):
    """Lists where `actual` differs from `expected`; dicts match as subsets, everything else by equality."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {type(actual).__name__}"]
        out = []
        for k, v in expected.items():
            if k not in actual:
                out.append(f"{path}.{k}: missing")
            else:
                out += _subset_mismatches(v, actual[k], f"{path}.{k}")
        return out
    return [] if expected == actual else [f"{path}: expected {expected!r}, got {actual!r}"]


class JsonEvaluator(BaseEvaluator):
    """Parses the target as JSON and checks it contains expected_outputs.json (subset match)."""

    def evaluate(self, test_case: TestCase, run_output: str, run_time: float, sandbox_path: str) -> EvalResult:
        if "json" not in test_case.expected_outputs:
            return self.skip("no expected_outputs.json")
        text = self.read_target(run_output, sandbox_path)
        try:
            actual = json.loads(text)
        except json.JSONDecodeError as e:
            return self.result(False, f"Output is not valid JSON: {e}")
        mismatches = _subset_mismatches(test_case.expected_outputs["json"], actual)
        if mismatches:
            return self.result(False, "JSON mismatches:\n" + "\n".join(mismatches), mismatches=mismatches)
        return self.result(True, "JSON output matches expected fields.")

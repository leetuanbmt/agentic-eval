import os
from abc import ABC, abstractmethod
from typing import Any, Dict
from pydantic import BaseModel, Field
from agent_eval.config import EvalConfig, EvaluatorDef
from agent_eval.models import TestCase
from agent_eval.security import safe_join


class EvalResult(BaseModel):
    evaluator_name: str
    score: float  # Scale 0 to 100
    passed: bool
    feedback: str
    skipped: bool = False  # The test case defines no expectation for this evaluator; excluded from the verdict.
    metrics: Dict[str, Any] = Field(default_factory=dict)


class BaseEvaluator(ABC):
    def __init__(self, evaluator_def: EvaluatorDef, config: EvalConfig, allow_exec: bool = False):
        self.evaluator_def = evaluator_def
        self.config = config
        self.allow_exec = allow_exec

    @abstractmethod
    def evaluate(self, test_case: TestCase, run_output: str, run_time: float, sandbox_path: str) -> EvalResult:
        """
        Evaluates the outputs of an agent run and returns an EvalResult
        """

    def result(self, passed: bool, feedback: str, score: float = None, **metrics) -> EvalResult:
        return EvalResult(evaluator_name=self.evaluator_def.name, passed=passed, feedback=feedback,
                          score=(100.0 if passed else 0.0) if score is None else score, metrics=metrics)

    def skip(self, reason: str) -> EvalResult:
        return EvalResult(evaluator_name=self.evaluator_def.name, score=0.0, passed=True,
                          skipped=True, feedback=f"Skipped: {reason}")

    def read_target(self, run_output: str, sandbox_path: str) -> str:
        """Returns the configured workspace file's content, or the agent output when no file is set."""
        if not self.evaluator_def.file:
            return run_output
        path = safe_join(sandbox_path, self.evaluator_def.file)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Expected file was not generated: {self.evaluator_def.file}")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

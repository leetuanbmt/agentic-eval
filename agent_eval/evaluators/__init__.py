# Evaluators package
from agent_eval.evaluators.base import BaseEvaluator, EvalResult
from agent_eval.evaluators.deterministic import ContainsEvaluator, ExactMatchEvaluator, JsonEvaluator
from agent_eval.evaluators.syntax import CommandEvaluator, SyntaxEvaluator
from agent_eval.evaluators.llm_judge import LLMJudgeEvaluator

# Keys are the `type` values accepted in eval-config.yaml (see config.EVALUATOR_TYPES).
EVALUATORS = {
    "exact_match": ExactMatchEvaluator,
    "contains": ContainsEvaluator,
    "json": JsonEvaluator,
    "command": CommandEvaluator,
    "syntax_checker": SyntaxEvaluator,  # Legacy name for "command".
    "llm_judge": LLMJudgeEvaluator,
}

__all__ = ["BaseEvaluator", "EvalResult", "ContainsEvaluator", "ExactMatchEvaluator", "JsonEvaluator",
           "CommandEvaluator", "SyntaxEvaluator", "LLMJudgeEvaluator", "EVALUATORS"]

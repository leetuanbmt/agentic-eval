import os
import shlex
import sys
from agent_eval.evaluators.base import BaseEvaluator, EvalResult
from agent_eval.models import TestCase
from agent_eval.runner import DOCKER_WORKSPACE, ExecutionNotAllowed, execute, render_command, template_vars


class SyntaxEvaluator(BaseEvaluator):
    """Runs a command in the workspace (e.g. a test suite or linter); passes on exit code 0."""

    def evaluate(self, test_case: TestCase, run_output: str, run_time: float, sandbox_path: str) -> EvalResult:
        if not self.evaluator_def.command:
            return self.skip("no command defined")
        if not self.allow_exec:
            raise ExecutionNotAllowed(f"Evaluator '{self.evaluator_def.name}' runs a command; re-run with --allow-exec")

        variables = template_vars(test_case)
        # Reserved placeholders are set last so test-case inputs with the same name cannot override them.
        docker = self.config.runtime.mode == "docker"
        variables["python"] = "python" if docker else sys.executable
        variables["sandbox"] = DOCKER_WORKSPACE if docker else sandbox_path
        # output_dir: parent directory of the first expected generated file, "." when there is none.
        first = next((f.get("path") for f in test_case.expected_outputs.get("generated_files") or []
                      if isinstance(f, dict) and f.get("path")), None)
        variables["output_dir"] = os.path.dirname(first or "") or "."
        try:
            argv = render_command(self.evaluator_def.command, variables, self.config.agent.shell)
        except KeyError as e:
            return self.result(False, f"Failed to build command: {e}")

        proc = execute(argv, self.config, sandbox_path, self.config.agent.env, self.evaluator_def.timeout_seconds)
        cmd = shlex.join(argv)
        if proc.timed_out:
            return self.result(False, f"Command: {cmd}\nTimed out after {self.evaluator_def.timeout_seconds}s",
                               exit_code=None, timed_out=True)
        passed = proc.exit_code == 0
        feedback = f"Command: {cmd}\nExit Code: {proc.exit_code}\n"
        feedback += "Command passed." if passed else f"Command failed.\nOutput:\n{proc.output[-4000:]}"
        return self.result(passed, feedback, exit_code=proc.exit_code)


CommandEvaluator = SyntaxEvaluator

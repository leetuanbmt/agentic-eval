import os
import shutil
import tempfile
from typing import List
from rich.console import Console
from agent_eval.config import EvalConfig
from agent_eval.models import TestCase
from agent_eval.security import remove_escaping_symlinks, safe_join

console = Console()


class SandboxManager:
    """Per-test-case scratch workspace. This is a working-directory boundary, not an OS sandbox."""

    def __init__(self, test_case: TestCase, config: EvalConfig):
        self.test_case = test_case
        self.config = config
        self.project_root = config.project_root
        self.sandbox_dir = ""
        self.copied_paths: List[str] = []

    def create(self) -> str:
        """Creates a fresh temp workspace with the test case's source_context copied in. Returns its path."""
        # mkdtemp guarantees clean() only ever deletes a directory this run created.
        self.sandbox_dir = os.path.realpath(tempfile.mkdtemp(prefix=f"agent-eval-{self.test_case.id}-"))

        for file_info in self.test_case.inputs.get("source_context", []) or []:
            path = file_info.get("path") if isinstance(file_info, dict) else None
            if not path:
                continue
            src_path = safe_join(self.project_root, path)
            if not os.path.exists(src_path):
                console.print(f"[yellow]Warning: context path not found, skipping:[/yellow] {path}")
                continue
            dest_path = safe_join(self.sandbox_dir, path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            if os.path.isdir(src_path):
                # Symlinks are preserved so link-aware agents see the real layout; escaping ones are dropped below.
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True, symlinks=True)
            else:
                shutil.copy2(src_path, dest_path)
            self.copied_paths.append(path)

        for rel in remove_escaping_symlinks(self.sandbox_dir):
            console.print(f"[yellow]Removed symlink escaping the sandbox:[/yellow] {rel}")
        return self.sandbox_dir

    def clean(self):
        if self.sandbox_dir and os.path.isdir(self.sandbox_dir):
            shutil.rmtree(self.sandbox_dir, ignore_errors=True)

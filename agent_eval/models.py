import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from ruamel.yaml import YAML


class MockResponse(BaseModel):
    """Canned agent behaviour for the offline `mock` adapter."""
    output: str = ""
    exit_code: int = 0
    files: Dict[str, str] = Field(default_factory=dict)  # Workspace-relative path -> content


class TestCase(BaseModel):
    __test__ = False  # Not a pytest test class.

    # The id names report entries and baseline keys, so keep it filesystem- and URL-safe.
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$", max_length=128)
    name: str
    category: str = "general"
    inputs: Dict[str, Any] = Field(default_factory=dict)
    expected_outputs: Dict[str, Any] = Field(default_factory=dict)
    limits: Dict[str, Any] = Field(default_factory=dict)  # timeout_seconds overrides agent.timeout_seconds
    mock: Optional[MockResponse] = None
    evaluators: Optional[List[str]] = None  # Names of config evaluators to apply; default is all of them.

    @classmethod
    def load_from_yaml(cls, path: str) -> "TestCase":
        if not os.path.exists(path):
            raise FileNotFoundError(f"Test case file not found: {path}")
        yaml = YAML(typ="safe")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Test case must be a YAML mapping: {path}")
        return cls(**data)

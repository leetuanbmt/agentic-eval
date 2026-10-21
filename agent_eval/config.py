import os
from typing import List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ruamel.yaml import YAML

EVALUATOR_TYPES = ("exact_match", "contains", "json", "command", "syntax_checker", "llm_judge")


class _Strict(BaseModel):
    # Typos in a config silently disabling a check are worse than a load error.
    model_config = ConfigDict(extra="forbid")


class ProjectConfig(_Strict):
    name: str
    version: str = "0.0.0"
    root: str = "."  # Project root, relative to the config file; source_context paths resolve under it.


class LLMJudgeConfig(_Strict):
    default_provider: str = "google"  # google | openai | anthropic | ollama | custom (OpenAI-compatible)
    default_model: str = "gemini-3.1-flash-lite"
    temperature: float = 0.0
    custom_endpoint: Optional[str] = None


class RuntimeConfig(_Strict):
    mode: Literal["local", "docker"] = "local"
    docker_image: Optional[str] = None
    docker_network: str = "none"
    docker_memory: str = "1g"
    docker_pids_limit: int = 256

    @model_validator(mode="after")
    def _image_required(self):
        if self.mode == "docker" and not self.docker_image:
            raise ValueError("runtime.docker_image is required when runtime.mode is 'docker'")
        return self


class AgentConfig(_Strict):
    adapter: Literal["mock", "command"] = "mock"
    # argv list (preferred) or a string split with shlex. Placeholders: {python}, {sandbox},
    # {test_case_path}, {config}, and test case inputs.
    command: Optional[Union[str, List[str]]] = None
    shell: bool = False  # Opt-in: runs the command through /bin/sh with every substituted value quoted.
    timeout_seconds: float = 300
    max_output_bytes: int = 1_000_000
    env: List[str] = Field(default_factory=list)  # Extra env vars passed to the agent (e.g. API key names).
    auto_approve: bool = False  # Answer "y" when the agent prints a confirmation prompt.

    @model_validator(mode="after")
    def _command_required(self):
        if self.adapter == "command" and not self.command:
            raise ValueError("agent.command is required when agent.adapter is 'command'")
        return self


class AgentCommandsConfig(_Strict):
    """Legacy (pre-0.1) agent section, mapped onto `agent` with adapter=command."""
    execute_command: str
    parse_run_log: Optional[str] = None


class EvaluatorDef(_Strict):
    name: str
    type: Literal[EVALUATOR_TYPES]
    prompt_template: Optional[str] = None  # llm_judge only
    command: Optional[Union[str, List[str]]] = None  # command / syntax_checker only
    file: Optional[str] = None  # exact_match / contains / json: read this workspace file instead of agent output
    threshold: float = 80.0  # llm_judge pass mark (0-100)
    timeout_seconds: float = 120


class EvalConfig(_Strict):
    project: ProjectConfig
    llm_judge: LLMJudgeConfig = Field(default_factory=LLMJudgeConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    agent: Optional[AgentConfig] = None
    agent_commands: Optional[AgentCommandsConfig] = None
    evaluators: List[EvaluatorDef] = Field(default_factory=list)
    config_dir: str = Field(default=".", exclude=True)

    @model_validator(mode="after")
    def _resolve_agent(self):
        if self.agent and self.agent_commands:
            raise ValueError("Use either 'agent' or the legacy 'agent_commands', not both")
        if self.agent is None:
            if self.agent_commands:
                self.agent = AgentConfig(adapter="command", command=self.agent_commands.execute_command)
            else:
                raise ValueError("Missing 'agent' section")
        names = [e.name for e in self.evaluators]
        if len(names) != len(set(names)):
            raise ValueError("Evaluator names must be unique")
        return self

    @property
    def project_root(self) -> str:
        return os.path.abspath(os.path.join(self.config_dir, self.project.root))

    @classmethod
    def load_from_yaml(cls, path: str) -> "EvalConfig":
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        yaml = YAML(typ="safe")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Config must be a YAML mapping: {path}")
        data["config_dir"] = os.path.dirname(os.path.abspath(path))
        return cls(**data)

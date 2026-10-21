"""Example LLM agent (Gemini + function calling) evaluated through the `command` adapter.

Tools are confined to the workspace with agent_eval.security.safe_join. The shell tool is
disabled unless --allow-shell-tool is passed, because it runs model-generated commands on the host.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from agent_eval.models import TestCase
from agent_eval.security import safe_join

WORKSPACE = ""
ALLOW_SHELL = False
DEFAULT_SYSTEM_PROMPT = "You are a careful AI software engineer working inside an isolated workspace."


def read_file(path: str) -> str:
    """Reads a text file in the workspace.

    Args:
        path: Path relative to the workspace root.
    """
    try:
        with open(safe_join(WORKSPACE, path), "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(path: str, content: str) -> str:
    """Writes a text file in the workspace, creating parent directories.

    Args:
        path: Path relative to the workspace root.
        content: Full file content.
    """
    try:
        resolved = safe_join(WORKSPACE, path)
        os.makedirs(os.path.dirname(resolved), exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def run_command(command: str) -> str:
    """Runs a shell command with the workspace as working directory (60s limit).

    Args:
        command: The command line to run.
    """
    if not ALLOW_SHELL:
        return "Error: shell tool is disabled for this run."
    try:
        p = subprocess.run(command, shell=True, cwd=WORKSPACE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=60)
        return f"Command exit code: {p.returncode}\nOutput:\n{p.stdout[-10000:]}"
    except subprocess.TimeoutExpired:
        return "Error: command timed out (60s limit)."


def main():
    global WORKSPACE, ALLOW_SHELL
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-case", required=True, help="Path to test case yaml")
    parser.add_argument("--sandbox", required=True, help="Workspace directory")
    parser.add_argument("--model", default="gemini-3.1-flash-lite")
    parser.add_argument("--allow-shell-tool", action="store_true")
    args = parser.parse_args()
    WORKSPACE = os.path.realpath(args.sandbox)
    ALLOW_SHELL = args.allow_shell_tool

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("This example needs: pip install 'agentic-eval[gemini]'")
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("Error: GEMINI_API_KEY or GOOGLE_API_KEY is not set.")

    test_case = TestCase.load_from_yaml(args.test_case)
    # An AGENTS.md copied into the workspace via source_context becomes the system prompt.
    instructions = read_file("AGENTS.md")
    system_prompt = DEFAULT_SYSTEM_PROMPT if instructions.startswith("Error") else instructions
    prompt = (f"Complete this task inside the workspace using the available tools.\n"
              f"Task: {test_case.name}\nInputs: {json.dumps(test_case.inputs, ensure_ascii=False)}")

    client = genai.Client(api_key=api_key)
    chat = client.chats.create(model=args.model, config=types.GenerateContentConfig(
        system_instruction=system_prompt, tools=[read_file, write_file, run_command]))
    for attempt in range(4):
        try:
            response = chat.send_message(prompt)
            break
        except Exception as e:
            if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e):
                raise
            wait = (attempt + 1) * 15
            print(f"[agent] Rate limited, retrying in {wait}s ({attempt + 1}/4)", flush=True)
            time.sleep(wait)
    else:
        sys.exit("Error: no response from Gemini after retries.")

    print(response.text or "")
    usage = response.usage_metadata
    if usage:
        print(f"[agent] tokens: prompt={usage.prompt_token_count} output={usage.candidates_token_count}")


if __name__ == "__main__":
    main()

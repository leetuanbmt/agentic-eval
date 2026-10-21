"""Path containment and secret redaction shared by every component that touches files or reports."""
import os
import re

# Env var names whose values are treated as secrets and scrubbed from logs and reports.
SECRET_ENV_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSW|CREDENTIAL|AUTH", re.IGNORECASE)
# Well-known credential shapes, scrubbed even if they never appeared in the environment.
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),  # OpenAI / Anthropic style keys
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),  # Google API keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),  # GitHub tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key ids
]
REDACTED = "[REDACTED]"


def is_within(root: str, path: str) -> bool:
    root = os.path.realpath(root)
    path = os.path.realpath(path)
    return os.path.commonpath([root, path]) == root


def safe_join(root: str, rel_path: str) -> str:
    """Resolves `rel_path` under `root`, following symlinks; raises if the result escapes `root`."""
    if not isinstance(rel_path, str) or not rel_path:
        raise ValueError(f"Invalid path: {rel_path!r}")
    if os.path.isabs(rel_path) or os.path.splitdrive(rel_path)[0]:
        raise PermissionError(f"Absolute paths are not allowed: {rel_path}")
    real_root = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(real_root, rel_path))
    if os.path.commonpath([real_root, candidate]) != real_root:
        raise PermissionError(f"Path escapes {real_root}: {rel_path}")
    return candidate


def remove_escaping_symlinks(root: str) -> list:
    """Deletes symlinks under `root` that resolve outside it; returns their paths relative to `root`."""
    removed = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            if os.path.islink(p) and not is_within(root, p):
                os.unlink(p)
                removed.append(os.path.relpath(p, root))
    return removed


def redact(text: str, env: dict = None) -> str:
    if not text:
        return text
    env = os.environ if env is None else env
    # Short values (e.g. "1", "true") would mangle unrelated text, so only redact substantial ones.
    for name, value in env.items():
        if SECRET_ENV_NAME.search(name) and value and len(value) >= 8:
            text = text.replace(value, REDACTED)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text

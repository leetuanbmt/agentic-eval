import shutil
import subprocess
import pytest
from agent_eval.config import EvalConfig
from agent_eval.runner import execute

IMAGE = "python:3.12-slim"


def _docker_ready():
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(not _docker_ready(), reason=f"docker or image {IMAGE} unavailable")


def _config():
    return EvalConfig(project={"name": "t"}, agent={"adapter": "mock"},
                      runtime={"mode": "docker", "docker_image": IMAGE})


def test_network_is_disabled(tmp_path):
    code = "import socket; socket.create_connection(('1.1.1.1', 53), timeout=3); print('CONNECTED')"
    r = execute(["python", "-c", code], _config(), str(tmp_path), [], timeout=60)
    assert r.exit_code != 0 and "CONNECTED" not in r.output


def test_only_workspace_is_writable_and_owned_by_host_user(tmp_path):
    r = execute(["python", "-c", "open('out.txt', 'w').write('x')"], _config(), str(tmp_path), [], timeout=60)
    assert r.exit_code == 0
    assert (tmp_path / "out.txt").read_text() == "x"
    shutil.rmtree(tmp_path)  # Fails if the container left root-owned files behind.


def test_timeout_kills_container(tmp_path):
    r = execute(["python", "-c", "import time; time.sleep(60)"], _config(), str(tmp_path), [], timeout=2)
    assert r.timed_out
    left = subprocess.run(["docker", "ps", "-q", "--filter", "ancestor=" + IMAGE], capture_output=True, text=True)
    assert left.stdout.strip() == ""

"""
E2E test fixtures — spin up the full docker-compose stack and tear it down.
"""
import subprocess
import time
from pathlib import Path

import pytest
import requests

COMPOSE_DIR = Path(__file__).parent.parent.parent  # src/
API_URL = "http://localhost:8000"


def _wait_for_healthy(url: str, timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"{url} did not become healthy within {timeout}s")


@pytest.fixture(scope="session", autouse=True)
def docker_stack():
    subprocess.run(
        ["docker-compose", "up", "-d", "--build"],
        cwd=COMPOSE_DIR,
        check=True,
    )
    _wait_for_healthy(f"{API_URL}/health")
    yield
    subprocess.run(
        ["docker-compose", "down", "-v"],
        cwd=COMPOSE_DIR,
        check=True,
    )

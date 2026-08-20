from pathlib import Path

import pytest

from _paths import ROOT, venv_python

PYTHON = venv_python()


@pytest.fixture
def good_server_cmd() -> list[str]:
    return [PYTHON, str(ROOT / "demo" / "good_server.py")]


@pytest.fixture
def bad_server_cmd() -> list[str]:
    return [PYTHON, str(ROOT / "demo" / "bad_server.py")]

"""Shared test paths: venv python on any platform, falling back to the
running interpreter (lets CI run without a .venv)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def venv_python() -> str:
    for cand in (
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".venv" / "Scripts" / "python.exe",
    ):
        if cand.exists():
            return str(cand)
    return sys.executable

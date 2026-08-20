import os
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from _paths import venv_python

from mcpproof.client_http import HttpProbe, open_session_http

PYTHON = venv_python()
SERVER = str(Path(__file__).resolve().parent / "http_target_server.py")

BOOT_DEADLINE = 15.0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _server_unavailable(reason: str):
    """Local dev without the target's env may skip; CI must never silently
    lose HTTP transport coverage — a green run has to mean these tests ran."""
    if os.environ.get("CI"):
        pytest.fail(f"HTTP target server must boot in CI — {reason}")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def http_url():
    port = _free_port()
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        proc = subprocess.Popen(
            [PYTHON, SERVER, str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        _server_unavailable(f"could not spawn HTTP target server: {exc}")
    try:
        deadline = time.monotonic() + BOOT_DEADLINE
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                httpx.get(url, timeout=1.0)
                ready = True
                break
            except httpx.TransportError:
                time.sleep(0.15)
        if not ready:
            _server_unavailable("HTTP target server failed to boot")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


async def test_http_probe_initialize_negotiates(http_url):
    async with HttpProbe(http_url) as probe:
        resp = await probe.initialize()
        assert resp is not None
        assert resp.get("jsonrpc") == "2.0"
        result = resp["result"]
        assert result["protocolVersion"]
        assert "serverInfo" in result
        assert probe.session_id is not None
        assert probe.transport == "http"
        assert probe.non_jsonrpc_stdout == []


async def test_http_probe_lists_tools(http_url):
    async with HttpProbe(http_url) as probe:
        assert await probe.initialize() is not None
        resp = await probe.request("tools/list")
        assert resp is not None
        names = {t["name"] for t in resp["result"]["tools"]}
        assert names == {"echo", "price"}


async def test_http_probe_unknown_method_gets_error_envelope(http_url):
    async with HttpProbe(http_url) as probe:
        assert await probe.initialize() is not None
        resp = await probe.request("mcpproof/nonexistent")
        assert resp is not None
        assert "error" in resp
        assert isinstance(resp["error"]["code"], int)


async def test_open_session_http_lists_and_calls_tools(http_url):
    async with open_session_http(http_url) as session:
        assert session.mcp_proof_init is not None
        tools = await session.list_tools()
        assert {t.name for t in tools.tools} == {"echo", "price"}
        result = await session.call_tool("price", {"item": "widget"})
        text = "".join(c.text for c in result.content if c.type == "text")
        assert "$42.00" in text


async def test_http_probe_dead_port_returns_none():
    url = f"http://127.0.0.1:{_free_port()}/mcp"
    async with HttpProbe(url, timeout=3) as probe:
        assert await probe.initialize() is None


def test_cli_run_over_http_produces_report(http_url, tmp_path):
    import subprocess

    from _paths import ROOT, venv_python

    out = tmp_path / "report.html"
    proc = subprocess.run(
        [venv_python(), "-m", "mcpproof.cli", "run", "--url", http_url,
         "--fixtures", str(tmp_path / "fx"), "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    html = out.read_text(encoding="utf-8")
    assert "SHIP-READY" in html and "NOT SHIP-READY" not in html
    assert "stdout hygiene only applies to the stdio transport" in html
    assert "--url" in html

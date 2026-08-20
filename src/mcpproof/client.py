"""Two ways to talk to a server under test.

RawProbe speaks newline-delimited JSON-RPC over stdio directly so checks can
observe wire-level behaviour the SDK would normalize away: exact error codes,
stdout pollution, and the negotiated protocol revision.

open_session wraps the official SDK for high-level work (tool calls,
regression recording) where protocol plumbing is not the thing being tested.
"""

import asyncio
import json
from collections import deque
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import LATEST_LEGACY_SPEC, __version__

DEFAULT_TIMEOUT = 15.0

STDERR_TAIL_LINES = 100


class RawProbe:
    def __init__(self, cmd: list[str], timeout: float = DEFAULT_TIMEOUT):
        self.cmd = cmd
        self.timeout = timeout
        self.non_jsonrpc_stdout: list[str] = []
        self.server_messages: list[dict] = []
        # last N stderr lines: the only diagnostics a crashed server leaves behind
        self.stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int | str, asyncio.Future] = {}
        self._next_id = 0
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None

    async def __aenter__(self) -> "RawProbe":
        self._proc = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        return self

    async def __aexit__(self, *exc) -> None:
        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except TimeoutError:
                self._proc.kill()
                await self._proc.wait()

    async def _read_stdout(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            if not text.strip():
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                self.non_jsonrpc_stdout.append(text)
                continue
            if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                self.non_jsonrpc_stdout.append(text)
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                fut = self._pending.pop(msg["id"], None)
                if fut and not fut.done():
                    fut.set_result(msg)
                else:
                    self.server_messages.append(msg)
            elif "id" in msg and "method" in msg:
                # server-initiated request: refuse politely so it can't hang us
                await self._write(
                    {
                        "jsonrpc": "2.0",
                        "id": msg["id"],
                        "error": {"code": -32601, "message": "Method not found"},
                    }
                )
                self.server_messages.append(msg)
            else:
                self.server_messages.append(msg)
        # stdout EOF: the server is gone; fail waiters now instead of
        # letting each pending request ride out its full timeout
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    async def _read_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                break
            self.stderr_tail.append(line.decode("utf-8", errors="replace").rstrip())

    async def _write(self, obj: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def request(
        self, method: str, params: dict | None = None, timeout: float | None = None
    ) -> dict | None:
        """Send a request; return the raw response envelope, or None on
        timeout, closed transport, or dead server process."""
        self._next_id += 1
        req_id = self._next_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut
        msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        try:
            await self._write(msg)
            return await asyncio.wait_for(fut, timeout or self.timeout)
        except (TimeoutError, asyncio.CancelledError, OSError):
            self._pending.pop(req_id, None)
            return None

    async def notify(self, method: str, params: dict | None = None) -> None:
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        try:
            await self._write(msg)
        except OSError:
            pass

    async def initialize(self, protocol_version: str = LATEST_LEGACY_SPEC) -> dict | None:
        """Legacy-era handshake requesting the newest revision it can carry,
        so the response reveals which revision the server negotiates."""
        resp = await self.request(
            "initialize",
            {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "mcp-proof", "version": __version__},
            },
        )
        if resp is not None and "result" in resp:
            await self.notify("notifications/initialized")
        return resp

    async def failure_context(self) -> str:
        """Exit code and stderr tail for evidence when the probe got nothing back."""
        parts: list[str] = []
        if self._proc is not None:
            if self._proc.returncode is None:
                try:  # a just-crashed child may not be reaped yet
                    await asyncio.wait_for(self._proc.wait(), timeout=0.5)
                except TimeoutError:
                    pass
            if self._proc.returncode is not None:
                parts.append(f"server process exited with code {self._proc.returncode}")
        tail = list(self.stderr_tail)
        if tail:
            parts.append("stderr tail: " + " | ".join(tail[-5:]))
        return "; ".join(parts)


@asynccontextmanager
async def open_session(cmd: list[str]):
    """Official-SDK session for high-level tool interaction."""
    params = StdioServerParameters(command=cmd[0], args=cmd[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            session.mcp_proof_init = init  # stash for callers that need metadata
            yield session

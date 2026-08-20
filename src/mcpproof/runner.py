"""Orchestrates the lanes behind the CLI commands."""

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .checks.base import FAIL, MUST
from .client import RawProbe
from .report.builder import build_report


def _find_chrome() -> str | None:
    mac_apps = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    if sys.platform == "darwin":
        for p in mac_apps:
            if Path(p).exists():
                return p
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _export_pdf(html_path: Path) -> Path | None:
    chrome = _find_chrome()
    if not chrome:
        print("⚠ --pdf: no Chrome/Chromium found; open the HTML in any browser and print to PDF")
        return None
    pdf_path = html_path.with_suffix(".pdf")
    try:
        subprocess.run(
            [chrome, "--headless", "--disable-gpu",
             f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer",
             html_path.resolve().as_uri()],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"⚠ --pdf export failed: {exc}")
        return None
    return pdf_path


def _probe_ctx(cmd: list[str] | None, url: str | None):
    if url:
        from .client_http import HttpProbe

        return HttpProbe(url)
    return RawProbe(cmd)


async def _meta_probe(
    cmd: list[str] | None, url: str | None = None
) -> tuple[str | None, str | None, list[dict]]:
    """One quick handshake: negotiated protocol, server-reported name, tool list."""
    async with _probe_ctx(cmd, url) as p:
        init = await p.initialize()
        if not init or "result" not in init:
            return None, None, []
        result = init["result"]
        negotiated = result.get("protocolVersion")
        name = (result.get("serverInfo") or {}).get("name")
        tools_resp = await p.request("tools/list")
        tools = []
        if tools_resp and "result" in tools_resp:
            tools = tools_resp["result"].get("tools", [])
        return negotiated, name, tools


async def _cmd_run(args) -> int:
    from .checks.conformance import run_conformance
    from .checks.security import run_security
    from .regression.ci_template import github_action_yaml
    from .regression.recorder import record
    from .regression.replayer import replay, summarize

    cmd = args.server_cmd or None
    url = getattr(args, "url", None)
    if getattr(args, "semantic", False):
        print("note: --semantic (LLM lane) is reserved for a future release — skipping it; "
              "all lanes below are deterministic")
    negotiated, reported_name, tools = await _meta_probe(cmd, url)
    if args.server_name:
        server_name = args.server_name
    elif reported_name:
        server_name = reported_name
    elif cmd:
        server_name = Path(cmd[-1]).stem
    else:
        from urllib.parse import urlparse

        server_name = urlparse(url).hostname or url

    print(f"→ conformance lane ({server_name})")
    conf = await run_conformance(cmd, url=url)
    print(f"→ security lane ({len(tools)} tools)")
    sec = run_security(tools)

    regression = None
    if args.fixtures:
        fdir = Path(args.fixtures)
        manifest = fdir / "_manifest.json"
        if not manifest.exists():
            print(f"→ regression lane: no baseline at {fdir}, recording one")
            skipped: list[str] = []
            await record(cmd, fdir, include_destructive=args.include_destructive,
                         skipped_out=skipped, edge_cases=getattr(args, "edge_cases", False),
                         url=url)
            if skipped:
                print(f"  ⚠ skipped {len(skipped)} potentially destructive tool(s): "
                      f"{', '.join(skipped)} (--include-destructive to record them)")
        print("→ regression lane: replaying fixtures")
        drifts = await replay(cmd, fdir, url=url)
        fixtures_sha = ""
        if manifest.exists():
            fixtures_sha = json.loads(manifest.read_text()).get("fixtures_sha256", "")
        regression = {
            "summary": summarize(drifts),
            "drifts": drifts,
            "fixtures_sha256": fixtures_sha,
            "fixtures_dir": str(fdir),
            "action_yaml": github_action_yaml(cmd, str(fdir), url=url),
        }

    out = build_report(
        server_name=server_name,
        server_cmd=cmd if cmd else ["--url", url],
        negotiated_protocol=negotiated,
        conformance=conf,
        security=sec,
        regression=regression,
        out_path=args.out,
    )

    if getattr(args, "pdf", False):
        pdf = _export_pdf(Path(args.out))
        if pdf:
            print(f"✓ PDF written: {pdf}")

    must_fails = [r for r in conf if r.level == MUST and r.status == FAIL]
    sec_fails = [r for r in sec if r.status == FAIL]
    gate_ok = not must_fails and not sec_fails and (
        regression is None or regression["summary"]["gate_pass"]
    )
    print(f"✓ report written: {out}")
    line = f"  conformance MUST failures: {len(must_fails)} | security findings: {len(sec_fails)}"
    if regression:
        line += f" | drift gate: {'PASS' if regression['summary']['gate_pass'] else 'FAIL'}"
    print(line)
    return 0 if gate_ok else 1


async def _cmd_record(args) -> int:
    from .regression.recorder import record

    skipped: list[str] = []
    paths = await record(args.server_cmd or None, Path(args.fixtures),
                         include_destructive=args.include_destructive, skipped_out=skipped,
                         edge_cases=getattr(args, "edge_cases", False),
                         url=getattr(args, "url", None))
    print(f"✓ recorded {len(paths)} fixtures into {args.fixtures}")
    if skipped:
        print(f"⚠ skipped {len(skipped)} potentially destructive tool(s): "
              f"{', '.join(skipped)} (--include-destructive to record them)")
    return 0


async def _cmd_replay(args) -> int:
    from .regression.replayer import replay, summarize

    drifts = await replay(args.server_cmd or None, Path(args.fixtures),
                          url=getattr(args, "url", None))
    summary = summarize(drifts)
    for d in drifts:
        if d.kind != "OK":
            print(f"[{d.kind}] {d.tool} ({d.fixture}): {d.detail}")
    gate = "PASS" if summary["gate_pass"] else "FAIL"
    line = f"replay: {summary['ok']} clean / {summary['content_total']} · gate {gate}"
    if summary["latency"]:
        line += f" · {summary['latency']} latency advisor{'y' if summary['latency'] == 1 else 'ies'}"
    print(line)
    return 0 if summary["gate_pass"] else 1


def dispatch(args) -> int:
    handler = {"run": _cmd_run, "record": _cmd_record, "replay": _cmd_replay}[args.command]
    return asyncio.run(handler(args))

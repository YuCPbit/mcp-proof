"""Orchestrates the lanes behind the CLI commands."""

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .checks.base import FAIL, MUST
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


async def _regression_lane(args, cmd: list[str] | None, url: str | None, era: str = "auto") -> dict:
    from .regression.ci_template import github_action_yaml
    from .regression.recorder import record
    from .regression.replayer import replay, summarize

    fdir = Path(args.fixtures)
    manifest = fdir / "_manifest.json"
    if not manifest.exists():
        print(f"→ regression lane: no baseline at {fdir}, recording one")
        skipped: list[str] = []
        unsynthesizable: list[str] = []
        await record(cmd, fdir, include_destructive=args.include_destructive,
                     skipped_out=skipped, edge_cases=getattr(args, "edge_cases", False),
                     url=url, era=era, synthesis_skipped_out=unsynthesizable)
        if skipped:
            print(f"  ⚠ skipped {len(skipped)} potentially destructive tool(s): "
                  f"{', '.join(skipped)} (--include-destructive to record them)")
        if unsynthesizable:
            print(f"  ⚠ skipped {len(unsynthesizable)} tool(s) with no schema-valid "
                  f"synthesizable arguments: {'; '.join(unsynthesizable)}")
    print("→ regression lane: replaying fixtures")
    drifts = await replay(cmd, fdir, url=url, era=era)
    fixtures_sha = ""
    if manifest.exists():
        fixtures_sha = json.loads(manifest.read_text()).get("fixtures_sha256", "")
    return {
        "summary": summarize(drifts),
        "drifts": drifts,
        "fixtures_sha256": fixtures_sha,
        "fixtures_dir": str(fdir),
        "action_yaml": github_action_yaml(cmd, str(fdir), url=url),
    }


async def _cmd_run(args) -> int:
    from .checks.conformance import run_conformance
    from .checks.security import run_security

    cmd = args.server_cmd or None
    url = getattr(args, "url", None)
    if getattr(args, "semantic", False):
        print("note: --semantic (LLM lane) is reserved for a future release — skipping it; "
              "all lanes below are deterministic")

    print(f"→ conformance lane (era: {getattr(args, 'era', 'auto')})")
    outcome = await run_conformance(cmd, url=url, era=getattr(args, "era", "auto"))
    conf = outcome.results
    tools = outcome.tools

    if args.server_name:
        server_name = args.server_name
    elif outcome.server_name:
        server_name = outcome.server_name
    elif cmd:
        server_name = Path(cmd[-1]).stem
    else:
        from urllib.parse import urlparse

        server_name = urlparse(url).hostname or url

    print(f"  {server_name}: {outcome.era} era"
          + (f", revision {outcome.revision}" if outcome.revision else ""))
    print(f"→ security lane ({len(tools)} tools)")
    sec = run_security(tools)

    regression = None
    if args.fixtures:
        # the conformance lane already learned the era — the regression lane
        # rides the same verdict instead of sniffing again
        regression = await _regression_lane(args, cmd, url, era=outcome.era)

    out = build_report(
        server_name=server_name,
        server_cmd=cmd if cmd else ["--url", url],
        negotiated_protocol=outcome.revision,
        protocol_era=outcome.era,
        discovery=outcome.discovery,
        conformance=conf,
        security=sec,
        regression=regression,
        out_path=args.out,
        json_path=getattr(args, "json", None),
        junit_path=getattr(args, "junit", None),
        sarif_path=getattr(args, "sarif", None),
    )
    for label, path in (("JSON", getattr(args, "json", None)),
                        ("JUnit", getattr(args, "junit", None)),
                        ("SARIF", getattr(args, "sarif", None))):
        if path:
            print(f"✓ {label} written: {path}")

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


async def _cmd_inspect(args) -> int:
    from .contract import capture_manifest

    manifest = await capture_manifest(
        args.server_cmd or None, url=getattr(args, "url", None),
        era=getattr(args, "era", "auto"),
    )
    out = Path(args.out)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    srv = manifest["server"]
    print(f"✓ contract manifest written: {out}")
    print(f"  {srv.get('name')} · {srv.get('era')} era · revision {srv.get('revision')}")
    print(f"  tools {len(manifest['tools'])} · resources {len(manifest['resources'])}"
          f" · prompts {len(manifest['prompts'])}")
    print(f"  contract sha256 {manifest['contract_sha256'][:16]}…")
    return 0


async def _cmd_diff(args) -> int:
    from .contract import diff_manifests, has_breaking

    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    current = json.loads(Path(args.current).read_text(encoding="utf-8"))
    changes = diff_manifests(base, current)
    if not changes:
        print("contract unchanged"
              f" (sha256 {current.get('contract_sha256', '')[:16]}…)")
        return 0
    for level in ("BREAKING", "ADDITIVE", "METADATA"):
        rows = [c for c in changes if c["level"] == level]
        if not rows:
            continue
        print(level)
        marker = {"BREAKING": "-", "ADDITIVE": "+", "METADATA": "~"}[level]
        for c in rows:
            print(f"{marker} {c['ref']}: {c['detail']}")
    fail_on = getattr(args, "fail_on", "breaking")
    if fail_on == "never":
        return 0
    if fail_on == "any":
        return 1
    return 1 if has_breaking(changes) else 0


async def _cmd_plan(args) -> int:
    """Which tools would auto-baselining call, and on what basis."""
    from .regression.recorder import _session_ctx, classify_tool, list_all_tools

    cmd = args.server_cmd or None
    url = getattr(args, "url", None)
    async with await _session_ctx(cmd, url, getattr(args, "era", "auto")) as session:
        tools = await list_all_tools(session)
    rows = [
        (t.name, *classify_tool(t.name, t.description, getattr(t, "annotations", None)))
        for t in tools
    ]
    auto = [(n, r) for n, d, r in rows if d == "auto"]
    skip = [(n, r) for n, d, r in rows if d == "skip"]
    width = max((len(n) for n, _, _ in rows), default=0)
    print(f"AUTO-CALL ({len(auto)})")
    for n, r in sorted(auto, key=lambda x: (not x[1].startswith("annotation"), x[0])):
        print(f"  ✓ {n:<{width}}  {r}")
    print(f"SKIPPED ({len(skip)})")
    for n, r in sorted(skip, key=lambda x: (not x[1].startswith("annotation"), x[0])):
        print(f"  × {n:<{width}}  {r}")
    print("\nrecord/run auto-call only the AUTO-CALL set; review this plan before "
          "auditing production, and use --include-destructive to record the rest.")
    return 0


async def _cmd_record(args) -> int:
    from .regression.recorder import record

    skipped: list[str] = []
    unsynthesizable: list[str] = []
    paths = await record(args.server_cmd or None, Path(args.fixtures),
                         include_destructive=args.include_destructive, skipped_out=skipped,
                         edge_cases=getattr(args, "edge_cases", False),
                         url=getattr(args, "url", None), era=getattr(args, "era", "auto"),
                         synthesis_skipped_out=unsynthesizable)
    print(f"✓ recorded {len(paths)} fixtures into {args.fixtures}")
    if skipped:
        print(f"⚠ skipped {len(skipped)} potentially destructive tool(s): "
              f"{', '.join(skipped)} (--include-destructive to record them)")
    if unsynthesizable:
        print(f"⚠ skipped {len(unsynthesizable)} tool(s) with no schema-valid "
              f"synthesizable arguments: {'; '.join(unsynthesizable)}")
    return 0


async def _cmd_replay(args) -> int:
    from .regression.replayer import replay, summarize

    drifts = await replay(args.server_cmd or None, Path(args.fixtures),
                          url=getattr(args, "url", None), era=getattr(args, "era", "auto"))
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
    handler = {
        "run": _cmd_run, "record": _cmd_record, "replay": _cmd_replay,
        "plan": _cmd_plan, "inspect": _cmd_inspect, "diff": _cmd_diff,
    }[args.command]
    return asyncio.run(handler(args))

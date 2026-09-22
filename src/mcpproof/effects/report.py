"""Render an effect-evidence report: declared effect semantics beside the
externally observed effect, the evidence for each, the objects that resulted,
and where authority/effectiveness was probed.

Self-contained HTML in the delivery report's visual language, but a distinct
document — the deterministic delivery report (fingerprinted, fixed schema) is
left untouched. A reader should be able to see, per call: (1) what the tool
declared, (2) what was actually observed out-of-band, (3) the evidence, (4)
what persistent objects resulted, (5) where authority/effectiveness was probed.
"""

from __future__ import annotations

import html
import json

from ..checks.base import FAIL, PASS, SKIP, WARN
from .model import A_YES, EffectRecord

_WRITE = ("create", "update", "delete")


def _badge(status: str) -> str:
    cls = {PASS: "pass", FAIL: "fail", WARN: "warn", SKIP: "skip"}.get(status, "skip")
    sym = {PASS: "✓ PASS", FAIL: "✗ FAIL", WARN: "! WARN", SKIP: "– SKIP"}.get(status, status)
    return f'<span class="badge {cls}">{sym}</span>'


def _e(s) -> str:
    return html.escape(str(s))


def _contradiction(rec: EffectRecord) -> str | None:
    ro = rec.declared.get("readOnlyHint") is True
    de = rec.declared.get("destructiveHint") is True
    if ro and rec.effect_type.value in _WRITE:
        extra = " and minted authority" if rec.authority_bearing.value == A_YES else ""
        return f"declared read-only, but observed a {rec.effect_type.value}{extra}"
    if rec.effect_type.value == "delete" and not de:
        return "deleted external state without declaring destructiveHint"
    return None


def render_effect_report(
    server_name: str,
    records: list[EffectRecord],
    checks: list,
    *,
    observer_desc: str,
    probe_desc: str,
    mutations: list[str] | None = None,
) -> str:
    fails = sum(1 for c in checks if c.status == FAIL)
    warns = sum(1 for c in checks if c.status == WARN)
    contradictions = [(r, c) for r in records if (c := _contradiction(r))]
    authority_objs = [r for r in records if r.authority_bearing.value == A_YES]

    rows_checks = "".join(
        f'<tr data-status="{c.status}"><td class="id">{_e(c.id)}</td>'
        f'<td class="lvl">{_e(c.level)}</td><td>{_badge(c.status)}</td>'
        f'<td><div class="ttl">{_e(c.title)}</div>'
        f'{f"<div class=ev>{_e(c.evidence)}</div>" if c.evidence else ""}'
        f'{f"<div class=fix><b>Fix:</b> {_e(c.fix_hint)}</div>" if c.fix_hint and c.status in (FAIL, WARN) else ""}'
        f'</td></tr>'
        for c in checks
    )

    ledger = "".join(_ledger_row(r) for r in records)

    contra_html = ""
    if contradictions:
        items = "".join(
            f"<li><b>{_e(r.tool)}</b>: {_e(msg)} "
            f'<span class="mono">({_e(r.effect_type.evidence)})</span></li>'
            for r, msg in contradictions
        )
        contra_html = (f'<div class="alert"><b>Declared vs observed — {len(contradictions)} '
                       f'contradiction(s):</b><ul>{items}</ul></div>')

    mut_note = ""
    if mutations:
        mut_note = (f'<p class="lede">Testbed variant with planted inconsistency: '
                    f'<span class="mono">{_e(", ".join(mutations))}</span>.</p>')

    verdict_cls = "fail" if fails else ("warn" if warns else "pass")
    verdict_txt = (f"{fails} effect-conformance failure(s)" if fails
                   else (f"{warns} advisory finding(s)" if warns
                         else "no effect-conformance failures observed"))

    return _TEMPLATE.format(
        server=_e(server_name),
        verdict_cls=verdict_cls,
        verdict=_e(verdict_txt),
        observer=_e(observer_desc),
        probe=_e(probe_desc),
        n_calls=len(records),
        n_auth=len(authority_objs),
        mut_note=mut_note,
        contradictions=contra_html,
        checks=rows_checks,
        ledger=ledger,
    )


def _ledger_row(r: EffectRecord) -> str:
    declared = ", ".join(f"{k}={v}" for k, v in r.declared.items()) or "—"
    eff = r.effect_type.value
    eff_cls = "write" if eff in _WRITE else "read"
    targets = ", ".join(f"{t.store}/{t.key}" for t in r.targets) or "—"
    auth = r.authority_bearing
    auth_txt = {"yes": "authority-bearing", "no": "not authority", "unknown": "unknown"}.get(
        auth.value, auth.value)
    auth_cls = "auth-yes" if auth.value == A_YES else "auth-no"
    persist = r.persistence.value
    persist_txt = "—" if persist is None else ("persistent" if persist else "ephemeral")
    dep = r.depends_on
    dep_txt = "—"
    if dep.how == "probed":
        deps = dep.value or []
        dep_txt = ", ".join(_e(d) for d in deps) if deps else "nothing revocable (residual)"
    authorized = r.authorized_by.value or "—"
    resp = (r.response_text or "").strip().replace("\n", " ")
    if len(resp) > 60:
        resp = resp[:57] + "…"

    # how-known chips
    def how(ev):
        return f'<span class="how how-{ev.how}">{ev.how}</span>'

    return (
        f'<tr>'
        f'<td><div class="tool">{_e(r.tool)}</div>'
        f'<div class="args mono">{_e(json.dumps(r.args))}</div></td>'
        f'<td class="mono">{_e(declared)}</td>'
        f'<td><span class="eff {eff_cls}">{_e(eff)}</span> {how(r.effect_type)}'
        f'<div class="ev">{_e(r.effect_type.evidence)}</div></td>'
        f'<td class="mono resp">{_e(resp) or "—"}</td>'
        f'<td>{_e(targets)}<div class="ev">{persist_txt}</div></td>'
        f'<td><span class="{auth_cls}">{_e(auth_txt)}</span> {how(auth)}'
        f'{f"<div class=ev>{_e(auth.evidence)}</div>" if auth.evidence else ""}</td>'
        f'<td class="mono">by: {_e(authorized)}<div class="ev">needs: {dep_txt}</div></td>'
        f'</tr>'
    )


_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{server} — effect evidence</title>
<style>
 :root{{color-scheme:light;
   --page:#faf9f7;--panel:#fff;--ink:#1b1a17;--ink-2:#514e47;--ink-3:#7d786d;
   --line:#e4e1d8;--line-soft:#edeae2;
   --accent:#4553c4;--accent-soft:rgba(69,83,196,.065);
   --ok:#2f7d46;--warn:#a16207;--bad:#b3352e;--bad-tint:rgba(179,53,46,.06);
   --mono:ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,monospace}}
 *{{box-sizing:border-box}}
 body{{margin:0;background:var(--page);color:var(--ink);
   font:14.5px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif;-webkit-font-smoothing:antialiased}}
 .wrap{{max-width:1220px;margin:0 auto;padding:44px 24px 72px}}
 .eyebrow{{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);margin:0 0 12px}}
 .eyebrow b{{color:var(--ink-2);font-weight:600}}
 h1{{font-size:30px;line-height:1.15;letter-spacing:-.02em;margin:0 0 12px;font-weight:650}}
 h2{{font-size:19px;letter-spacing:-.01em;margin:36px 0 10px;font-weight:640}}
 .lede{{color:var(--ink-2);margin:2px 0;font-size:14px}}
 .verdict{{display:inline-flex;gap:8px;padding:4px 12px;border-radius:999px;font-weight:600;
   font-size:13px;border:1px solid;margin:0 0 16px}}
 .verdict.pass{{color:var(--ok);border-color:rgba(47,125,70,.45);background:rgba(47,125,70,.07)}}
 .verdict.warn{{color:var(--warn);border-color:rgba(161,98,7,.45);background:rgba(161,98,7,.07)}}
 .verdict.fail{{color:var(--bad);border-color:rgba(179,53,46,.45);background:var(--bad-tint)}}
 .scope{{border:1px solid var(--line);border-radius:10px;background:var(--panel);
   padding:12px 16px;font-size:13px;color:var(--ink-2);max-width:74em}}
 .scope b{{color:var(--ink)}}
 .meta{{display:flex;flex-wrap:wrap;font-size:13px;margin:18px 0 0;border-top:1px solid var(--line);
   border-bottom:1px solid var(--line)}}
 .meta>div{{padding:9px 24px 9px 0;margin-right:24px;border-right:1px solid var(--line-soft)}}
 .meta>div:last-child{{border-right:0}}
 .meta .k{{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3)}}
 .meta .v{{font-family:var(--mono);font-size:13px}}
 .alert{{border-left:2px solid var(--bad);padding:2px 0 2px 14px;margin:20px 0 0;font-size:13.5px;
   max-width:74em}}
 .alert>b{{color:var(--bad);display:block;font-size:11px;text-transform:uppercase;
   letter-spacing:.09em;margin-bottom:4px}}
 .alert ul{{margin:0;padding-left:18px}} .alert li{{margin:3px 0;color:var(--ink-2)}}
 .alert li b{{color:var(--ink)}}
 .tablewrap{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}}
 table{{width:100%;border-collapse:collapse;font-size:12.5px;background:var(--panel)}}
 th{{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3);
   font-weight:600;padding:8px 12px;border-bottom:1px solid var(--line);background:var(--page);
   white-space:nowrap}}
 td{{padding:8px 12px;border-bottom:1px solid var(--line-soft);vertical-align:top}}
 tr:last-child td{{border-bottom:0}}
 tbody tr:hover>td{{background:rgba(27,26,23,.022)}}
 .id,.mono{{font-family:var(--mono);font-size:11.5px}}
 .lvl{{color:var(--ink-3);font-size:11px}}
 .ttl{{font-weight:550;font-size:13px}} .ev{{color:var(--ink-2);font-size:11.5px;margin-top:2px}}
 .fix{{color:var(--ink-3);font-size:11.5px;margin-top:2px}} .fix b{{color:var(--ink-2)}}
 .tool{{font-weight:600;font-size:13px}} .args{{color:var(--ink-3);margin-top:1px}}
 .resp{{color:var(--ink-2);max-width:150px;word-break:break-word}}
 .badge{{display:inline-flex;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600;
   border:1px solid var(--line);color:var(--ink-2);white-space:nowrap}}
 .badge.pass{{color:var(--ok);border-color:rgba(47,125,70,.4);background:rgba(47,125,70,.06)}}
 .badge.fail{{color:var(--bad);border-color:rgba(179,53,46,.4);background:var(--bad-tint)}}
 .badge.warn{{color:var(--warn);border-color:rgba(161,98,7,.4);background:rgba(161,98,7,.06)}}
 .badge.skip{{color:var(--ink-3)}}
 .eff{{display:inline-block;padding:0 7px;border-radius:999px;font-size:11px;font-weight:600;
   border:1px solid var(--line);color:var(--ink-2)}}
 .eff.write{{color:var(--warn);border-color:rgba(161,98,7,.4);background:rgba(161,98,7,.06)}}
 .auth-yes{{color:var(--accent);font-weight:650;font-size:12.5px}}
 .auth-no{{color:var(--ink-2);font-size:12.5px}}
 .how{{display:inline-block;font-size:9.5px;text-transform:uppercase;letter-spacing:.04em;
   padding:1px 5px;border-radius:4px;margin-left:3px;vertical-align:middle}}
 .how-observed{{background:rgba(47,125,70,.1);color:var(--ok)}}
 .how-probed{{background:var(--accent-soft);color:var(--accent)}}
 .how-declared{{background:rgba(161,98,7,.1);color:var(--warn)}}
 .how-unknown{{background:var(--line-soft);color:var(--ink-3)}}
 footer{{margin-top:44px;padding-top:14px;border-top:1px solid var(--line);color:var(--ink-3);
   font-size:12px}}
 @media (max-width:640px){{h1{{font-size:24px}}.meta>div{{padding-right:14px;margin-right:14px}}}}
</style></head><body><div class="wrap">
<p class="eyebrow"><b>mcp-proof</b> / effect evidence</p>
<h1>{server}</h1>
<div class="verdict {verdict_cls}">{verdict}</div>
{mut_note}
<div class="scope"><b>Observation boundary.</b> Effects are read <b>out-of-band</b> via {observer},
never from the tools' own responses. Authority and effectiveness come from a probe that
<b>exercises</b> created objects: {probe}. Dimensions no channel can establish are marked
<span class="how how-unknown">unknown</span> and their checks SKIP — never a silent pass. This is a
controlled measurement instrument; findings here are about the audited server, not production
prevalence.</div>
<div class="meta">
 <div><span class="k">Calls observed</span><span class="v">{n_calls}</span></div>
 <div><span class="k">Authority objects</span><span class="v">{n_auth}</span></div>
</div>
{contradictions}
<h2>Effect-conformance checks</h2>
<div class="tablewrap"><table>
<thead><tr><th>Check</th><th>Level</th><th>Result</th><th>Details</th></tr></thead>
<tbody>{checks}</tbody></table></div>
<h2>Per-call effect ledger</h2>
<p class="lede">Declared annotations beside the effect an independent observer saw, the response a
response-only auditor would have read, the objects that resulted, and the probe's authority /
dependency verdict.</p>
<div class="tablewrap"><table>
<thead><tr><th>Call</th><th>Declared</th><th>Observed effect</th><th>Response seen</th>
<th>Objects / persistence</th><th>Authority (probed)</th><th>Lineage</th></tr></thead>
<tbody>{ledger}</tbody></table></div>
<footer>mcp-proof effect lane · deterministic, out-of-band observation · no LLM judging.
<b>how-known</b>: <span class="how how-observed">observed</span> (state diff)
<span class="how how-probed">probed</span> (exercised)
<span class="how how-declared">declared</span> (server's word)
<span class="how how-unknown">unknown</span> (no channel).</footer>
</div></body></html>
"""

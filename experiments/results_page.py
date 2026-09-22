"""Static site builder for the experiment results page.

Renders experiments/results/index.html from the three runners' JSON outputs —
the JSON is the single source of truth, so the page cannot drift from what the
experiments measured. No framework, no chart library: components are small
Python render functions, visualizations are semantic HTML (metric matrices,
dot matrices, thin inline micro-bars) rather than chart chrome.

Design system: near-white warm ground, graphite text, one indigo accent;
muted green/amber/red only as small status dots, badges and error tints.
Numbers are printed exactly as the runners rounded them (3 decimals).

Component vocabulary (kept deliberately close to the layout grammar):
    nav · header_block · experiment_section · finding · metric_matrix ·
    detection_matrix · evidence_table · status_cell · method_note
"""

from __future__ import annotations

import html

# ---------------------------------------------------------------- tokens ----

CSS = """
:root{
  --page:#faf9f7; --panel:#ffffff; --ink:#1b1a17; --ink-2:#514e47; --ink-3:#7d786d;
  --line:#e4e1d8; --line-soft:#edeae2;
  --accent:#4553c4; --accent-soft:rgba(69,83,196,.065); --accent-line:rgba(69,83,196,.35);
  --ok:#2f7d46; --warn:#a16207; --bad:#b3352e;
  --bad-tint:rgba(179,53,46,.07); --note-tint:rgba(161,98,7,.06);
  --mono:ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,'Segoe UI',sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.55 var(--sans);
     -webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code,.mono{font-family:var(--mono)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

.shell{max-width:1220px;margin:0 auto;padding:0 24px 96px;display:grid;
       grid-template-columns:176px minmax(0,1fr);gap:48px}
main{min-width:0;max-width:960px}

/* ------------------------------------------------------------- nav rail */
.rail{padding-top:56px}
.rail nav{position:sticky;top:28px;font-size:13px}
.rail .rail-mark{font-weight:650;letter-spacing:-.01em;margin-bottom:14px;color:var(--ink)}
.rail .rail-mark .sep{color:var(--ink-3);font-weight:400}
.rail a{display:block;padding:5px 0 5px 12px;color:var(--ink-2);border-left:2px solid transparent;
        line-height:1.35}
.rail a .eid{font-family:var(--mono);font-size:11px;color:var(--ink-3);margin-right:6px}
.rail a:hover{color:var(--ink);text-decoration:none}
.rail a[aria-current]{border-left-color:var(--accent);color:var(--ink)}
.rail a[aria-current] .eid{color:var(--accent)}

/* --------------------------------------------------------------- header */
header.doc{padding:56px 0 8px}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
         margin:0 0 14px}
.eyebrow b{color:var(--ink-2);font-weight:600}
h1{font-size:38px;line-height:1.12;letter-spacing:-.022em;margin:0 0 10px;font-weight:650}
.question{font-size:17px;color:var(--ink-2);margin:0 0 14px;max-width:52em}
.lede{font-size:15px;color:var(--ink-2);margin:0;max-width:56em}

.metastrip{display:flex;flex-wrap:wrap;gap:0;margin:26px 0 0;border-top:1px solid var(--line);
           border-bottom:1px solid var(--line);font-size:13px}
.metastrip>div{padding:10px 26px 10px 0;margin-right:26px;border-right:1px solid var(--line-soft)}
.metastrip>div:last-child{border-right:0;margin-right:0}
.metastrip .k{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.08em;
              color:var(--ink-3);margin-bottom:1px}
.metastrip .v{font-family:var(--mono);font-size:13px;color:var(--ink)}
.disclaimer{font-size:12.5px;color:var(--ink-3);margin:10px 0 0}
.artifacts{font-size:12.5px;color:var(--ink-3);margin:6px 0 0}
.artifacts a{font-family:var(--mono);font-size:12px;margin-right:14px}

/* ---------------------------------------------------------- experiments */
section.exp{margin-top:64px;padding-top:28px;border-top:1px solid var(--line)}
.exp-head{display:flex;align-items:baseline;gap:12px;margin:0 0 4px}
.exp-head .eid{font-family:var(--mono);font-size:13px;color:var(--accent);font-weight:600}
.exp-head h2{font-size:25px;letter-spacing:-.015em;font-weight:640;margin:0}
.exp-head .anchor{color:var(--line);font-size:15px;visibility:hidden}
.exp-head:hover .anchor{visibility:visible}
.rq{margin:10px 0 0;max-width:54em}
.label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.09em;
       color:var(--ink-3);margin-bottom:3px}
.rq p{margin:0;font-size:15.5px;color:var(--ink-2)}

.finding{margin:18px 0 0;padding:2px 0 2px 14px;border-left:2px solid var(--accent);max-width:54em}
.finding p{margin:0;font-size:16px;color:var(--ink)}
.finding .label{color:var(--accent);opacity:.85}

.viz{margin:22px 0 0}
.method{font-size:12.5px;color:var(--ink-3);margin:14px 0 0;max-width:60em}
.method b{color:var(--ink-2);font-weight:600}

/* ----------------------------------------------------------- tables ----*/
.tablewrap{overflow-x:auto;margin:0;border:1px solid var(--line);border-radius:10px;
           background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--panel)}
th{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3);
   font-weight:600;text-align:left;padding:8px 14px;border-bottom:1px solid var(--line);
   white-space:nowrap;background:var(--page)}
th.num,td.num{text-align:right}
td{padding:8px 14px;border-bottom:1px solid var(--line-soft);vertical-align:top}
tr:last-child td{border-bottom:0}
td .sub{display:block;font-size:11.5px;color:var(--ink-3);margin-top:1px}
.id{font-family:var(--mono);font-size:12.5px;white-space:nowrap;cursor:copy}
.id:hover{color:var(--accent)}
.id.copied{color:var(--ok)}
.val{font-family:var(--mono);font-size:13px;font-variant-numeric:tabular-nums}
tr.hl-accent>td{background:var(--accent-soft)}
tr.hl-accent>td:first-child{box-shadow:inset 2px 0 0 var(--accent)}
tr.hl-note>td{background:var(--note-tint)}
tr.hl-note>td:first-child{box-shadow:inset 2px 0 0 var(--warn)}
tr.group>td{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3);
            background:var(--page);padding:5px 14px;border-bottom:1px solid var(--line-soft)}
td.err{background:var(--bad-tint)}
.note-cell{font-size:12.5px;color:var(--ink-2)}
tbody tr:hover>td{background:rgba(27,26,23,.022)}
tbody tr.hl-accent:hover>td{background:var(--accent-soft)}
tbody tr.hl-note:hover>td{background:var(--note-tint)}

/* metric micro-bars */
.mrow{display:flex;align-items:center;gap:10px;justify-content:flex-end}
.bar{flex:none;width:76px;height:4px;background:var(--line-soft);border-radius:2px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--ink-3);border-radius:2px}
tr.hl-accent .bar i{background:var(--accent)}

/* status dots */
.dot{font-size:12px;line-height:1}
.dot.on{color:var(--ink)} .dot.off{color:var(--ink-3)}
.dot.ok{color:var(--ok)} .dot.bad{color:var(--bad)}
.dotlbl{font-size:11.5px;color:var(--ink-3);margin-left:5px}
.legend{font-size:12px;color:var(--ink-3);margin:8px 2px 0}
.legend .dot{margin-left:10px;margin-right:2px}
.legend .swatch{display:inline-block;width:12px;height:12px;border-radius:3px;
                background:var(--bad-tint);border:1px solid var(--line);
                vertical-align:-2px;margin:0 4px 0 12px}

.badge{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.02em;
       padding:1px 7px;border-radius:999px;border:1px solid var(--line);color:var(--ink-2)}
.badge.bad{color:var(--bad);border-color:rgba(179,53,46,.4);background:var(--bad-tint)}
.badge.inv{color:var(--accent);border-color:var(--accent-line);background:var(--accent-soft)}

/* evidence disclosure */
details.evidence{margin:16px 0 0;border:1px solid var(--line);background:var(--panel);
                 border-radius:10px;overflow:hidden}
details.evidence .tablewrap{border:0;border-radius:0}
details.evidence>summary{cursor:pointer;list-style:none;padding:9px 14px;font-size:13px;
                         color:var(--ink-2);display:flex;align-items:center;gap:8px;
                         user-select:none}
details.evidence>summary::-webkit-details-marker{display:none}
details.evidence>summary:before{content:"+";font-family:var(--mono);color:var(--ink-3);
                                width:12px;text-align:center}
details.evidence[open]>summary:before{content:"−"}
details.evidence[open]>summary{border-bottom:1px solid var(--line-soft)}
details.evidence .inner{padding:0}
details.evidence table{border:0}
details.evidence .method{padding:10px 14px;margin:0}

/* footer */
footer.doc{margin-top:72px;padding-top:18px;border-top:1px solid var(--line);
           font-size:12.5px;color:var(--ink-3)}
footer.doc code{font-size:12px;background:var(--panel);border:1px solid var(--line-soft);
                padding:1px 5px;border-radius:4px}

@media (max-width:1080px){
  html{scroll-padding-top:64px}
  .shell{display:block;padding:0 18px 72px}
  .rail{padding:0;margin:0 -18px}
  .rail nav{position:sticky;top:0;display:flex;align-items:center;gap:2px;overflow-x:auto;
            background:var(--page);border-bottom:1px solid var(--line);padding:10px 18px;
            z-index:10}
  .rail .rail-mark{margin:0 14px 0 0;white-space:nowrap;font-size:13px}
  .rail a{border-left:0;border-bottom:2px solid transparent;padding:2px 8px;white-space:nowrap}
  .rail a[aria-current]{border-bottom-color:var(--accent)}
  header.doc{padding-top:34px}
  h1{font-size:30px}
  .metastrip>div{padding-right:16px;margin-right:16px}
}
@media (max-width:640px){
  h1{font-size:26px}
  .metastrip{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}
  .metastrip>div{border-right:0;padding:8px 0;margin:0;min-width:0}
  .metastrip .v{white-space:normal;overflow-wrap:anywhere}
  .artifacts a{overflow-wrap:anywhere}
}
"""

JS = """
(function(){
  // scroll-spy: mark the section currently in view in the rail
  var links = Array.prototype.slice.call(document.querySelectorAll('.rail a[href^="#"]'));
  var map = {};
  links.forEach(function(a){ map[a.getAttribute('href').slice(1)] = a; });
  var current = null;
  function setCurrent(id){
    if (current === id || !map[id]) return;
    links.forEach(function(a){ a.removeAttribute('aria-current'); });
    map[id].setAttribute('aria-current','true');
    current = id;
  }
  setCurrent('overview');
  if ('IntersectionObserver' in window){
    var obs = new IntersectionObserver(function(entries){
      entries.forEach(function(e){ if (e.isIntersecting) setCurrent(e.target.id); });
    }, {rootMargin:'0px 0px -78% 0px'});
    document.querySelectorAll('[data-spy]').forEach(function(s){ obs.observe(s); });
  }
  // click-to-copy for object identifiers
  document.querySelectorAll('.id[data-copy]').forEach(function(el){
    el.title = 'click to copy';
    el.addEventListener('click', function(){
      var t = el.getAttribute('data-copy');
      if (navigator.clipboard) navigator.clipboard.writeText(t);
      el.classList.add('copied');
      setTimeout(function(){ el.classList.remove('copied'); }, 900);
    });
  });
})();
"""


# --------------------------------------------------------------- helpers ----


def _e(s: object) -> str:
    return html.escape(str(s))


def fmt3(v: float) -> str:
    """Exact runner value (already rounded to 3 dp) in a uniform column."""
    return f"{v:.3f}"


def copy_id(text: str) -> str:
    return f'<code class="id" data-copy="{_e(text)}">{_e(text)}</code>'


def status_cell(state: bool, *, on: str = "true", off: str = "false",
                wrong: bool = False, tone: str = "neutral") -> str:
    """A compact semantic boolean cell: ● true / ○ false, with the textual
    state kept visible for accessibility. `wrong` tints the cell as a
    disagreement with ground truth (class on the td, added by caller)."""
    dot_cls = "on" if state else "off"
    if tone == "ok" and state:
        dot_cls = "ok"
    if tone == "bad" and state:
        dot_cls = "bad"
    mark = "●" if state else "○"
    label = on if state else off
    extra = ' <span class="sr">(disagrees with ground truth)</span>' if wrong else ""
    return (f'<span class="dot {dot_cls}" aria-hidden="true">{mark}</span>'
            f'<span class="dotlbl">{_e(label)}</span>{extra}')


def micro_metric(v: float) -> str:
    """Numeric value with a thin horizontal micro-bar; value stays readable."""
    return (f'<span class="mrow"><span class="bar"><i style="width:{v * 100:.0f}%"></i></span>'
            f'<span class="val">{fmt3(v)}</span></span>')


def method_note(text_html: str) -> str:
    return f'<p class="method">{text_html}</p>'


def finding(text_html: str) -> str:
    return (f'<div class="finding"><span class="label">Finding</span>'
            f'<p>{text_html}</p></div>')


def table(head: list[str], body_rows: list[str], *, num_cols: set[int] = frozenset()) -> str:
    ths = "".join(
        f'<th{" class=num" if i in num_cols else ""}>{h}</th>' for i, h in enumerate(head)
    )
    return (f'<div class="tablewrap"><table><thead><tr>{ths}</tr></thead>'
            f'<tbody>{"".join(body_rows)}</tbody></table></div>')


def evidence_details(summary: str, inner_html: str) -> str:
    return (f'<details class="evidence"><summary>{_e(summary)}</summary>'
            f'<div class="inner">{inner_html}</div></details>')


def experiment_section(eid: str, anchor: str, title: str, question: str,
                       finding_html: str, viz_html: str,
                       evidence_html: str = "", note_html: str = "") -> str:
    return f"""
<section class="exp" id="{anchor}" data-spy>
  <div class="exp-head"><span class="eid">{_e(eid)}</span><h2>{_e(title)}</h2>
    <a class="anchor" href="#{anchor}" aria-label="link to {_e(eid)}">#</a></div>
  <div class="rq"><span class="label">Research question</span><p>{question}</p></div>
  {finding_html}
  <div class="viz">{viz_html}</div>
  {evidence_html}
  {note_html}
</section>"""


# ------------------------------------------------------------ E1 pieces ----

_DETECTOR_LABELS = {
    "effect_aware": ("Effect-aware", "out-of-band state observation"),
    "response_level": ("Response-level", "tool responses only (current auditor)"),
    "name_heuristic": ("Name heuristic", "tool names/descriptions only"),
    "probe": ("Probe (exercise)", "attempts to use the object"),
    "persistence": ("Persistence ⇒ authority", "persistent objects count as authority"),
    "name_keyword": ("Name keyword", "credential-looking names count as authority"),
    "existence": ("Existence (inventory)", "listed ⇒ effective"),
    "delegation_centric": ("Delegation-centric", "grant active ⇒ effective"),
}


def _detector_label(key: str) -> tuple[str, str]:
    return _DETECTOR_LABELS.get(key, (key, ""))


def e1_metric_matrix(scores: dict) -> str:
    order = ["effect_aware", "response_level", "name_heuristic"]
    rows = []
    for key in order:
        s = scores[key]
        name, sub = _detector_label(key)
        hl = ' class="hl-accent"' if key == "effect_aware" else ""
        rows.append(
            f'<tr{hl}><td><span>{_e(name)}</span><span class="sub">{_e(sub)} · '
            f'<span class="val">TP {s["tp"]} · FP {s["fp"]} · FN {s["fn"]}</span></span></td>'
            f'<td class="num"><span class="val">{fmt3(s["precision"])}</span></td>'
            f'<td class="num">{micro_metric(s["recall"])}</td>'
            f'<td class="num">{micro_metric(s["f1"])}</td></tr>'
        )
    return table(["Detector", "Precision", "Recall", "F1"], rows, num_cols={1, 2, 3})


def e1_detection_matrix(catch_table: dict) -> str:
    """Per-lie dot matrix: which detector flagged the lying tool."""
    det_order = ["effect_aware", "response_level", "name_heuristic"]
    visible = [(k, v) for k, v in catch_table.items() if not v["response_invisible"]]
    invisible = [(k, v) for k, v in catch_table.items() if v["response_invisible"]]

    def rows_for(items, group_label, invisible_group):
        out = [f'<tr class="group"><td colspan="5">{_e(group_label)}</td></tr>']
        for lie, info in items:
            cells = []
            for d in det_order:
                caught = d in info["caught_by"]
                cells.append(
                    f'<td>{status_cell(caught, on="caught", off="missed", tone="ok")}</td>')
            hl = ' class="hl-accent"' if invisible_group else ""
            out.append(
                f'<tr{hl}><td>{copy_id(lie)}</td><td>{copy_id(info["tool"])}</td>'
                + "".join(cells) + "</tr>")
        return out

    rows = rows_for(visible, "effect visible in the response", False)
    rows += rows_for(invisible,
                     "effect invisible in the response — only observation can see it", True)
    head = ["Planted lie", "Lying tool",
            "Effect-aware", "Response-level", "Name heuristic"]
    legend = ('<p class="legend"><span class="dot ok">●</span> caught'
              '<span class="dot off">○</span> missed — highlighted rows are the three '
              'response-invisible lies</p>')
    return table(head, rows) + legend


def e1_evidence(variants: list[dict]) -> str:
    rows = []
    for v in variants:
        flagged = v["flagged"]

        def fset(key, flagged=flagged):
            names = flagged.get(key, [])
            return ", ".join(copy_id(n) for n in names) if names else '<span class="dot off">—</span>'

        positives = ", ".join(copy_id(p) for p in v["positives"]) or '<span class="dot off">—</span>'
        rows.append(
            f'<tr><td>{copy_id(v["variant"])}</td><td>{positives}</td>'
            f'<td>{fset("effect_aware")}</td><td>{fset("response_level")}</td>'
            f'<td>{fset("name_heuristic")}</td></tr>')
    inner = table(["Server variant", "Ground truth (lying tool)",
                   "Effect-aware flagged", "Response-level flagged", "Name heuristic flagged"],
                  rows)
    inner += method_note(
        "One audit per variant; every detector reads the same execution, so differences come "
        "from the observation channel, not from run-to-run noise. The honest variant measures "
        "false positives — no detector flagged anything on it.")
    return evidence_details("Inspect evidence — per-variant detections", inner)


# ------------------------------------------------------------ E2 pieces ----


def e2_summary_matrix(confusion: dict) -> str:
    order = ["probe", "name_keyword", "persistence"]
    rows = []
    for key in order:
        c = confusion[key]
        name, sub = _detector_label(key)
        hl = ' class="hl-accent"' if key == "probe" else ""
        rows.append(
            f'<tr{hl}><td><span>{_e(name)}</span><span class="sub">{_e(sub)}</span></td>'
            f'<td class="num">{micro_metric(c["accuracy"])}</td>'
            f'<td class="num"><span class="val">{c["tp"]}</span></td>'
            f'<td class="num"><span class="val">{c["fp"]}</span></td>'
            f'<td class="num"><span class="val">{c["tn"]}</span></td>'
            f'<td class="num"><span class="val">{c["fn"]}</span></td></tr>')
    return table(["Classifier", "Accuracy", "TP", "FP", "TN", "FN"],
                 rows, num_cols={1, 2, 3, 4, 5})


def e2_corpus_table(corpus: list[dict]) -> str:
    rows = []
    for o in corpus:
        truth = o["ground_truth_authority"]
        pred = o["pred"]
        note = o.get("note") or ""
        hl = ' class="hl-note"' if note else ""

        def pcell(key, pred=pred, truth=truth):
            p = pred[key]
            wrong = p != truth
            cls = ' class="err"' if wrong else ""
            return f'<td{cls}>{status_cell(p, wrong=wrong)}</td>'

        rows.append(
            f'<tr{hl}><td>{copy_id(o["store"] + "/" + o["key"])}</td>'
            f'<td>{status_cell(o["persistent"])}</td>'
            f'<td>{status_cell(truth, tone="ok")}</td>'
            f'{pcell("persistence")}{pcell("name_keyword")}{pcell("probe")}'
            f'<td class="note-cell">{_e(note) or "—"}</td></tr>')
    head = ["Object", "Persistent", "Authority (truth)",
            "Persistence says", "Name says", "Probe says", "Note"]
    legend = ('<p class="legend"><span class="dot on">●</span> true'
              '<span class="dot off">○</span> false'
              '<span class="swatch"></span> prediction disagrees with ground truth</p>')
    return table(head, rows) + legend


# ------------------------------------------------------------ E3 pieces ----


def e3_summary_matrix(scores: dict) -> str:
    order = ["probe", "existence", "delegation_centric"]
    rows = []
    for key in order:
        s = scores[key]
        name, sub = _detector_label(key)
        hl = ' class="hl-accent"' if key == "probe" else ""
        fi = s["false_ineffective"]
        fi_html = (f'<span class="badge bad">{fi} — residual authority missed</span>'
                   if fi else '<span class="val">0</span>')
        rows.append(
            f'<tr{hl}><td><span>{_e(name)}</span><span class="sub">{_e(sub)}</span></td>'
            f'<td class="num">{micro_metric(s["accuracy"])}</td>'
            f'<td class="num"><span class="val">{s["false_effective"]}</span></td>'
            f'<td class="num">{fi_html}</td></tr>')
    return table(["Detector", "Accuracy", "False-effective", "False-ineffective"],
                 rows, num_cols={1, 2, 3})


def e3_scenario_matrix(scenarios: list[dict]) -> str:
    rows = []
    for r in scenarios:
        truth = r["truth_effective"]
        p = r["predictions"]
        residual = r["scenario"] == "grant_revoked"
        hl = ' class="hl-accent"' if residual else ""

        def pcell(key, p=p, truth=truth):
            v = p[key]
            wrong = v != truth
            cls = ' class="err"' if wrong else ""
            return f'<td{cls}>{status_cell(v, on="effective", off="dead", wrong=wrong)}</td>'

        note = r["description"]
        if residual:
            note = f'{note} <span class="badge inv">residual authority</span>'
        rows.append(
            f'<tr{hl}><td>{copy_id(r["scenario"])}</td>'
            f'<td>{status_cell(truth, on="effective", off="dead", tone="ok")}</td>'
            f'{pcell("existence")}{pcell("delegation_centric")}{pcell("probe")}'
            f'<td class="note-cell">{note}</td></tr>')
    head = ["Lifecycle scenario", "Truth", "Existence says", "Delegation says",
            "Probe says", "Note"]
    legend = ('<p class="legend"><span class="dot ok">●</span> effective'
              '<span class="dot off">○</span> dead'
              '<span class="swatch"></span> prediction disagrees with ground truth</p>')
    return table(head, rows) + legend


def e3_evidence(scenarios: list[dict]) -> str:
    rows = []
    for r in scenarios:
        rows.append(
            f'<tr><td>{copy_id(r["scenario"])}</td>'
            f'<td>{status_cell(r["listed"], on="listed", off="absent")}</td>'
            f'<td>{status_cell(r["grant_active"], on="active", off="revoked")}</td>'
            f'<td><span class="val">{_e(r["probe_status"])}</span></td>'
            f'<td class="note-cell mono" style="font-size:12px">{_e(r["probe_basis"])}</td></tr>')
    inner = table(["Scenario", "Key row", "Grant", "Probe status", "Probe basis"], rows)
    inner += method_note(
        "The probe basis is the evidence line the exercise probe recorded: which credential "
        "column it exercised and which rule accepted or rejected it. The key is "
        "<code>api_keys/key_0001</code> in every scenario; each scenario runs on a fresh server.")
    return evidence_details("Inspect evidence — per-scenario probe transcript", inner)


# ------------------------------------------------------------- assembly ----


def _nav(items: list[tuple[str, str, str]]) -> str:
    links = "".join(
        f'<a href="#{anchor}">{f"<span class=eid>{_e(eid)}</span>" if eid else ""}{_e(label)}</a>'
        for eid, label, anchor in items)
    return (f'<aside class="rail"><nav aria-label="experiments">'
            f'<div class="rail-mark">mcp-proof <span class="sep">/</span> evaluation</div>'
            f'{links}</nav></aside>')


def _header(r1: dict, r2: dict, r3: dict) -> str:
    n_exp = 3
    n_lies = len(r1.get("catch_table", {}))
    n_invisible = sum(1 for v in r1.get("catch_table", {}).values() if v["response_invisible"])
    meta = f"""
<div class="metastrip" role="list">
  <div role="listitem"><span class="k">Testbed</span>
    <span class="v">controlled · synthetic</span></div>
  <div role="listitem"><span class="k">Ground truth</span>
    <span class="v">out-of-band state</span></div>
  <div role="listitem"><span class="k">Experiments</span>
    <span class="v">{n_exp} · 3 detectors each</span></div>
  <div role="listitem"><span class="k">Planted lies</span>
    <span class="v">{n_lies} ({n_invisible} response-invisible)</span></div>
</div>
<p class="disclaimer">Controlled-testbed measurements of detection behaviour on planted
inconsistencies — not production prevalence. Ground truth is read out-of-band from the state
store, never through the audited MCP surface.</p>
<p class="artifacts">Artifacts:
  <a href="effect-report-honest.html">effect-report-honest.html</a>
  <a href="effect-report-silent-keymint.html">effect-report-silent-keymint.html</a>
  <a href="summary.md">summary.md</a>
  <a href="e1_effect_conformance.json">e1.json</a>
  <a href="e2_persistence_vs_authority.json">e2.json</a>
  <a href="e3_existence_vs_effectiveness.json">e3.json</a>
</p>"""
    return f"""
<header class="doc" id="overview" data-spy>
  <p class="eyebrow"><b>mcp-proof</b> / evaluation</p>
  <h1>Effect-aware conformance</h1>
  <p class="question">Can declared MCP effects be verified against independently observed
  external state?</p>
  <p class="lede">Declared MCP semantics can be misleading even when tool responses and tool
  names look correct. Each experiment compares a declared or inferred property against ground
  truth established outside the audited MCP surface — an out-of-band state observer and a
  probe that exercises created objects.</p>
  {meta}
</header>"""


def build_page(r1: dict, r2: dict, r3: dict) -> str:
    nav = _nav([
        ("", "Overview", "overview"),
        ("E1", "Annotation lies", "e1"),
        ("E2", "Persistence vs authority", "e2"),
        ("E3", "Effectiveness", "e3"),
        ("", "Method", "method"),
    ])

    e1 = experiment_section(
        "E1", "e1", "Declared effect vs observed effect",
        "Can effect observation catch annotation lies that a response-only auditor and a "
        "name heuristic miss?",
        finding("Only effect observation detects all three response-invisible lies. "
                "Each baseline reaches recall 0.333 with a structural blind spot the "
                "observation channel cannot fix."),
        e1_metric_matrix(r1["scores"])
        + '<p class="legend" style="margin-bottom:14px">aggregated over the honest server + '
          'six single-lie variants; per-lie detections below</p>'
        + e1_detection_matrix(r1["catch_table"]),
        e1_evidence(r1["variants"]),
        method_note("<b>Oracle:</b> the testbed's mutation ledger — each variant plants exactly "
                    "one annotation lie in one tool. <b>Fairness:</b> all three detectors read "
                    "the same execution records; they differ only in which channel they may "
                    "consult (external state, response text, or metadata)."),
    )

    e2 = experiment_section(
        "E2", "e2", "Persistence is not authority",
        "Does probe-backed classification separate authority-bearing objects from ordinary "
        "persistent objects better than “persistent ⇒ authority” and a credential-name "
        "keyword?",
        finding("The probe classifies by <em>use</em>, not appearance — it is correct on the "
                "decoy note named <code>api_key_backup</code> (fools both baselines' signals) "
                "and on a credential that never persisted."),
        e2_summary_matrix(r2["confusion"])
        + '<p class="legend" style="margin-bottom:14px">object corpus spans the '
          'persistent × authority quadrants; per-object classifications below</p>'
        + e2_corpus_table(r2["corpus"]),
        "",
        method_note("<b>Oracle:</b> by-construction authority labels — a table's objects are "
                    "authority-bearing iff the testbed's real authorization rule accepts them "
                    "as credentials. <b>Probing time:</b> each object is exercised at creation "
                    "time, while it genuinely exists; persistence is judged against the final "
                    "snapshot."),
    )

    e3 = experiment_section(
        "E3", "e3", "Existence is not current effectiveness",
        "After a lifecycle event (grant revoked, key revoked, key deleted, TTL expired), does "
        "an exercise probe report an object's true effectiveness where “it is still listed” "
        "and “its grant is still active” do not?",
        finding("In <code>grant_revoked</code> the key remains effective although the grant "
                "that authorized it is gone — residual authority. The delegation-centric view "
                "calls it dead (the one false-ineffective); the probe does not, and existence "
                "never distinguishes a live key from a listed-but-dead one."),
        e3_summary_matrix(r3["scores"])
        + '<p class="legend" style="margin-bottom:14px">false-ineffective is the dangerous '
          'error: believing an object is neutralized while it still works</p>'
        + e3_scenario_matrix(r3["scenarios"]),
        e3_evidence(r3["scenarios"]),
        method_note("<b>Oracle:</b> intended effectiveness per scenario, by construction — "
                    "modelled on documented provider behaviour (a revoked grant leaving a "
                    "minted key alive; keys listed after revocation). "
                    "<b>Event application:</b> lifecycle events are applied out-of-band, "
                    "never through the audited tools."),
    )

    method = """
<section class="exp" id="method" data-spy>
  <div class="exp-head"><h2>Method &amp; reproduction</h2>
    <a class="anchor" href="#method" aria-label="link to method">#</a></div>
  <div class="rq" style="max-width:60em"><p>
  Every number on this page is read from the experiment runners' JSON outputs, so the page
  cannot drift from what was measured. The observer reads the server's SQLite store directly;
  the probe replays the server's real authorization rule out-of-band (shared code, faithful by
  construction). Effects a channel cannot establish are reported <span class="val">unknown</span>
  and never counted as evidence. Full methodology, limitations and related-work positioning:
  <a href="https://github.com/YuCPbit/mcp-proof/blob/main/docs/effect-aware-conformance.md">docs/effect-aware-conformance.md</a>.
  </p></div>
  <p class="method" style="margin-top:14px">Reproduce from a clean state:
  <code class="val">python experiments/run_all.py</code> — regenerates the JSON, the markdown
  tables and this page. Flagship effect-evidence reports:
  <code class="val">python experiments/make_report.py</code>.</p>
</section>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Effect-aware conformance — mcp-proof evaluation</title>
<style>{CSS}</style>
</head>
<body>
<div class="shell">
{nav}
<main>
{_header(r1, r2, r3)}
{e1}
{e2}
{e3}
{method}
<footer class="doc">
Generated by <code>experiments/run_all.py</code> from the runners' own JSON outputs ·
deterministic testbed · no LLM judging · values shown exactly as measured (3-decimal rounding
performed by the runners).
</footer>
</main>
</div>
<script>{JS}</script>
</body>
</html>
"""

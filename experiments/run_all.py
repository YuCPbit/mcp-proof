"""Run E1–E3 from a clean state, aggregate results, and build the results page.

Every number on the page is read back from the experiments' own JSON outputs,
so the page can never drift from what the runners produced. Page rendering
lives in results_page.py (component functions over the JSON); this module only
orchestrates: run experiments → write JSON/markdown → render the flagship
effect-evidence reports → build index.html.

The whole pipeline is deterministic: two runs write byte-identical files, and
CI re-runs it against the committed results to enforce exactly that. The
real-server case studies (case_studies.py) are the one deliberate exception —
they need the third-party servers on the machine, so this module only *reads*
their committed JSON when rendering the page and never re-runs them.

    python experiments/run_all.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import e1_effect_conformance as e1  # noqa: E402
import e2_persistence_vs_authority as e2  # noqa: E402
import e3_existence_vs_effectiveness as e3  # noqa: E402
import make_report  # noqa: E402
import results_page  # noqa: E402
from case_studies import load_committed_case_results  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    print("→ E1")
    e1.main()
    print("→ E2")
    e2.main()
    print("→ E3")
    e3.main()
    print("→ flagship effect-evidence reports")
    make_report.main()

    r1 = _load("e1_effect_conformance.json")
    r2 = _load("e2_persistence_vs_authority.json")
    r3 = _load("e3_existence_vs_effectiveness.json")
    cases = load_committed_case_results()

    (RESULTS / "index.html").write_text(
        results_page.build_page(r1, r2, r3, cases), encoding="utf-8")

    md1 = (RESULTS / "e1_effect_conformance.md").read_text(encoding="utf-8")
    md2 = (RESULTS / "e2_persistence_vs_authority.md").read_text(encoding="utf-8")
    md3 = (RESULTS / "e3_existence_vs_effectiveness.md").read_text(encoding="utf-8")
    case_mds = [
        (RESULTS / f"case_{c['target']}.md").read_text(encoding="utf-8")
        for c in cases
        if (RESULTS / f"case_{c['target']}.md").exists()
    ]
    (RESULTS / "summary.md").write_text(
        "# Effect-aware conformance — experiment summary\n\n"
        "Controlled-testbed measurements; ground truth is out-of-band. "
        "Not production prevalence.\n\n" + md1 + "\n" + md2 + "\n" + md3
        + ("\n" + "\n".join(case_mds) if case_mds else ""),
        encoding="utf-8")
    print(f"\n✓ wrote {RESULTS / 'index.html'}, summary.md, and per-experiment JSON/MD"
          + (f" (+ {len(cases)} committed case studies rendered)" if cases else ""))


if __name__ == "__main__":
    main()

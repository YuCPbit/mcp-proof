"""JUnit XML from the report model — one testcase per check / replay verdict.

Semantics: FAIL → <failure>, SKIP → <skipped>, WARN passes but keeps its
evidence in <system-out> so CI UIs surface it. Regression fixtures fail on
BREAKING / VALUE / ERROR; COSMETIC and LATENCY pass with a note.
"""

import xml.etree.ElementTree as ET

_DRIFT_FAILS = ("BREAKING", "VALUE", "ERROR")


def _case(suite: ET.Element, classname: str, name: str) -> ET.Element:
    return ET.SubElement(suite, "testcase", classname=classname, name=name, time="0")


def _suite(root: ET.Element, name: str) -> ET.Element:
    return ET.SubElement(root, "testsuite", name=name)


def _finalize(suite: ET.Element) -> None:
    cases = list(suite)
    suite.set("tests", str(len(cases)))
    suite.set("failures", str(sum(1 for c in cases if c.find("failure") is not None)))
    suite.set("skipped", str(sum(1 for c in cases if c.find("skipped") is not None)))
    suite.set("errors", "0")


def junit_xml(model: dict) -> str:
    root = ET.Element("testsuites", name=f"mcp-proof: {model['server']['name']}")

    for lane_name, lane in (("conformance", model["conformance"]), ("security", model["security"])):
        suite = _suite(root, lane_name)
        for r in lane["checks"]:
            case = _case(suite, f"mcpproof.{lane_name}", f"{r['id']} {r['title']}")
            if r["status"] == "FAIL":
                failure = ET.SubElement(case, "failure", message=r["evidence"][:200] or r["title"])
                failure.text = f"{r['evidence']}\nFix: {r['fix_hint']}"
            elif r["status"] == "SKIP":
                ET.SubElement(case, "skipped", message=r["evidence"][:200])
            elif r["status"] == "WARN":
                out = ET.SubElement(case, "system-out")
                out.text = f"WARN: {r['evidence']}"
        _finalize(suite)

    reg = model.get("regression")
    if reg:
        suite = _suite(root, "regression")
        for d in reg["drifts"]:
            case = _case(suite, "mcpproof.regression", f"{d['tool']} [{d['fixture']}] {d['kind']}")
            if d["kind"] in _DRIFT_FAILS:
                failure = ET.SubElement(case, "failure", message=d["detail"][:200] or d["kind"])
                failure.text = d["detail"]
            elif d["kind"] != "OK":
                out = ET.SubElement(case, "system-out")
                out.text = f"{d['kind']}: {d['detail']}"
        _finalize(suite)

    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"

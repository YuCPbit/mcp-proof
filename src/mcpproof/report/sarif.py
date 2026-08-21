"""SARIF 2.1.0 from the report model — FAIL as error, WARN as warning,
breaking/value/error drifts as errors under synthetic REG-* rules.

The subject is a live server, not a source file, so locations point at a
pseudo-artifact named after the server; GitHub code scanning renders the
rule, level and message either way.
"""

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"

_DRIFT_FAILS = ("BREAKING", "VALUE", "ERROR")


def _location(model: dict) -> dict:
    uri = f"{model['server']['name'] or 'mcp-server'}.mcp"
    return {
        "physicalLocation": {
            "artifactLocation": {"uri": uri.replace(" ", "-")},
            "region": {"startLine": 1},
        }
    }


def sarif_json(model: dict) -> dict:
    rules: dict[str, dict] = {}
    results: list[dict] = []
    loc = _location(model)

    for lane_name, lane in (("conformance", model["conformance"]), ("security", model["security"])):
        for r in lane["checks"]:
            if r["status"] not in ("FAIL", "WARN"):
                continue
            rules.setdefault(r["id"], {
                "id": r["id"],
                "shortDescription": {"text": r["title"]},
                "help": {"text": r["fix_hint"] or r["title"]},
                "properties": {"lane": lane_name, "level": r["level"]},
            })
            results.append({
                "ruleId": r["id"],
                "level": "error" if r["status"] == "FAIL" else "warning",
                "message": {"text": f"{r['title']} — {r['evidence'] or 'no further evidence'}"},
                "locations": [loc],
            })

    reg = model.get("regression")
    if reg:
        for d in reg["drifts"]:
            if d["kind"] == "OK":
                continue
            rule_id = f"REG-{d['kind']}"
            rules.setdefault(rule_id, {
                "id": rule_id,
                "shortDescription": {"text": f"behavioural drift: {d['kind']}"},
                "help": {"text": "Replay of recorded fixtures observed this drift class."},
                "properties": {"lane": "regression"},
            })
            results.append({
                "ruleId": rule_id,
                "level": "error" if d["kind"] in _DRIFT_FAILS else "note",
                "message": {"text": f"{d['tool']} [{d['fixture']}]: {d['detail'] or d['kind']}"},
                "locations": [loc],
            })

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {
                "driver": {
                    "name": model["tool"]["name"],
                    "version": model["tool"]["version"],
                    "informationUri": "https://github.com/YuCPbit/mcp-proof",
                    "rules": sorted(rules.values(), key=lambda r: r["id"]),
                }
            },
            "properties": {
                "runHash": model["run_hash"],
                "behaviorSha256": model["behavior_sha256"],
                "auditStatus": model["audit"]["status"],
                "shipReady": model["verdict"]["ship_ready"],
                "protocolEra": model["server"]["era"],
            },
            "results": results,
        }],
    }

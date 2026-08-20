"""v0.6: two-phase argument synthesis (deterministic coverage) and
schema-violating negative probes (TOOL-07)."""

from pathlib import Path

from _paths import venv_python
from jsonschema import Draft202012Validator

from mcpproof.checks.base import PASS, SKIP, WARN
from mcpproof.checks.conformance import run_conformance
from mcpproof.regression.negative import negative_variants
from mcpproof.regression.sampler import sample_args

PYTHON = venv_python()
MODERN = [PYTHON, str(Path(__file__).resolve().parent / "modern_target_server.py")]


# ------------------------------------------------------ sampler coverage ----


def _valid(schema, args):
    Draft202012Validator(schema).validate(args)
    return args


def test_sampler_resolves_local_refs():
    schema = {
        "type": "object",
        "properties": {"who": {"$ref": "#/$defs/person"}},
        "required": ["who"],
        "$defs": {"person": {"type": "object",
                             "properties": {"name": {"type": "string"}},
                             "required": ["name"]}},
    }
    args = _valid(schema, sample_args(schema))
    assert args["who"]["name"] == "example"


def test_sampler_merges_allof():
    schema = {
        "type": "object",
        "properties": {
            "q": {"allOf": [
                {"type": "string"},
                {"minLength": 10},
            ]},
        },
        "required": ["q"],
    }
    args = _valid(schema, sample_args(schema))
    assert len(args["q"]) >= 10


def test_sampler_const_pattern_format_bounds():
    schema = {
        "type": "object",
        "properties": {
            "mode": {"const": "fast"},
            "code": {"type": "string", "pattern": "^[a-z]{3}$"},
            "when": {"type": "string", "format": "date"},
            "count": {"type": "integer", "exclusiveMinimum": 4, "multipleOf": 5},
            "ratio": {"type": "number", "minimum": 2.5},
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        },
        "required": ["mode", "code", "when", "count", "ratio", "tags"],
    }
    args = _valid(schema, sample_args(schema))
    assert args["mode"] == "fast"
    assert args["when"] == "2024-01-01"
    assert args["count"] % 5 == 0 and args["count"] > 4
    assert args["ratio"] >= 2.5
    assert len(args["tags"]) == 2


def test_sampler_is_deterministic():
    schema = {
        "type": "object",
        "properties": {"q": {"type": "string", "pattern": "^[a-z]+$"}},
        "required": ["q"],
    }
    assert sample_args(schema) == sample_args(schema)


# ------------------------------------------------------ negative variants ----


def test_negative_variants_are_verified_invalid():
    schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "maxLength": 10},
            "n": {"type": "integer", "maximum": 5},
        },
        "required": ["text", "n"],
    }
    variants = negative_variants(schema, limit=3)
    assert variants, "constrained schema must yield negative variants"
    validator = Draft202012Validator(schema)
    for case, args in variants:
        assert not validator.is_valid(args), (case, args)


def test_negative_variants_empty_for_unusable_schema():
    assert negative_variants({}) == []
    assert negative_variants({"type": "object", "properties": {}}) == []


def test_negative_boolean_uses_int_not_string():
    schema = {
        "type": "object",
        "properties": {"flag": {"type": "boolean"}},
        "required": ["flag"],
    }
    variants = dict(negative_variants(schema))
    flipped = [v["flag"] for v in variants.values() if "flag" in v and v["flag"] is not True]
    assert flipped and all(not isinstance(v, str) for v in flipped), (
        "lax validators coerce 'yes'-style strings — the type flip must be an int"
    )


# ------------------------------------------------------------- TOOL-07 ----


async def test_tool07_passes_on_strict_server():
    outcome = await run_conformance(MODERN)
    t07 = {r.id: r for r in outcome.results}["TOOL-07"]
    assert t07.status == PASS, t07.evidence
    assert "all rejected" in t07.evidence


async def test_tool07_warns_on_loose_server():
    outcome = await run_conformance(MODERN + ["--loose-validation"])
    t07 = {r.id: r for r in outcome.results}["TOOL-07"]
    assert t07.status == WARN, (t07.status, t07.evidence)
    assert "not enforced" in t07.evidence
    assert "minimal invalid input" in t07.evidence


async def test_tool07_skips_without_tools():
    cmd = [PYTHON, str(Path(__file__).resolve().parent / "resources_only_server.py")]
    outcome = await run_conformance(cmd)
    t07 = {r.id: r for r in outcome.results}["TOOL-07"]
    assert t07.status == SKIP

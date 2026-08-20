import hashlib
import json


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def obj_hash(obj) -> str:
    return sha256_hex(canonical_json(obj))


def run_hash(part_hashes: list[str]) -> str:
    """Aggregate fingerprint over an ordered list of component hashes."""
    return sha256_hex("\n".join(part_hashes))

from __future__ import annotations
import json
import hashlib
from typing import Any

def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x

def canon_json_bytes(x: Any) -> bytes:
    x = _jsonable(x)
    return json.dumps(
        x,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")

def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def chain_hash(prev_chain_root: str, step_merkle_root: str) -> str:
    if not isinstance(prev_chain_root, str) or len(prev_chain_root) != 64:
        raise ValueError("prev_chain_root must be 64-hex")
    if not isinstance(step_merkle_root, str) or len(step_merkle_root) != 64:
        raise ValueError("step_merkle_root must be 64-hex")
    return sha256_hex(canon_json_bytes([prev_chain_root, step_merkle_root]))

def genesis_root() -> str:
    return "0" * 64

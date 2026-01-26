from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def replay_verify_step_dir(step_dir: Path) -> Dict[str, Any]:
    from scripts.verify_bundle import verify_step_dir as _verify_step_dir

    out = _verify_step_dir(str(step_dir))

    ok = False
    reason = "NONE"
    merkle_root = ""
    leaf_hashes: List[str] = []
    step_dir_s = str(step_dir)

    if isinstance(out, dict):
        ok = bool(out.get("ok", False))
        reason = str(out.get("reason") or "NONE")
        merkle_root = str(out.get("merkle_root") or "")
        leaf_hashes_raw = out.get("leaf_hashes", [])
        if isinstance(leaf_hashes_raw, list):
            leaf_hashes = [str(x) for x in leaf_hashes_raw]
        step_dir_s = str(out.get("step_dir") or step_dir_s)

    elif isinstance(out, tuple):
        ok = bool(out[0]) if len(out) >= 1 else False
        reason = str(out[1] or "NONE") if len(out) >= 2 else "NONE"
        merkle_root = str(out[2] or "") if len(out) >= 3 else ""
        leaf_hashes = []

    root_hash_txt = ""
    try:
        root_hash_txt = _read_text(step_dir / "root_hash.txt")
    except Exception:
        root_hash_txt = ""

    if not merkle_root:
        try:
            b = _read_json(step_dir / "bundle.json")
            merkle_root = str(b.get("merkle_root") or "")
        except Exception:
            merkle_root = ""

    if not merkle_root:
        merkle_root = root_hash_txt

    return {
        "schema": "api.replay_verify_step.v1",
        "step_dir": step_dir_s,
        "ok": bool(ok),
        "reason": str(reason or "NONE"),
        "merkle_root": str(merkle_root or ""),
        "leaf_hashes": leaf_hashes,
        "root_hash_txt": str(root_hash_txt or ""),
        "ts_ms": int(time.time() * 1000),
    }

def _historical_step_dir(stream_id: str, step_number: int) -> Path:
    import os

    root = Path(os.getenv("VSC_HISTORICAL_ROOT", "out/historical"))
    step_name = f"step_{int(step_number):06d}"
    return root / str(stream_id) / step_name


def audit_verify_historical(stream_id: str, step_number: int) -> dict:
    import time

    step_dir = _historical_step_dir(stream_id, step_number)

    if not step_dir.exists():
        out = {
            "schema": "api.audit_verify_historical.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": False,
            "reason": "MISSING_STEP_DIR",
            "merkle_root": "",
            "root_hash_txt": "",
            "leaf_hashes": [],
            "same_hash": False,
            "storage": {
                "backend": "filesystem",
                "historical_root": str(step_dir.parent.parent),
                "object_prefix": f"{stream_id}/step_{int(step_number):06d}/",
                "fetched_ok": False,
            },
            "signature_valid": False,
            "ts_ms": int(time.time() * 1000.0),
        }
        return out

    out = replay_verify_step_dir(step_dir)

    root_hash_txt = str(out.get("root_hash_txt", ""))
    merkle_root = str(out.get("merkle_root", ""))

    same_hash = bool(root_hash_txt) and bool(merkle_root) and (root_hash_txt == merkle_root)

    out2 = {
        "schema": "api.audit_verify_historical.v1",
        "stream_id": str(stream_id),
        "step_number": int(step_number),
        "ok": bool(out.get("ok", False)),
        "reason": str(out.get("reason", "")),
        "merkle_root": merkle_root,
        "root_hash_txt": root_hash_txt,
        "leaf_hashes": list(out.get("leaf_hashes", [])),
        "same_hash": bool(same_hash),
        "storage": {
            "backend": "filesystem",
            "historical_root": str(step_dir.parent.parent),
            "object_prefix": f"{stream_id}/step_{int(step_number):06d}/",
            "fetched_ok": True,
        },
        "signature_valid": False,
        "ts_ms": int(time.time() * 1000.0),
    }
    return out2

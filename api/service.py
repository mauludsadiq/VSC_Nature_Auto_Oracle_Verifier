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

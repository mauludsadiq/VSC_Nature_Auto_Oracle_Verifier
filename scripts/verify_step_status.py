#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        out = {}
        bad = False
        for k in x.keys():
            if not isinstance(k, (str, int, float, bool)) and k is not None:
                bad = True
                break
        if bad:
            items = []
            for k, v in x.items():
                if isinstance(k, tuple) and all(isinstance(t, str) for t in k):
                    k2 = "|".join(k)
                else:
                    k2 = repr(k)
                items.append((k2, _jsonable(v)))
            items.sort(key=lambda kv: kv[0])
            return {"__tuplekey_dict__": items}
        for k, v in x.items():
            out[str(k)] = _jsonable(v)
        return out
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
    import hashlib
    return hashlib.sha256(b).hexdigest()


def canon_hash(x: Any) -> str:
    return sha256_hex(canon_json_bytes(x))


def merkle_pair(h1: str, h2: str) -> str:
    return sha256_hex(canon_json_bytes([h1, h2]))


def merkle_root(leaves: List[str]) -> str:
    if len(leaves) == 0:
        return sha256_hex(canon_json_bytes(["EMPTY"]))
    lvl = list(leaves)
    while len(lvl) > 1:
        if len(lvl) % 2 == 1:
            lvl.append(lvl[-1])
        nxt: List[str] = []
        for i in range(0, len(lvl), 2):
            nxt.append(merkle_pair(lvl[i], lvl[i + 1]))
        lvl = nxt
    return lvl[0]


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def status_from_bundle(bundle: Dict[str, Any]) -> str:
    leaf = bundle.get("leaf_verdicts", {}) or {}
    sel = str(bundle.get("selected_action", ""))

    pass_all = True
    for v in leaf.values():
        if str(v).upper() != "PASS":
            pass_all = False
            break

    if pass_all:
        return "PASS"

    vt = str(leaf.get("value_table", "")).upper()
    rg = str(leaf.get("risk_gate", "")).upper()
    if vt == "FAIL" and sel == "ABSTAIN" and rg == "PASS":
        return "DETECTED_VALUE_FORGERY"

    return "FAIL"


def verify_step_dir(step_dir: Path, strict_value_children: bool) -> Dict[str, Any]:
    bundle_path = step_dir / "bundle.json"
    root_path = step_dir / "root_hash.txt"
    if not bundle_path.exists():
        return {"ok": False, "reason": f"missing {bundle_path.name}"}
    if not root_path.exists():
        return {"ok": False, "reason": f"missing {root_path.name}"}

    bundle = _read_json(bundle_path)
    expected_root = root_path.read_text(encoding="utf-8").strip()

    # Leaf hashes from actual witness files (source of truth)
    file_map = {
        "percept": "w_percept.json",
        "model_contract": "w_model_contract.json",
        "value_table": "w_value.json",
        "risk_gate": "w_risk.json",
        "exec": "w_exec.json",
    }
    leaf_order = ["percept", "model_contract", "value_table", "risk_gate", "exec"]

    leaf_hashes: Dict[str, str] = {}
    for name in leaf_order:
        fn = file_map[name]
        p = step_dir / fn
        if not p.exists():
            return {"ok": False, "reason": f"missing {fn}"}
        leaf_hashes[name] = canon_hash(_read_json(p))

    computed_root = merkle_root([leaf_hashes[k] for k in leaf_order])
    if computed_root != expected_root:
        return {
            "ok": False,
            "reason": "merkle_root_mismatch",
            "expected_root": expected_root,
            "computed_root": computed_root,
        }

    # Optional strict verification: value_children list in bundle must match files
    if strict_value_children:
        vc = bundle.get("value_children", []) or []
        for ent in vc:
            fn = ent.get("file")
            hx = ent.get("hash")
            if not fn or not hx:
                return {"ok": False, "reason": "bad_value_children_entry"}
            p = step_dir / str(fn)
            if not p.exists():
                return {"ok": False, "reason": f"missing_value_child {fn}"}
            got = canon_hash(_read_json(p))
            if got != str(hx):
                return {"ok": False, "reason": f"value_child_hash_mismatch {fn}", "expected": hx, "got": got}

    return {"ok": True, "bundle": bundle}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step_dir")
    ap.add_argument("--strict-value-children", action="store_true")
    ap.add_argument("--detected-ok", action="store_true")
    args = ap.parse_args()

    step_dir = Path(args.step_dir)

    res = verify_step_dir(step_dir, strict_value_children=args.strict_value_children)
    if not res.get("ok"):
        print(f"FAIL_VERIFY_STEP_STATUS: {step_dir.name}")
        print("reason:", res.get("reason"))
        raise SystemExit(1)

    bundle = res["bundle"]
    st = status_from_bundle(bundle)

    if st == "PASS":
        print(f"PASS_VERIFY_STEP_STATUS: {step_dir.name}")
        raise SystemExit(0)

    if st == "DETECTED_VALUE_FORGERY":
        print(f"DETECTED_VERIFY_STEP_STATUS: {step_dir.name}")
        if args.detected_ok:
            raise SystemExit(0)
        raise SystemExit(2)

    print(f"FAIL_VERIFY_STEP_STATUS: {step_dir.name}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()

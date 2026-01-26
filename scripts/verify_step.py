#!/usr/bin/env python3
"""
Replay verification for a single step directory.

Verifies:
  1) Each witness file hash matches bundle["leaves"] entries.
  2) Merkle root recomputed from leaves (canonical order) matches:
       - bundle["merkle_root"]
       - root_hash.txt
  3) (Optional) value_children hashes match bundle["value_children"]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


LEAF_ORDER = ["percept", "model_contract", "value_table", "risk_gate", "exec"]

LEAF_FILES = {
    "percept": "w_percept.json",
    "model_contract": "w_model_contract.json",
    "value_table": "w_value.json",
    "risk_gate": "w_risk.json",
    "exec": "w_exec.json",
}


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        out: Dict[str, Any] = {}
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


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def verify_step(step_dir: Path, strict_value_children: bool = False) -> int:
    if not step_dir.exists():
        print(f"FAIL_STEP_NOT_FOUND: {step_dir}")
        return 2

    bundle_path = step_dir / "bundle.json"
    root_path = step_dir / "root_hash.txt"

    if not bundle_path.exists():
        print(f"FAIL_MISSING_BUNDLE: {bundle_path}")
        return 2
    if not root_path.exists():
        print(f"FAIL_MISSING_ROOT_HASH: {root_path}")
        return 2

    bundle = _read_json(bundle_path)

    bundle_root = str(bundle.get("merkle_root", "")).strip()
    disk_root = _read_text(root_path)

    if not bundle_root:
        print("FAIL_BUNDLE_MISSING_MERKLE_ROOT")
        return 2

    # leaves in bundle: [{"name": k, "hash": h}, ...]
    leaves_list = bundle.get("leaves", [])
    if not isinstance(leaves_list, list) or len(leaves_list) == 0:
        print("FAIL_BUNDLE_MISSING_LEAVES")
        return 2

    expected_leaf_hash: Dict[str, str] = {}
    for item in leaves_list:
        if not isinstance(item, dict):
            continue
        nm = item.get("name")
        hh = item.get("hash")
        if isinstance(nm, str) and isinstance(hh, str):
            expected_leaf_hash[nm] = hh

    # 1) Verify witness file hashes match expected leaf hashes
    ok = True
    computed_leaf_hash: Dict[str, str] = {}

    for nm in LEAF_ORDER:
        fn = LEAF_FILES.get(nm)
        if fn is None:
            continue
        path = step_dir / fn
        if not path.exists():
            print(f"FAIL_MISSING_WITNESS: {fn}")
            ok = False
            continue

        w = _read_json(path)
        h = canon_hash(w)
        computed_leaf_hash[nm] = h

        exp = expected_leaf_hash.get(nm, None)
        if exp is None:
            print(f"WARN_NO_LEAF_ENTRY: {nm}")
        elif h != exp:
            print(f"FAIL_LEAF_HASH_MISMATCH: {nm}")
            print(f"  expected={exp}")
            print(f"  actual  ={h}")
            ok = False

    # 2) Verify merkle root recomputed matches bundle root and disk root
    leaf_hashes_ordered = [computed_leaf_hash.get(nm, "") for nm in LEAF_ORDER]
    if any(h == "" for h in leaf_hashes_ordered):
        print("FAIL_MISSING_COMPUTED_LEAF_HASHES_FOR_MERKLE")
        ok = False
    else:
        computed_root = merkle_root(leaf_hashes_ordered)

        if computed_root != bundle_root:
            print("FAIL_MERKLE_ROOT_MISMATCH_BUNDLE")
            print(f"  bundle   ={bundle_root}")
            print(f"  computed ={computed_root}")
            ok = False

        if computed_root != disk_root:
            print("FAIL_MERKLE_ROOT_MISMATCH_DISK")
            print(f"  root_hash.txt={disk_root}")
            print(f"  computed     ={computed_root}")
            ok = False

    # 3) Optional: verify value_children file hashes match bundle["value_children"]
    if strict_value_children:
        vc = bundle.get("value_children", [])
        if not isinstance(vc, list):
            print("FAIL_VALUE_CHILDREN_NOT_LIST")
            ok = False
        else:
            for item in vc:
                if not isinstance(item, dict):
                    continue
                file = item.get("file")
                exp = item.get("hash")
                if not isinstance(file, str) or not isinstance(exp, str):
                    continue
                p = step_dir / file
                if not p.exists():
                    print(f"FAIL_MISSING_VALUE_CHILD_FILE: {file}")
                    ok = False
                    continue
                w = _read_json(p)
                h = canon_hash(w)
                if h != exp:
                    print(f"FAIL_VALUE_CHILD_HASH_MISMATCH: {file}")
                    print(f"  expected={exp}")
                    print(f"  actual  ={h}")
                    ok = False

    if ok:
        print(f"PASS_VERIFY_STEP: {step_dir.name}")
        return 0

    print(f"FAIL_VERIFY_STEP: {step_dir.name}")
    return 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step_dir", help="e.g., out/stream/step_000025")
    ap.add_argument(
        "--strict-value-children",
        action="store_true",
        help="Also verify bundle.value_children hashes (w_value_*.json).",
    )
    args = ap.parse_args()

    rc = verify_step(Path(args.step_dir), strict_value_children=args.strict_value_children)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()

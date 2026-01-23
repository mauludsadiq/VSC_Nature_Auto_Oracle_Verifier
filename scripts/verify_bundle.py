from __future__ import annotations
import os
import sys
import json
import hashlib
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
    return hashlib.sha256(b).hexdigest()


def hash_canon(x: Any) -> str:
    return sha256_hex(canon_json_bytes(x))


def _hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(h)


def merkle_root_from_leaf_hashes(leaf_hex: List[str]) -> str:
    if not leaf_hex:
        raise ValueError("empty leaf set")
    level = [_hex_to_bytes(h) for h in leaf_hex]
    while len(level) > 1:
        nxt: List[bytes] = []
        i = 0
        while i < len(level):
            left = level[i]
            right = level[i + 1] if (i + 1) < len(level) else level[i]
            nxt.append(hashlib.sha256(left + right).digest())
            i += 2
        level = nxt
    return level[0].hex()


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_step_dir(step_dir: str) -> Dict[str, Any]:
    bundle_path = os.path.join(step_dir, "bundle.json")
    if not os.path.isfile(bundle_path):
        raise FileNotFoundError(bundle_path)

    bundle = load_json(bundle_path)

    leaf_map = {
        "percept": "w_percept.json",
        "model_contract": "w_model_contract.json",
        "value_table": "w_value.json",
        "risk_gate": "w_risk.json",
        "exec": "w_exec.json",
    }

    leaf_verdicts = bundle.get("leaf_verdicts", {})
    leaf_hashes: List[str] = []
    leaf_replay: Dict[str, Dict[str, Any]] = {}

    for leaf_name, fname in leaf_map.items():
        p = os.path.join(step_dir, fname)
        if not os.path.isfile(p):
            raise FileNotFoundError(p)

        w = load_json(p)
        leaf_replay[leaf_name] = w

        h = hash_canon(w)
        leaf_hashes.append(h)

        expected_v = leaf_verdicts.get(leaf_name)
        actual_v = w.get("verdict")
        verdict_ok = (expected_v is None) or (expected_v == actual_v)

        if not verdict_ok:
            return {
                "ok": False,
                "reason": "LEAF_VERDICT_MISMATCH",
                "leaf": leaf_name,
                "expected": expected_v,
                "actual": actual_v,
                "step_dir": step_dir,
            }

    root_replay = merkle_root_from_leaf_hashes(leaf_hashes)
    root_bundle = bundle.get("merkle_root")

    if root_bundle is None:
        return {
            "ok": False,
            "reason": "BUNDLE_MISSING_MERKLE_ROOT",
            "step_dir": step_dir,
        }

    if root_replay != root_bundle:
        return {
            "ok": False,
            "reason": "MERKLE_ROOT_MISMATCH",
            "root_bundle": root_bundle,
            "root_replay": root_replay,
            "leaf_hashes": leaf_hashes,
            "step_dir": step_dir,
        }

    root_txt = os.path.join(step_dir, "root_hash.txt")
    if os.path.isfile(root_txt):
        with open(root_txt, "r", encoding="utf-8") as f:
            root_file = f.read().strip()
        if root_file and (root_file != root_bundle):
            return {
                "ok": False,
                "reason": "ROOT_HASH_TXT_MISMATCH",
                "root_bundle": root_bundle,
                "root_hash_txt": root_file,
                "step_dir": step_dir,
            }

    return {
        "ok": True,
        "reason": "PASS_VERIFY_BUNDLE",
        "step_dir": step_dir,
        "merkle_root": root_bundle,
        "leaf_hashes": leaf_hashes,
    }


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m scripts.verify_bundle <out/stream/step_000123>", file=sys.stderr)
        return 2

    step_dir = argv[1]
    result = verify_step_dir(step_dir)

    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

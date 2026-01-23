from __future__ import annotations
import os
import sys
import json
from typing import Any, Dict, List

from scripts.verify_audit_chain import canon_hash, merkle_root


LEAF_FILE_MAP = {
    "percept": "w_percept.json",
    "model_contract": "w_model_contract.json",
    "value_table": "w_value.json",
    "risk_gate": "w_risk.json",
    "exec": "w_exec.json",
}


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_step_dir(step_dir: str) -> Dict[str, Any]:
    bundle_path = os.path.join(step_dir, "bundle.json")
    if not os.path.isfile(bundle_path):
        raise FileNotFoundError(bundle_path)

    bundle = load_json(bundle_path)

    root_bundle = bundle.get("merkle_root")
    if root_bundle is None or not isinstance(root_bundle, str):
        return {"ok": False, "reason": "BUNDLE_MISSING_MERKLE_ROOT", "step_dir": step_dir}

    leaves = bundle.get("leaves")
    if not isinstance(leaves, list) or not leaves:
        return {"ok": False, "reason": "BUNDLE_MISSING_LEAVES", "step_dir": step_dir}

    leaf_hashes_recomputed: List[str] = []
    leaf_hashes_from_bundle: List[str] = []

    for item in leaves:
        if not isinstance(item, dict):
            return {"ok": False, "reason": "BUNDLE_LEAF_SCHEMA_BAD", "step_dir": step_dir}

        name = item.get("name")
        h_expected = item.get("hash")

        if not isinstance(name, str) or not isinstance(h_expected, str):
            return {"ok": False, "reason": "BUNDLE_LEAF_SCHEMA_BAD", "step_dir": step_dir}

        fname = LEAF_FILE_MAP.get(name)
        if fname is None:
            return {
                "ok": False,
                "reason": "UNKNOWN_LEAF_NAME",
                "leaf_name": name,
                "step_dir": step_dir,
            }

        fpath = os.path.join(step_dir, fname)
        if not os.path.isfile(fpath):
            return {
                "ok": False,
                "reason": "MISSING_LEAF_FILE",
                "leaf_name": name,
                "leaf_file": fname,
                "step_dir": step_dir,
            }

        w = load_json(fpath)
        h_actual = canon_hash(w)

        leaf_hashes_from_bundle.append(h_expected)
        leaf_hashes_recomputed.append(h_actual)

        if h_actual != h_expected:
            return {
                "ok": False,
                "reason": "LEAF_HASH_MISMATCH",
                "leaf_name": name,
                "expected": h_expected,
                "actual": h_actual,
                "step_dir": step_dir,
            }

    root_replay = merkle_root(leaf_hashes_from_bundle)

    if root_replay != root_bundle:
        return {
            "ok": False,
            "reason": "MERKLE_ROOT_MISMATCH",
            "root_bundle": root_bundle,
            "root_replay": root_replay,
            "leaf_hashes": leaf_hashes_from_bundle,
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
        "leaf_hashes": leaf_hashes_from_bundle,
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

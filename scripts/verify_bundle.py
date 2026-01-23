from __future__ import annotations
import os
import sys
import json
import argparse
from typing import Any, Dict, List, Optional

from scripts.verify_audit_chain import canon_hash, merkle_root
from scripts.chain_root import chain_hash, genesis_root

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

def _step_parent_dir(step_dir: str) -> Optional[str]:
    base = os.path.basename(os.path.normpath(step_dir))
    parent = os.path.dirname(os.path.normpath(step_dir))
    if not base.startswith("step_"):
        return None
    suf = base.split("step_", 1)[1]
    if not suf.isdigit():
        return None
    idx = int(suf)
    if idx <= 0:
        return None
    prev = f"step_{idx-1:06d}"
    prev_dir = os.path.join(parent, prev)
    return prev_dir

def verify_step_dir(step_dir: str, require_signature: bool = False, verify_chain_mode: bool = False) -> Dict[str, Any]:
    bundle_path = os.path.join(step_dir, "bundle.json")
    if not os.path.isfile(bundle_path):
        return {"ok": False, "reason": "MISSING_BUNDLE_JSON", "step_dir": step_dir}

    bundle = load_json(bundle_path)

    root_bundle = bundle.get("merkle_root")
    if root_bundle is None or not isinstance(root_bundle, str):
        return {"ok": False, "reason": "BUNDLE_MISSING_MERKLE_ROOT", "step_dir": step_dir}

    leaves = bundle.get("leaves")
    if not isinstance(leaves, list) or not leaves:
        return {"ok": False, "reason": "BUNDLE_MISSING_LEAVES", "step_dir": step_dir}

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
            return {"ok": False, "reason": "UNKNOWN_LEAF_NAME", "leaf_name": name, "step_dir": step_dir}

        fpath = os.path.join(step_dir, fname)
        if not os.path.isfile(fpath):
            return {"ok": False, "reason": "MISSING_LEAF_FILE", "leaf_name": name, "leaf_file": fname, "step_dir": step_dir}

        w = load_json(fpath)
        h_actual = canon_hash(w)

        leaf_hashes_from_bundle.append(h_expected)

        if h_actual != h_expected:
            return {"ok": False, "reason": "LEAF_HASH_MISMATCH", "leaf_name": name, "expected": h_expected, "actual": h_actual, "step_dir": step_dir}

    root_replay = merkle_root(leaf_hashes_from_bundle)
    if root_replay != root_bundle:
        return {"ok": False, "reason": "MERKLE_ROOT_MISMATCH", "root_bundle": root_bundle, "root_replay": root_replay, "leaf_hashes": leaf_hashes_from_bundle, "step_dir": step_dir}

    root_txt = os.path.join(step_dir, "root_hash.txt")
    if os.path.isfile(root_txt):
        with open(root_txt, "r", encoding="utf-8") as f:
            root_file = f.read().strip()
        if root_file and (root_file != root_bundle):
            return {"ok": False, "reason": "ROOT_HASH_TXT_MISMATCH", "root_bundle": root_bundle, "root_hash_txt": root_file, "step_dir": step_dir}

    if verify_chain_mode:
        prev_chain_root = bundle.get("prev_chain_root")
        chain_root_b = bundle.get("chain_root")
        if not isinstance(prev_chain_root, str) or len(prev_chain_root) != 64:
            prev_chain_root = genesis_root()
        if not isinstance(chain_root_b, str) or len(chain_root_b) != 64:
            return {"ok": False, "reason": "BUNDLE_MISSING_CHAIN_ROOT", "step_dir": step_dir}

        parent_dir = _step_parent_dir(step_dir)
        if parent_dir is None:
            expected = chain_hash(prev_chain_root, root_bundle)
            if expected != chain_root_b:
                return {"ok": False, "reason": "CHAIN_ROOT_MISMATCH", "chain_root_bundle": chain_root_b, "chain_root_replay": expected, "step_dir": step_dir}
        else:
            parent_bundle_path = os.path.join(parent_dir, "bundle.json")
            if not os.path.isfile(parent_bundle_path):
                return {"ok": False, "reason": "CHAIN_PARENT_MISSING", "parent_step_dir": parent_dir, "step_dir": step_dir}
            pb = load_json(parent_bundle_path)
            parent_chain = pb.get("chain_root")
            if not isinstance(parent_chain, str) or len(parent_chain) != 64:
                return {"ok": False, "reason": "CHAIN_PARENT_MISSING_CHAIN_ROOT", "parent_step_dir": parent_dir, "step_dir": step_dir}
            if parent_chain != prev_chain_root:
                return {"ok": False, "reason": "CHAIN_LINK_MISMATCH", "expected_prev_chain_root": parent_chain, "bundle_prev_chain_root": prev_chain_root, "step_dir": step_dir}
            expected = chain_hash(prev_chain_root, root_bundle)
            if expected != chain_root_b:
                return {"ok": False, "reason": "CHAIN_ROOT_MISMATCH", "chain_root_bundle": chain_root_b, "chain_root_replay": expected, "step_dir": step_dir}

    if require_signature:
        sig = bundle.get("signature")
        vk = bundle.get("verifier_pubkey")
        if not isinstance(sig, str) or not isinstance(vk, str):
            return {"ok": False, "reason": "MISSING_SIGNATURE", "step_dir": step_dir}
        return {"ok": True, "reason": "PASS_VERIFY_BUNDLE_SIGNED", "step_dir": step_dir, "merkle_root": root_bundle, "leaf_hashes": leaf_hashes_from_bundle}

    return {"ok": True, "reason": "PASS_VERIFY_BUNDLE", "step_dir": step_dir, "merkle_root": root_bundle, "leaf_hashes": leaf_hashes_from_bundle}

def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step_dir")
    ap.add_argument("--require-signature", action="store_true")
    ap.add_argument("--verify-chain", action="store_true")
    args = ap.parse_args(argv[1:])

    out = verify_step_dir(args.step_dir, require_signature=args.require_signature, verify_chain_mode=args.verify_chain)
    print(json.dumps(out, sort_keys=True))
    return 0 if out.get("ok") else 1

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

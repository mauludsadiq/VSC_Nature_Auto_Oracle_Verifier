import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import argparse
import re

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
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

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
            nxt.append(merkle_pair(lvl[i], lvl[i+1]))
        lvl = nxt
    return lvl[0]

def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--witness_dir", required=True)
    ap.add_argument("--root_hash", default=None)
    args = ap.parse_args()

    wd = Path(args.witness_dir)
    if not wd.exists():
        raise SystemExit(f"witness_dir not found: {wd}")

    step_dirs = sorted([p for p in wd.glob("step_*") if p.is_dir()])

    step_ids = []
    for d in step_dirs:
        m = re.match(r"step_(\d{6})$", d.name)
        if not m:
            raise SystemExit("FAIL_STEP_DIR_NAME")
        step_ids.append(int(m.group(1)))

    if len(step_ids) != len(set(step_ids)):
        raise SystemExit("FAIL_STEP_DUPLICATE")

    if step_ids and step_ids[0] != 0:
        raise SystemExit("FAIL_STEP_NOT_ZERO")

    for i, v in enumerate(step_ids):
        if v != i:
            raise SystemExit("FAIL_STEP_SEQUENCE")

    if not step_dirs:
        raise SystemExit("no step_* dirs found")

    for sd in step_dirs:

        expected_base = {
            "bundle.json",
            "root_hash.txt",
            "w_percept.json",
            "w_model_contract.json",
            "w_value.json",
            "w_risk.json",
            "w_exec.json",
        }
        present = {x.name for x in sd.iterdir() if x.is_file()}
        missing = sorted(expected_base - present)
        extra = sorted(present - expected_base)

        allowed_extra = [x for x in extra if x.startswith("w_value_") and x.endswith(".json")]
        forbidden_extra = [x for x in extra if x not in allowed_extra]

        if missing:
            raise SystemExit("FAIL_STEP_FILES_MISSING:" + ",".join(missing))
        if forbidden_extra:
            raise SystemExit("FAIL_STEP_FILES_EXTRA:" + ",".join(sorted(forbidden_extra)))

        bundle_path = sd / "bundle.json"
        root_path = sd / "root_hash.txt"
        if not bundle_path.exists() or not root_path.exists():
            raise SystemExit(f"missing bundle/root in {sd}")

        bundle = load_json(bundle_path)
        root_txt = root_path.read_text(encoding="utf-8").strip()
        if root_txt != bundle["merkle_root"]:
            raise SystemExit(f"root mismatch in {sd}")

        leaf_order = []
        leaf_hashes = []
        if "leaves" in bundle:
            for item in bundle["leaves"]:
                leaf_order.append(item["name"])
                leaf_hashes.append(item["hash"])
        else:
            w_model = load_json(sd / "w_model_contract.json")
            w_value = load_json(sd / "w_value.json")
            w_risk = load_json(sd / "w_risk.json")
            w_exec = load_json(sd / "w_exec.json")
            leaf_order = ["model_contract", "value_table", "risk_gate", "exec"]
            leaf_hashes = [canon_hash(w_model), canon_hash(w_value), canon_hash(w_risk), canon_hash(w_exec)]

        recomputed = merkle_root(leaf_hashes)
        if recomputed != bundle["merkle_root"]:
            raise SystemExit(f"merkle recompute mismatch in {sd}")

        step = bundle.get("step_counter", sd.name)
        action = bundle.get("selected_action", "UNKNOWN")
        print(f"[VERIFIED] Step {step}: action={action} root={bundle['merkle_root'][:12]} msg=ok")

    if args.root_hash is not None:
        last = load_json(step_dirs[-1] / "bundle.json")["merkle_root"]
        if not last.startswith(args.root_hash) and last != args.root_hash:
            raise SystemExit("provided root_hash does not match last step merkle root")

    print("[CHAIN VERIFIED] All steps verified.")

if __name__ == "__main__":
    main()

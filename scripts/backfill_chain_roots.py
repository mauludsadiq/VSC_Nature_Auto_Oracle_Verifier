from __future__ import annotations

import os
import re
import json
from typing import Any, List

from scripts.chain_root import chain_hash, genesis_root

def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def dump_json(path: str, x: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n")

def list_step_dirs(stream_dir: str) -> List[str]:
    out = []
    for name in os.listdir(stream_dir):
        if re.fullmatch(r"step_\d{6}", name):
            out.append(os.path.join(stream_dir, name))
    out.sort()
    return out

def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("stream_dir")
    args = ap.parse_args()

    stream_dir = args.stream_dir
    if not os.path.isdir(stream_dir):
        raise SystemExit(f"not a dir: {stream_dir}")

    step_dirs = list_step_dirs(stream_dir)
    if not step_dirs:
        raise SystemExit("no step_XXXXXX dirs found")

    chain_prev = genesis_root()

    wrote = 0
    for sd in step_dirs:
        bundle_path = os.path.join(sd, "bundle.json")
        if not os.path.isfile(bundle_path):
            raise SystemExit(f"missing bundle.json: {bundle_path}")

        bundle = load_json(bundle_path)
        step_root = bundle.get("merkle_root")
        if not isinstance(step_root, str) or len(step_root) != 64:
            raise SystemExit(f"bad merkle_root in {bundle_path}")

        prev_chain_root = bundle.get("prev_chain_root")
        if not isinstance(prev_chain_root, str) or len(prev_chain_root) != 64:
            prev_chain_root = chain_prev

        cr = chain_hash(prev_chain_root, step_root)

        bundle["prev_chain_root"] = prev_chain_root
        bundle["chain_root"] = cr

        dump_json(bundle_path, bundle)

        with open(os.path.join(sd, "chain_root.txt"), "w", encoding="utf-8") as f:
            f.write(cr + "\n")

        chain_prev = cr
        wrote += 1

    print(json.dumps({"ok": True, "reason": "PASS_BACKFILL_CHAIN_ROOTS", "steps": wrote, "final_chain_root": chain_prev}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

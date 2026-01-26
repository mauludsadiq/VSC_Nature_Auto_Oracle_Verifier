#!/usr/bin/env python3
"""
Verify the append-only chain across step directories.

Contract:
  step_i has:
    - root_hash.txt     (merkle root of leaves for that step)
    - chain_root.txt    (hash-chain root through step i)

We recompute chain incrementally and verify each chain_root.txt.

Chain definition (deterministic):
  H0 = sha256(canon(["GENESIS"]))
  H_{i+1} = sha256(canon([H_i, root_i]))
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, List, Tuple


def canon_json_bytes(x: Any) -> bytes:
    return json.dumps(
        x,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def chain_pair(prev_chain: str, step_root: str) -> str:
    return sha256_hex(canon_json_bytes([prev_chain, step_root]))


def read_hash(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def list_steps(stream_dir: Path) -> List[Tuple[int, Path]]:
    out: List[Tuple[int, Path]] = []
    for d in sorted(stream_dir.glob("step_*")):
        if not d.is_dir():
            continue
        name = d.name
        if not name.startswith("step_"):
            continue
        try:
            k = int(name.split("_", 1)[1])
        except Exception:
            continue
        out.append((k, d))
    out.sort(key=lambda kv: kv[0])
    return out


def verify_chain(stream_dir: Path) -> int:
    if not stream_dir.exists():
        print(f"FAIL_STREAM_NOT_FOUND: {stream_dir}")
        return 2

    steps = list_steps(stream_dir)
    if not steps:
        print(f"FAIL_NO_STEPS_FOUND: {stream_dir}")
        return 2

    genesis = sha256_hex(canon_json_bytes(["GENESIS"]))
    chain = genesis

    ok = True

    for k, d in steps:
        root_p = d / "root_hash.txt"
        chain_p = d / "chain_root.txt"

        if not root_p.exists():
            print(f"FAIL_MISSING_ROOT_HASH: {d.name}/root_hash.txt")
            ok = False
            break

        if not chain_p.exists():
            print(f"FAIL_MISSING_CHAIN_ROOT: {d.name}/chain_root.txt")
            ok = False
            break

        step_root = read_hash(root_p)
        expected_chain = chain_pair(chain, step_root)
        observed_chain = read_hash(chain_p)

        if expected_chain != observed_chain:
            print(f"FAIL_CHAIN_MISMATCH: {d.name}")
            print(f"  expected={expected_chain}")
            print(f"  observed={observed_chain}")
            ok = False
            break

        chain = expected_chain

    if ok:
        last_k, _ = steps[-1]
        print(f"PASS_VERIFY_CHAIN: steps=0..{last_k}")
        print(f"FINAL_CHAIN_ROOT={chain}")
        return 0

    print("FAIL_VERIFY_CHAIN")
    return 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stream_dir", help="e.g., out/stream")
    args = ap.parse_args()
    raise SystemExit(verify_chain(Path(args.stream_dir)))


if __name__ == "__main__":
    main()

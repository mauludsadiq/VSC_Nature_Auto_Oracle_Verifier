from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

import requests


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--red", required=True, help="Path to red packet JSON")
    ap.add_argument("--run-id", default="ci")
    args = ap.parse_args()

    red = _read_json(Path(args.red))

    r = requests.post(
        f"{args.url}/v1/verify/red-packet",
        json={"red_packet": red, "run_id": args.run_id},
        timeout=30,
    )

    if r.status_code != 200:
        print("FAIL_API_VERIFY_STEP_HTTP", r.status_code, r.text.strip())
        return 2

    out = r.json()

    required = [
        "schema",
        "run_id",
        "step_counter",
        "selected_action",
        "perceived_state",
        "observed_next_state",
        "merkle_root",
        "root_hash_txt",
        "leaf_verdicts",
        "status",
        "out_step_dir",
    ]
    for k in required:
        if k not in out:
            print("FAIL_API_VERIFY_STEP_MISSING_KEY", k)
            return 3

    step_dir = Path(out["out_step_dir"])
    if not step_dir.exists():
        print("FAIL_API_VERIFY_STEP_NO_STEP_DIR", str(step_dir))
        return 4

    if not (step_dir / "bundle.json").exists():
        print("FAIL_API_VERIFY_STEP_NO_BUNDLE_JSON", str(step_dir))
        return 5

    print("PASS_API_VERIFY_STEP", str(step_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

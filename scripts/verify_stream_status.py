#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass
class StreamSummary:
    stream_dir: str
    steps_expected: int
    steps_found: int
    pass_count: int
    detected_value_forgery_count: int
    fail_count: int
    first_fail_step: Optional[int]
    last_step: Optional[int]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stream_dir")
    ap.add_argument("--steps", type=int, default=None, help="optional fixed step count (default: infer from folders)")
    ap.add_argument("--strict-value-children", action="store_true")
    ap.add_argument("--detected-ok", action="store_true")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    stream_dir = Path(args.stream_dir)

    # Infer step dirs
    step_dirs = sorted([p for p in stream_dir.iterdir() if p.is_dir() and p.name.startswith("step_")])
    steps_found = len(step_dirs)
    if steps_found == 0:
        print("FAIL_VERIFY_STREAM_STATUS: no step_ dirs found")
        raise SystemExit(1)

    if args.steps is not None:
        steps_expected = int(args.steps)
    else:
        # assume contiguous 0..N-1
        steps_expected = steps_found

    # Import verify_step_status runtime
    import importlib

    m = importlib.import_module("scripts.verify_step_status")
    verify_step_dir = getattr(m, "verify_step_dir")
    status_from_bundle = getattr(m, "status_from_bundle")

    pass_count = 0
    det_count = 0
    fail_count = 0
    first_fail_step: Optional[int] = None

    for i in range(steps_expected):
        d = stream_dir / f"step_{i:06d}"
        if not d.exists():
            fail_count += 1
            if first_fail_step is None:
                first_fail_step = i
            continue

        res = verify_step_dir(d, strict_value_children=args.strict_value_children)
        if not res.get("ok"):
            fail_count += 1
            if first_fail_step is None:
                first_fail_step = i
            continue

        bundle = res["bundle"]
        st = status_from_bundle(bundle)

        if st == "PASS":
            pass_count += 1
        elif st == "DETECTED_VALUE_FORGERY":
            det_count += 1
        else:
            fail_count += 1
            if first_fail_step is None:
                first_fail_step = i

    last_step = steps_expected - 1

    summary = StreamSummary(
        stream_dir=str(stream_dir),
        steps_expected=steps_expected,
        steps_found=steps_found,
        pass_count=pass_count,
        detected_value_forgery_count=det_count,
        fail_count=fail_count,
        first_fail_step=first_fail_step,
        last_step=last_step,
    )

    out_path = None
    if args.json_out:
        out_path = Path(args.json_out)
    else:
        out_path = stream_dir / "stream_verify_summary.json"

    out_path.write_text(json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {out_path}")

    if fail_count == 0:
        print("PASS_VERIFY_STREAM_STATUS")
        raise SystemExit(0)

    # Fail exists
    if fail_count > 0 and args.detected_ok:
        # still fail if true FAILs exist; detected is already separated
        print("FAIL_VERIFY_STREAM_STATUS")
        raise SystemExit(1)

    print("FAIL_VERIFY_STREAM_STATUS")
    raise SystemExit(1)


if __name__ == "__main__":
    main()

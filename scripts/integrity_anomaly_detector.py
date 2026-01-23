#!/usr/bin/env python3
"""
integrity_anomaly_detector.py

Ghost File Detector for step-wise witness ledgers.

Contract enforced (default):
- Always-changing: bundle.json, chain_root.txt, root_hash.txt
- Value-changing:  w_value.json, w_value_ABSTAIN.json, w_value_MOVE_RIGHT.json
- Percept: changes only on steps {1,2} (genesis+settle), then frozen
- Exec:   changes only on step {1}, then frozen
- Risk:   changes on periodic "checkpoint pulse" steps:
          step % RISK_PERIOD in {0,1} with step>=RISK_PERIOD
          (matches your observed 25/26, 50/51, ...)

It flags:
- Unexpected changed files ("ghost changes")
- Missing expected changes ("silent failure")
- New files appearing / files disappearing
- Files changing during forbidden phases

Writes:
  out/stream/integrity_anomaly_report.json

Exit code:
  0 if clean
  2 if anomalies found
"""

import argparse
import glob
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Set, Tuple


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_bytes(obj) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def list_step_dirs(stream_root: str) -> List[str]:
    step_dirs = sorted(glob.glob(os.path.join(stream_root, "step_*")))
    step_dirs = [d for d in step_dirs if os.path.isdir(d)]
    return step_dirs


def step_id_from_dir(sd: str) -> int:
    base = os.path.basename(sd.rstrip("/"))
    return int(base.split("_")[-1])


def hash_tree(step_dir: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for p in sorted(glob.glob(os.path.join(step_dir, "**"), recursive=True)):
        if os.path.isfile(p):
            rel = os.path.relpath(p, step_dir).replace("\\", "/")
            out[rel] = sha256_file(p)
    return out


@dataclass
class Contract:
    always_change: Set[str]
    value_change: Set[str]
    percept_change_steps: Set[int]
    exec_change_steps: Set[int]
    risk_period: int
    risk_pulse_mods: Set[int]
    risk_min_step: int

    def expected_changed_files(self, step: int) -> Set[str]:
        exp = set()
        exp |= self.always_change
        exp |= self.value_change

        if step in self.percept_change_steps:
            exp.add("w_percept.json")

        if step in self.exec_change_steps:
            exp.add("w_exec.json")

        if step >= self.risk_min_step and (step % self.risk_period) in self.risk_pulse_mods:
            exp.add("w_risk.json")

        return exp

    def forbidden_changed_files(self, step: int) -> Set[str]:
        forbid = set()

        if step not in self.percept_change_steps:
            forbid.add("w_percept.json")

        if step not in self.exec_change_steps:
            forbid.add("w_exec.json")

        if not (step >= self.risk_min_step and (step % self.risk_period) in self.risk_pulse_mods):
            forbid.add("w_risk.json")

        return forbid


DEFAULT_CONTRACT = Contract(
    always_change={"bundle.json", "chain_root.txt", "root_hash.txt"},
    value_change={"w_value.json", "w_value_ABSTAIN.json", "w_value_MOVE_RIGHT.json"},
    percept_change_steps={1, 2},
    exec_change_steps={1},
    risk_period=25,
    risk_pulse_mods={0, 1},
    risk_min_step=25,
)


def contract_dict(c: Contract) -> dict:
    return {
        "always_change": sorted(list(c.always_change)),
        "value_change": sorted(list(c.value_change)),
        "percept_change_steps": sorted(list(c.percept_change_steps)),
        "exec_change_steps": sorted(list(c.exec_change_steps)),
        "risk_period": c.risk_period,
        "risk_pulse_mods": sorted(list(c.risk_pulse_mods)),
        "risk_min_step": c.risk_min_step,
    }


def contract_sha256(contract_obj: dict) -> str:
    return sha256_bytes(canonical_json_bytes(contract_obj))


@dataclass
class StepDiff:
    step: int
    prev_step: int
    changed_files: List[str]
    unchanged_files: List[str]
    added_files: List[str]
    removed_files: List[str]
    expected_change_missing: List[str]
    unexpected_changed: List[str]
    forbidden_changed: List[str]


@dataclass
class Report:
    stream_root: str
    num_steps_scanned: int
    first_step: int
    last_step: int
    anomalies_found: int
    contract: dict
    contract_sha256: str
    detector_path: str
    detector_sha256: str
    diffs_with_anomalies: List[StepDiff]


def compute_diff(prev: Dict[str, str], cur: Dict[str, str]) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
    prev_keys = set(prev.keys())
    cur_keys = set(cur.keys())

    added = cur_keys - prev_keys
    removed = prev_keys - cur_keys

    common = prev_keys & cur_keys
    changed = {k for k in common if prev[k] != cur[k]}
    unchanged = common - changed

    return changed, unchanged, added, removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream-root", default="out/stream", help="Root containing step_* directories.")
    ap.add_argument("--max-steps", type=int, default=0, help="If >0, limit scan to first N step dirs.")
    ap.add_argument("--start-step", type=int, default=-1, help="If >=0, only scan steps >= this value.")
    ap.add_argument("--end-step", type=int, default=-1, help="If >=0, only scan steps <= this value.")
    ap.add_argument("--report-path", default="out/stream/integrity_anomaly_report.json")
    ap.add_argument("--fail-on-any", action="store_true", help="Exit nonzero if ANY anomalies.")
    args = ap.parse_args()

    stream_root = args.stream_root
    step_dirs = list_step_dirs(stream_root)
    if not step_dirs:
        raise SystemExit(f"no step_* dirs found under {stream_root}")

    def keep(sd: str) -> bool:
        s = step_id_from_dir(sd)
        if args.start_step >= 0 and s < args.start_step:
            return False
        if args.end_step >= 0 and s > args.end_step:
            return False
        return True

    step_dirs = [sd for sd in step_dirs if keep(sd)]
    if args.max_steps and args.max_steps > 0:
        step_dirs = step_dirs[: args.max_steps]

    if len(step_dirs) < 2:
        raise SystemExit("need at least 2 steps to diff")

    prev_sd = step_dirs[0]
    prev_step = step_id_from_dir(prev_sd)
    prev_hashes = hash_tree(prev_sd)

    anomalies: List[StepDiff] = []
    anomalies_count = 0

    for sd in step_dirs[1:]:
        step = step_id_from_dir(sd)
        cur_hashes = hash_tree(sd)

        changed, unchanged, added, removed = compute_diff(prev_hashes, cur_hashes)

        expected = DEFAULT_CONTRACT.expected_changed_files(step)
        forbidden = DEFAULT_CONTRACT.forbidden_changed_files(step)

        expected_missing = sorted([f for f in expected if f in prev_hashes and f in cur_hashes and f not in changed])
        unexpected_changed = sorted([f for f in changed if f not in expected])
        forbidden_changed = sorted([f for f in changed if f in forbidden])

        added_files = sorted(list(added))
        removed_files = sorted(list(removed))

        is_anomaly = bool(expected_missing or unexpected_changed or forbidden_changed or added_files or removed_files)

        if is_anomaly:
            anomalies_count += 1
            anomalies.append(
                StepDiff(
                    step=step,
                    prev_step=prev_step,
                    changed_files=sorted(list(changed)),
                    unchanged_files=sorted(list(unchanged)),
                    added_files=added_files,
                    removed_files=removed_files,
                    expected_change_missing=expected_missing,
                    unexpected_changed=unexpected_changed,
                    forbidden_changed=forbidden_changed,
                )
            )

        prev_sd = sd
        prev_step = step
        prev_hashes = cur_hashes

    cdict = contract_dict(DEFAULT_CONTRACT)
    csha = contract_sha256(cdict)

    detector_path = os.path.abspath(__file__)
    dsha = sha256_file(detector_path)

    rep = Report(
        stream_root=stream_root,
        num_steps_scanned=len(step_dirs),
        first_step=step_id_from_dir(step_dirs[0]),
        last_step=step_id_from_dir(step_dirs[-1]),
        anomalies_found=anomalies_count,
        contract=cdict,
        contract_sha256=csha,
        detector_path=detector_path,
        detector_sha256=dsha,
        diffs_with_anomalies=anomalies,
    )

    os.makedirs(os.path.dirname(args.report_path), exist_ok=True)
    with open(args.report_path, "w") as f:
        json.dump(asdict(rep), f, indent=2, sort_keys=True)

    if anomalies_count == 0:
        print("PASS_INTEGRITY_ANOMALY_DETECTOR")
        print(f"WROTE: {args.report_path}")
        print(f"contract_sha256={csha}")
        print(f"detector_sha256={dsha}")
        return

    print("FAIL_INTEGRITY_ANOMALY_DETECTOR")
    print(f"anomalies_found={anomalies_count}")
    print(f"WROTE: {args.report_path}")
    print(f"contract_sha256={csha}")
    print(f"detector_sha256={dsha}")

    for i, a in enumerate(anomalies[:10]):
        print(f"\n--- anomaly[{i}] step={a.step} prev={a.prev_step} ---")
        if a.added_files:
            print("added_files:", a.added_files)
        if a.removed_files:
            print("removed_files:", a.removed_files)
        if a.expected_change_missing:
            print("expected_change_missing:", a.expected_change_missing)
        if a.unexpected_changed:
            print("unexpected_changed:", a.unexpected_changed)
        if a.forbidden_changed:
            print("forbidden_changed:", a.forbidden_changed)

    if args.fail_on_any:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

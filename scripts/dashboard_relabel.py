#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))

def _status_from_bundle(b: Dict[str, Any]) -> str:
    leaf = b.get("leaf_verdicts", {}) or {}
    sel = str(b.get("selected_action", ""))

    pass_all = True
    for v in leaf.values():
        if str(v).upper() != "PASS":
            pass_all = False
            break

    if pass_all:
        return "PASS"

    vt = str(leaf.get("value_table", "")).upper()
    rg = str(leaf.get("risk_gate", "")).upper()

    # The canonical "caught lie -> fallback to ABSTAIN" case
    if vt == "FAIL" and sel == "ABSTAIN" and rg == "PASS":
        return "DETECTED_VALUE_FORGERY"

    return "FAIL"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stream_dir", nargs="?", default="out/stream")
    ap.add_argument("--in-dashboard", default="dashboard.csv")
    ap.add_argument("--out-dashboard", default="dashboard_v2.csv")
    args = ap.parse_args()

    stream_dir = Path(args.stream_dir)
    dash_in = stream_dir / args.in_dashboard
    dash_out = stream_dir / args.out_dashboard

    if not dash_in.exists():
        raise SystemExit(f"Missing: {dash_in}")

    # Build step->status map from bundle.json (source of truth)
    status_map: Dict[int, str] = {}
    for sd in sorted(stream_dir.glob("step_*")):
        bpath = sd / "bundle.json"
        if not bpath.exists():
            continue
        b = _read_json(bpath)
        k = int(b.get("step_counter", int(sd.name.split("_")[-1])))
        status_map[k] = _status_from_bundle(b)

    lines = dash_in.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise SystemExit(f"Empty: {dash_in}")

    header = lines[0].split(",")
    if "status" not in header:
        header2 = header + ["status"]
    else:
        header2 = header

    out_lines = [",".join(header2)]

    # Assume first column is step index (matches your awk usage)
    for row in lines[1:]:
        if not row.strip():
            continue
        parts = row.split(",")
        try:
            step_k = int(parts[0])
        except Exception:
            # Non-data line; preserve
            out_lines.append(row)
            continue

        st = status_map.get(step_k, "UNKNOWN")
        if "status" in header:
            # Replace existing status column
            idx = header.index("status")
            while len(parts) <= idx:
                parts.append("")
            parts[idx] = st
            out_lines.append(",".join(parts))
        else:
            out_lines.append(row + "," + st)

    dash_out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    # Print a tiny summary
    counts: Dict[str, int] = {}
    for v in status_map.values():
        counts[v] = counts.get(v, 0) + 1
    print("WROTE:", dash_out)
    for k in sorted(counts.keys()):
        print(f"{k}={counts[k]}")

if __name__ == "__main__":
    main()

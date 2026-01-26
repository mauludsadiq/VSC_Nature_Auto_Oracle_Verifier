from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _try_read_text(p: Path) -> str:
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8").strip()


def _g(obj: Any, path: str, default: Any = None) -> Any:
    cur = obj
    for key in path.split("."):
        if not isinstance(cur, dict):
            return default
        if key not in cur:
            return default
        cur = cur[key]
    return cur


def _fmt_bool(x: Any) -> str:
    if x is True:
        return "true"
    if x is False:
        return "false"
    return "?"


def _fmt_num(x: Any) -> str:
    if isinstance(x, (int, float)):
        return f"{x}"
    return "?"


def _first_fail(leaf_verdicts: Dict[str, Any]) -> Optional[str]:
    order = ["percept", "model_contract", "value_table", "risk_gate", "exec"]
    for k in order:
        v = leaf_verdicts.get(k)
        if isinstance(v, str) and v.upper() == "FAIL":
            return k
    return None


def _load_step_dir(step_dir: Path) -> Dict[str, Any]:
    files = {
        "bundle": step_dir / "bundle.json",
        "percept": step_dir / "w_percept.json",
        "model": step_dir / "w_model_contract.json",
        "risk": step_dir / "w_risk.json",
        "exec": step_dir / "w_exec.json",
        "value_summary": step_dir / "w_value.json",
        "root_hash": step_dir / "root_hash.txt",
        "chain_root_txt": step_dir / "chain_root.txt",
    }

    out: Dict[str, Any] = {"paths": {k: str(v) for k, v in files.items()}}
    out["bundle"] = _read_json(files["bundle"]) if files["bundle"].exists() else {}

    out["percept"] = _read_json(files["percept"]) if files["percept"].exists() else {}
    out["model"] = _read_json(files["model"]) if files["model"].exists() else {}
    out["risk"] = _read_json(files["risk"]) if files["risk"].exists() else {}
    out["exec"] = _read_json(files["exec"]) if files["exec"].exists() else {}
    out["value_summary"] = _read_json(files["value_summary"]) if files["value_summary"].exists() else {}

    value_action_witnesses: List[Tuple[str, Dict[str, Any]]] = []
    for p in sorted(step_dir.glob("w_value_*.json")):
        if p.name == "w_value.json":
            continue
        try:
            d = _read_json(p)
        except Exception:
            d = {}
        value_action_witnesses.append((p.name, d))

    out["value_actions"] = value_action_witnesses
    out["root_hash"] = _try_read_text(files["root_hash"])
    out["chain_root_txt"] = _try_read_text(files["chain_root_txt"])
    return out


def _print_header(step_dir: Path, pack: Dict[str, Any]) -> None:
    bundle = pack.get("bundle", {})
    leaf = _g(bundle, "leaf_verdicts", {}) or {}

    print("PROOF_EXPLAIN")
    print(f"step_dir={step_dir}")
    print(f"root_hash_txt={pack.get('root_hash','')}")
    if pack.get("chain_root_txt"):
        print(f"chain_root_txt={pack.get('chain_root_txt','')}")

    step_counter = _g(bundle, "step_counter", None)
    prev_state = _g(bundle, "prev_state", None)
    proposed_state = _g(bundle, "proposed_state", None)
    observed_next_state = _g(bundle, "observed_next_state", None)
    proposed_action = _g(bundle, "proposed_action", None)
    selected_action = _g(bundle, "selected_action", None)
    reason = _g(bundle, "reason", None)
    validated = _g(bundle, "validated", None)

    print(f"step_counter={step_counter}")
    print(f"validated={validated}")
    print(f"reason={reason}")
    print(f"prev_state={prev_state}")
    print(f"proposed_state={proposed_state}")
    print(f"observed_next_state={observed_next_state}")
    print(f"proposed_action={proposed_action}")
    print(f"selected_action={selected_action}")

    print("leaf_verdicts=" + json.dumps(leaf, sort_keys=True))
    ff = _first_fail(leaf) if isinstance(leaf, dict) else None
    print(f"first_fail_contract={ff if ff else 'NONE'}")
    print("")


def _print_contract_block(name: str, witness: Dict[str, Any], focus: List[str]) -> None:
    verdict = _g(witness, "verdict", "?")
    checks = _g(witness, "checks", {}) or {}
    metrics = _g(witness, "metrics", {}) or {}
    derived = _g(witness, "derived", {}) or {}

    print(f"[{name}] verdict={verdict}")

    if isinstance(checks, dict) and checks:
        keys = sorted(list(checks.keys()))
        show = keys[:12]
        for k in show:
            print(f"  check.{k}={_fmt_bool(checks.get(k))}")
        if len(keys) > len(show):
            print(f"  check.__more__={len(keys) - len(show)}")

    for fp in focus:
        val = _g(witness, fp, None)
        if val is None:
            val = _g(metrics, fp, None)
        if val is None:
            val = _g(derived, fp, None)
        if val is not None:
            if isinstance(val, (int, float)):
                print(f"  {fp}={_fmt_num(val)}")
            else:
                print(f"  {fp}={val}")

    if isinstance(metrics, dict) and metrics:
        if "l1_to_ref" in metrics:
            print(f"  metrics.l1_to_ref={_fmt_num(metrics.get('l1_to_ref'))}")
        if "forbidden_prob" in metrics:
            print(f"  metrics.forbidden_prob={_fmt_num(metrics.get('forbidden_prob'))}")
        if "support_size" in metrics:
            print(f"  metrics.support_size={_fmt_num(metrics.get('support_size'))}")

    print("")


def _summarize_value_action(name: str, w: Dict[str, Any]) -> str:
    verdict = _g(w, "verdict", "?")
    checks = _g(w, "checks", {}) or {}

    dq = _g(w, "metrics.dq", None)
    dr = _g(w, "metrics.dr", None)
    if dq is None:
        dq = _g(w, "mc.dq", None)
    if dr is None:
        dr = _g(w, "mc.dr", None)

    q_mc = _g(w, "mc.Q_mc", None)
    r_mc = _g(w, "mc.R_mc", None)
    q_hat = _g(w, "inputs.Q_hat", None)
    r_hat = _g(w, "inputs.R_hat", None)

    q_ok = checks.get("q_ok", None)
    r_ok = checks.get("r_ok", None)

    parts: List[str] = []
    parts.append(f"{name} verdict={verdict}")
    if q_hat is not None:
        parts.append(f"Q_hat={_fmt_num(q_hat)}")
    if q_mc is not None:
        parts.append(f"Q_mc={_fmt_num(q_mc)}")
    if dq is not None:
        parts.append(f"dQ={_fmt_num(dq)}")
    if q_ok is not None:
        parts.append(f"q_ok={_fmt_bool(q_ok)}")

    if r_hat is not None:
        parts.append(f"R_hat={_fmt_num(r_hat)}")
    if r_mc is not None:
        parts.append(f"R_mc={_fmt_num(r_mc)}")
    if dr is not None:
        parts.append(f"dR={_fmt_num(dr)}")
    if r_ok is not None:
        parts.append(f"r_ok={_fmt_bool(r_ok)}")

    return "  " + " ".join(parts)


@dataclass
class ExplainSummary:
    step_dir: str
    step_counter: Optional[int]
    validated: Any
    reason: Any
    prev_state: Any
    proposed_state: Any
    observed_next_state: Any
    proposed_action: Any
    selected_action: Any
    leaf_verdicts: Dict[str, Any]
    first_fail_contract: Optional[str]
    root_hash_txt: str
    chain_root_txt: str


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step_dir", type=str)
    ap.add_argument("--json-out", type=str, default="")
    args = ap.parse_args()

    step_dir = Path(args.step_dir).expanduser().resolve()
    pack = _load_step_dir(step_dir)
    bundle = pack.get("bundle", {})
    leaf = _g(bundle, "leaf_verdicts", {}) or {}
    ff = _first_fail(leaf) if isinstance(leaf, dict) else None

    _print_header(step_dir, pack)

    percept_focus = []
    model_focus = []
    risk_focus = ["derived.selected_action","derived.regret_int"]
    exec_focus = []

    _print_contract_block("percept", pack.get("percept", {}), percept_focus)
    _print_contract_block("model_contract", pack.get("model", {}), model_focus)

    print("[value_table]")
    value_actions = pack.get("value_actions", [])
    if value_actions:
        for fname, w in value_actions:
            print(_summarize_value_action(fname, w))
    else:
        print("  (no per-action value witnesses found)")
    print("")

    _print_contract_block("risk_gate", pack.get("risk", {}), risk_focus)
    _print_contract_block("exec", pack.get("exec", {}), exec_focus)

    summary = ExplainSummary(
        step_dir=str(step_dir),
        step_counter=_g(bundle, "step_counter", None),
        validated=_g(bundle, "validated", None),
        reason=_g(bundle, "reason", None),
        prev_state=_g(bundle, "prev_state", None),
        proposed_state=_g(bundle, "proposed_state", None),
        observed_next_state=_g(bundle, "observed_next_state", None),
        proposed_action=_g(bundle, "proposed_action", None),
        selected_action=_g(bundle, "selected_action", None),
        leaf_verdicts=leaf if isinstance(leaf, dict) else {},
        first_fail_contract=ff,
        root_hash_txt=pack.get("root_hash", ""),
        chain_root_txt=pack.get("chain_root_txt", ""),
    )

    if args.json_out:
        outp = Path(args.json_out).expanduser().resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"WROTE_JSON_SUMMARY: {outp}")


if __name__ == "__main__":
    main()

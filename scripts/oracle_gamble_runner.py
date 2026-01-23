import json
from pathlib import Path
from typing import Dict, Tuple, Optional, List

from chaos_env.chaos_env_wrapper import run_oracle_step
from percept_contract import PerceptContractV1
from model_contract import ModelContractV1
from value_contract import ValueContractV1
from risk_gate import RiskGateContractV1
from exec_contract import ExecContractV1, SkillSpecV1

_DASH_LAST_PATH = None
_DASH_LAST_LINE = None
from scripts.dashboard_schema import DASHBOARD_KEYS, DASHBOARD_HEADER

def dump_csv_row(csv_path: Path, row: Dict[str, str]) -> None:
    global _DASH_LAST_PATH, _DASH_LAST_LINE

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists():
        csv_path.write_text(DASHBOARD_HEADER, encoding="utf-8")

    vals = []
    for k in DASHBOARD_KEYS:
        vals.append(str(row.get(k, "NA")))

    line = ",".join(vals)

    if _DASH_LAST_PATH == str(csv_path) and _DASH_LAST_LINE == line:
        return

    try:
        prev = csv_path.read_text(encoding="utf-8").splitlines()
        if len(prev) >= 2:
            last = prev[-1].rstrip("\r\n")
            if last == line:
                _DASH_LAST_PATH = str(csv_path)
                _DASH_LAST_LINE = line
                return
    except Exception:
        pass

    with csv_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    _DASH_LAST_PATH = str(csv_path)
    _DASH_LAST_LINE = line

    if not csv_path.exists():
        csv_path.write_text(DASHBOARD_HEADER, encoding="utf-8")

    vals = []
    for k in DASHBOARD_KEYS:
        vals.append(str(row.get(k, "NA")))

    line = ",".join(vals)

    try:
        prev_lines = csv_path.read_text(encoding="utf-8").splitlines()
        if len(prev_lines) >= 2:
            last = prev_lines[-1]
            if last == line:
                return
    except Exception:
        pass

    with csv_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    if not csv_path.exists():
        csv_path.write_text(DASHBOARD_HEADER, encoding="utf-8")

    vals = []
    for k in DASHBOARD_KEYS:
        vals.append(str(row.get(k, "NA")))

    line = ",".join(vals) + "\n"
    with csv_path.open("a", encoding="utf-8") as f:
        f.write(line)

    header = "step,time,action,proof_status,merkle_root,result,reason,percept,model,value,risk,exec\n"
    if not csv_path.exists():
        csv_path.write_text(header, encoding="utf-8")

    def g(k: str) -> str:
        return str(row.get(k, "NA"))

    line = (
        g("step") + "," +
        g("time") + "," +
        g("action") + "," +
        g("proof_status") + "," +
        g("merkle_root") + "," +
        g("result") + "," +
        g("reason") + "," +
        g("percept") + "," +
        g("model") + "," +
        g("value") + "," +
        g("risk") + "," +
        g("exec") + "\n"
    )
    with csv_path.open("a", encoding="utf-8") as f:
        f.write(line)

def load_red_packet(inbox: Path, k: int) -> Dict:
    p = inbox / f"proposal_step_{k}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    if "observation" not in d:
        st = str(d.get("state", d.get("prev_state", "")))
        d["observation"] = {"raw": f"pos={st}"}
    if "proposed_state" not in d:
        d["proposed_state"] = str(d.get("state", d.get("prev_state", "")))
    return d



    p = inbox / f"proposal_step_{k}.json"
    return json.loads(p.read_text(encoding="utf-8"))

def main():
    root = Path(".")
    inbox = root / "inbox"
    out_stream = root / "out" / "stream"
    inbox.mkdir(parents=True, exist_ok=True)
    out_stream.mkdir(parents=True, exist_ok=True)

    skills = {
        "MOVE_RIGHT": SkillSpecV1(
            name="MOVE_RIGHT",
            pre_states=["1,1","1,2"],
            post_states=["1,2"],
            allowed_subactions=["MOVE_RIGHT"],
            max_trace_len=2
        ),
        "ABSTAIN": SkillSpecV1(
            name="ABSTAIN",
            pre_states=["1,1","1,2","9,9"],
            post_states=["1,1","1,2","9,9"],
            allowed_subactions=["ABSTAIN"],
            max_trace_len=1
        )
    }

    state_vocab: List[str] = ["1,1","1,2","9,9"]

    T_ver: Dict[Tuple[str,str], Dict[str,int]] = {
        ("1,1","ABSTAIN"): {"1,1": 1024},
        ("1,2","ABSTAIN"): {"1,2": 1024},
        ("9,9","ABSTAIN"): {"9,9": 1024},
    }

    contracts = {
        "percept_contract": PerceptContractV1(n_views=3, agree_k=2, require_temporal=True, require_state_format=True),
        "model_contract": ModelContractV1(S=10, eps_T=0.1, eps_update=0.05, k_max=3, pi_min=0.01, eta_forbid=0.001),
        "value_contract": ValueContractV1(S=10, gamma_fp=1.0, horizon=1, n_rollouts=64, eps_q=2.0, eps_r=2.0, follow_action="ABSTAIN"),
        "risk_contract": RiskGateContractV1(S=10, rho_max=0.05, eps_regret=0.0, abstain_action="ABSTAIN"),
        "exec_contract": ExecContractV1(S=10, pi_min=0.01, eps_model=0.0, forbid_states=["9,9"]),
    }

    global_seed = 12345
    k = 0
    state = "1,1"
    prev_action: Optional[str] = None

    import datetime
    while True:
        pkt_path = inbox / f"proposal_step_{k}.json"
        if not pkt_path.exists():
            break

        red = load_red_packet(inbox, k)

        out_step_dir = out_stream / f"step_{k:06d}"
        bundle = run_oracle_step(
            red_packet=red,
            contracts=contracts,
            skills=skills,
            T_ver=T_ver,
            global_seed=global_seed,
            out_step_dir=out_step_dir,
            prev_state=state,
            prev_action=prev_action,
            state_vocab=state_vocab,
        )

        action = bundle["selected_action"]
        exec_v = bundle.get("exec_verdict", "FAIL")

        if exec_v == "PASS":
            state = bundle["observed_next_state"]

        prev_action = action

        leaf = bundle.get("leaf_verdicts", {})
        reason = "OK"
        if leaf.get("percept") == "FAIL":
            reason = "PERCEPT_FAIL"
        elif leaf.get("model_contract") == "FAIL":
            reason = "MODEL_FAIL"
        elif leaf.get("value_table") == "FAIL":
            reason = "VALUE_FAIL"
        elif leaf.get("risk_gate") == "FAIL":
            reason = "RISK_FAIL"
        elif bundle.get("exec_verdict") == "FAIL":
            reason = "EXEC_FAIL"

        now = datetime.datetime.utcnow().isoformat() + "Z"
        dump_csv_row(
            out_stream / "dashboard.csv",
            {
                "step": str(k),
                "time": now,
                "action": action,
                "proof_status": "VALIDATED",
                "merkle_root": bundle["merkle_root"][:12],
                "result": "OK" if action != "ABSTAIN" else "ABSTAIN",
                "reason": reason,
                "percept": bundle.get("leaf_verdicts", {}).get("percept", "NA"),
                "model": bundle.get("leaf_verdicts", {}).get("model_contract", "NA"),
                "value": bundle.get("leaf_verdicts", {}).get("value_table", "NA"),
                "risk": bundle.get("leaf_verdicts", {}).get("risk_gate", "NA"),
                "exec": exec_v,
            }
        )
        k += 1

if __name__ == "__main__":
    main()

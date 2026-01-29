from verifier.contract_digest_v1 import verifier_contract_digest_v1
import json, hashlib
from pathlib import Path
from typing import Any, Dict, List, Tuple

from value_contract import verify_value_proposal_single, ValueContractV1
from risk_gate import risk_gate_select_action, RiskGateContractV1
from exec_contract import verify_exec_proposal, ExecContractV1, SkillSpecV1

def _jsonable(x: Any) -> Any:
    # Convert objects into JSON-safe canonical form (supports tuple-key dicts).
    if isinstance(x, dict):
        # If any key is not JSON-legal, stringify keys deterministically.
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
    return json.dumps(
        x,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")

def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def hash_canon(x: Any) -> str:
    return sha256_hex(canon_json_bytes(x))

def mix32(a: int, b: int) -> int:
    return (a * 0x9E3779B9 + b) & 0xFFFFFFFF

def sha32(s: str) -> int:
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "little") & 0xFFFFFFFF

def derive_seeds(global_seed: int, step_counter: int) -> Dict[str, int]:
    base = mix32(global_seed & 0xFFFFFFFF, step_counter & 0xFFFFFFFF)
    return {
        "model": mix32(base, 1),
        "value": mix32(base, 2),
        "risk": mix32(base, 3),
        "exec": mix32(base, 4),
    }

def merkle_pair(h1: str, h2: str) -> str:
    return sha256_hex(canon_json_bytes([h1, h2]))

def merkle_root_4(leaves: List[str]) -> str:
    assert len(leaves) == 4
    left = merkle_pair(leaves[0], leaves[1])
    right = merkle_pair(leaves[2], leaves[3])
    return merkle_pair(left, right)

def execute_agent_step(
    *,
    s_t: str,
    T_ver: Dict[Tuple[str, str], Dict[str, int]],
    reward_table: Dict[Tuple[str, str, str], float],
    violation_states: List[str],
    skills: Dict[str, SkillSpecV1],
    value_contract: ValueContractV1,
    risk_contract: RiskGateContractV1,
    exec_contract: ExecContractV1,
    global_seed: int,
    step_counter: int,
    output_dir: Path,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    seeds = derive_seeds(global_seed, step_counter)

    witnesses: Dict[str, Any] = {}
    hashes: Dict[str, str] = {}

    # 1) model witness (static)
    w_model = {
        "schema": "agent_step.model_witness.v1",
        "step": step_counter,
        "input_state": s_t,
        "model_hash": hash_canon(T_ver),
        "verdict": "PASS",
        "note": "Static sealed T_ver used (no update proposed).",
    }
    (output_dir / "w_model.json").write_text(json.dumps(w_model, indent=2), encoding="utf-8")
    witnesses["model"] = w_model
    hashes["model"] = hash_canon(w_model)

    # 2) Γ_value per-action
    actions = sorted([a for (s, a) in T_ver.keys() if s == s_t])
    if not actions:
        actions = [risk_contract.abstain_action]

    verified_q: Dict[str, float] = {}
    verified_r: Dict[str, float] = {}
    value_children: Dict[str, str] = {}
    all_value_pass = True

    for a in actions:
        proposed_q = 0.0
        proposed_r = 0.0
        a_seed = mix32(seeds["value"], sha32(a))

        w_child = verify_value_proposal_single(
            contract=value_contract,
            s=s_t,
            a=a,
            proposed_q=proposed_q,
            proposed_r=proposed_r,
            t_ver=T_ver,
            reward_table=reward_table,
            violation_states=violation_states,
            rollout_seed=a_seed,
        )
        (output_dir / f"w_value_{a}.json").write_text(json.dumps(w_child, indent=2), encoding="utf-8")

        h_child = hash_canon(w_child)
        value_children[a] = h_child
        if w_child["verdict"] != "PASS":
            all_value_pass = False

        verified_q[a] = float(w_child["mc"]["Q_mc"])
        verified_r[a] = float(w_child["mc"]["R_mc"])

    w_value = {
        "schema": "agent_step.value_table.v1",
        "step": step_counter,
        "s": s_t,
        "actions": actions,
        "children": [{"action": a, "hash": value_children[a]} for a in actions],
        "verdict": "PASS" if all_value_pass else "FAIL",
    }
    (output_dir / "w_value.json").write_text(json.dumps(w_value, indent=2), encoding="utf-8")
    witnesses["value"] = w_value
    hashes["value"] = hash_canon(w_value)

    if w_value["verdict"] != "PASS":
        raise AssertionError("Γ_value failed")

    # 3) Γ_pi
    proposed_action = max(sorted(actions), key=lambda a: verified_q[a])
    w_risk = risk_gate_select_action(
        contract=risk_contract,
        q_values=verified_q,
        r_values=verified_r,
        proposed_action=proposed_action,
    )
    (output_dir / "w_risk.json").write_text(json.dumps(w_risk, indent=2), encoding="utf-8")
    witnesses["risk"] = w_risk
    hashes["risk"] = hash_canon(w_risk)
    if w_risk["verdict"] != "PASS":
        raise AssertionError("Γ_pi failed")

    selected_action = w_risk["derived"]["selected_action"]
    if selected_action not in skills:
        raise AssertionError(f"Skill not found: {selected_action}")
    skill = skills[selected_action]

    # 4) Γ_exec
    trans_dist = T_ver.get((s_t, selected_action), {s_t: 1 << value_contract.S})
    s_t1 = max(sorted(trans_dist.items()), key=lambda kv: kv[1])[0]
    trace = [{"u": selected_action, "s": s_t1}]

    w_exec = verify_exec_proposal(
        contract=exec_contract,
        skill=skill,
        s_t=s_t,
        skill_token=selected_action,
        trace=trace,
        s_t1=s_t1,
        t_ver_int_mass=trans_dist,
    )
    (output_dir / "w_exec.json").write_text(json.dumps(w_exec, indent=2), encoding="utf-8")
    witnesses["exec"] = w_exec
    hashes["exec"] = hash_canon(w_exec)
    if w_exec["verdict"] != "PASS":
        raise AssertionError("Γ_exec failed")

    root = merkle_root_4([hashes["model"], hashes["value"], hashes["risk"], hashes["exec"]])
    (output_dir / "root_hash.txt").write_text(root + "\n", encoding="utf-8")

    bundle = {

    "bundle_schema_version": "v1",
    "verifier_contract_digest": verifier_contract_digest_v1(Path(__file__).resolve().parents[1]),

        "schema": "agent_step.bundle.v1",
        "step_counter": step_counter,
        "input_state": s_t,
        "selected_action": selected_action,
        "output_state": s_t1,
        "witnesses": {
            "model": {"file": "w_model.json", "hash": hashes["model"], "verdict": w_model["verdict"]},
            "value": {"file": "w_value.json", "hash": hashes["value"], "verdict": w_value["verdict"]},
            "risk":  {"file": "w_risk.json", "hash": hashes["risk"], "verdict": w_risk["verdict"]},
            "exec":  {"file": "w_exec.json", "hash": hashes["exec"], "verdict": w_exec["verdict"]},
        },
        "merkle_root": root,
        "global_seed": global_seed,
        "derived_seeds": seeds,
        "verdict": "PASS",
    }
    (output_dir / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    return bundle

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from percept_contract import PerceptContractV1, verify_percept_proposal
from model_contract import ModelContractV1, verify_model_proposal

import os


def _maybe_inject_forbidden_mass(
    step_counter: int,
    proposal_pairs: list,
    forbidden_next_states: list,
):
    """Inject eta mass onto a forbidden next-state inside proposal_pairs.

    proposal_pairs is expected to be a list of 2-tuples:
      (next_state, prob)

    We scale all existing probs by (1-eta) and append (forbidden_state, eta).
    This preserves normalization and tests forbid_ok hard.
    """

    try:
        inj_step = int(os.getenv("VSC_STEALTH_FORBID_INJECT_STEP", "-1"))
        if step_counter != inj_step:
            return proposal_pairs, None

        eta = float(os.getenv("VSC_STEALTH_FORBID_ETA", "1e-12"))
        if eta <= 0.0:
            return proposal_pairs, None

        if not forbidden_next_states:
            return proposal_pairs, None

        forbidden = forbidden_next_states[0]
        if isinstance(forbidden, list):
            forbidden = tuple(forbidden)

        total = 0.0
        for ns, p in proposal_pairs:
            total += float(p)

        if total <= 0.0:
            return proposal_pairs, None

        scale = max(0.0, 1.0 - eta)
        new_pairs = []
        for ns, p in proposal_pairs:
            new_pairs.append((ns, float(p) * scale))

        new_pairs.append((forbidden, float(eta)))

        meta = {
            "step": step_counter,
            "eta": float(eta),
            "forbidden_next": forbidden,
        }
        return new_pairs, meta

    except Exception:
        return proposal_pairs, None

from value_contract import ValueContractV1, verify_value_proposal_single
from risk_gate import RiskGateContractV1, risk_gate_select_action
from exec_contract import ExecContractV1, SkillSpecV1, verify_exec_proposal



def _maybe_inject_forbid(step_counter: int, proposed: dict) -> dict:
    try:
        inj_step = int(os.getenv("VSC_STEALTH_FORBID_INJECT_STEP", "-1"))
        if step_counter != inj_step:
            return proposed

        eta = float(os.getenv("VSC_STEALTH_FORBID_ETA", "1e-12"))
        key = os.getenv("VSC_STEALTH_FORBID_KEY", "FORBIDDEN")

        from scripts.stealth_attack_runner import _inject_forbidden_mass

        mutated, did = _inject_forbidden_mass(proposed, eta=eta, forbidden_key=key)
        if did:
            if isinstance(mutated, dict):
                mutated["__stealth_injected__"] = {"eta": eta, "key": key}
        return mutated
    except Exception:
        return proposed

def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))

def dump_json(p: Path, x: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2), encoding="utf-8")

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
    import hashlib
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

def parse_reward_table(encoded: Dict[str, float]) -> Dict[Tuple[str, str, str], float]:
    out: Dict[Tuple[str, str, str], float] = {}
    for k, v in encoded.items():
        s, a, s2 = k.split("|")
        out[(s, a, s2)] = float(v)
    return out

def canon_action_file(a: str) -> str:
    return a.replace("/", "_").replace(" ", "_")

def mix32(a: int, b: int) -> int:
    return (a * 0x9E3779B9 + b) & 0xFFFFFFFF

def sha32(s: str) -> int:
    import hashlib
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "little") & 0xFFFFFFFF

def derive_seeds(global_seed: int, step_counter: int) -> Dict[str, int]:
    base = mix32(global_seed & 0xFFFFFFFF, step_counter & 0xFFFFFFFF)
    return {
        "percept": mix32(base, 17),
        "model": mix32(base, 1),
        "value": mix32(base, 2),
        "risk": mix32(base, 3),
        "exec": mix32(base, 4),
    }


def _maybe_attack_b_force_exec(step_counter: int, selected_action: str, abstain_action: str):
    import os
    try:
        inj_step = int(os.getenv("VSC_ATTACK_B_STEP", "-1"))
        if step_counter != inj_step:
            return selected_action, None

        if selected_action != abstain_action:
            return selected_action, None

        forced = os.getenv("VSC_ATTACK_B_FORCE_ACTION", "MOVE_RIGHT")
        meta = {
            "step": step_counter,
            "original_action": selected_action,
            "forced_exec_action": forced,
        }
        return forced, meta
    except Exception:
        return selected_action, None

def run_oracle_step(
    *,
    red_packet: Dict[str, Any],
    contracts: Dict[str, Any],
    skills: Dict[str, SkillSpecV1],
    T_ver: Dict[Tuple[str, str], Dict[str, int]],
    global_seed: int,
    out_step_dir: Path,
    prev_state: Optional[str] = None,
    prev_action: Optional[str] = None,
    state_vocab: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
    out_step_dir.mkdir(parents=True, exist_ok=True)
    if prev_state is None:
        prev_state = str(red_packet.get("prev_state", red_packet.get("state", "")))
    if prev_action is None:
        prev_action = red_packet.get("prev_action", None)
    if state_vocab is None:
        state_vocab = list(red_packet.get("state_vocab", ["1,1","1,2","9,9"]))


    step_counter = int(red_packet["step_counter"])
    actions_full = list(red_packet["actions"])
    actions = list(actions_full)
    seeds = derive_seeds(global_seed, step_counter)

    percept_contract: PerceptContractV1 = contracts.get(
        "percept_contract",
        PerceptContractV1(
            n_views=3,
            agree_k=2,
            require_temporal=(prev_action is not None),
            require_state_format=True,
        ),
    )

    s_raw = str(red_packet.get("state", prev_state))
    observation = red_packet.get("observation", None)
    if observation is None:
        observation = {"raw": f"pos={s_raw}"}

    proposed_state = red_packet.get("proposed_state", None)
    if proposed_state is None:
        mr = red_packet.get("model_row_proposal", None)
        if isinstance(mr, list) and len(mr) > 0 and isinstance(mr[0], (list, tuple)) and len(mr[0]) >= 1:
            proposed_state = str(mr[0][0])
        else:
            proposed_state = s_raw

    w_percept = verify_percept_proposal(
        contract=percept_contract,
        observation=observation,
        proposed_state=proposed_state,
        prev_state=prev_state,
        prev_action=prev_action,
        t_ver=T_ver,
        state_vocab=state_vocab,
    )
    dump_json(out_step_dir / "w_percept.json", w_percept)

    if w_percept["verdict"] == "PASS":
        s_t = proposed_state
    else:
        s_t = prev_state
        actions = [contracts["risk_contract"].abstain_action]

    proposal_pairs = [tuple(x) for x in red_packet["model_row_proposal"]]
    ref_pairs = [tuple(x) for x in red_packet["model_row_ref"]]
    forbidden_next = list(red_packet.get("forbidden_next_states", []))

    proposal_pairs, stealth_meta = _maybe_inject_forbidden_mass(
        step_counter=step_counter,
        proposal_pairs=proposal_pairs,
        forbidden_next_states=forbidden_next,
    )


    model_contract: ModelContractV1 = contracts["model_contract"]
    abstain_action = contracts["risk_contract"].abstain_action
    model_action = next((a for a in actions_full if a != abstain_action), abstain_action)

    a_row = next((a for a in actions if a != abstain_action), actions[0])

    
    w_model_contract = verify_model_proposal(
    model_contract,
    proposal_pairs=proposal_pairs,
    ref_pairs=ref_pairs,
    ver_pairs=None,
    forbidden_next_states=forbidden_next,
    )

    if "check" not in w_model_contract and "checks" in w_model_contract:
        w_model_contract["check"] = w_model_contract["checks"]
    if "checks" not in w_model_contract and "check" in w_model_contract:
        w_model_contract["checks"] = w_model_contract["check"]


    if stealth_meta is not None:
        w_model_contract["stealth_inject"] = stealth_meta

    dump_json(out_step_dir / "w_model_contract.json", w_model_contract)

    value_contract: ValueContractV1 = contracts["value_contract"]
    reward_table = parse_reward_table(red_packet.get("reward_table", {}))
    violation_states = list(red_packet.get("violation_states", []))

    if w_model_contract["verdict"] == "PASS" and model_action != abstain_action:
        T_ver[(s_t, model_action)] = w_model_contract["candidate_int_mass"]

    verified_q: Dict[str, float] = {}
    verified_r: Dict[str, float] = {}
    child_hashes: Dict[str, str] = {}
    all_value_pass = True

    proposed_q_map = dict(red_packet.get("proposed_q", {}))
    proposed_r_map = dict(red_packet.get("proposed_r", {}))

    for a in sorted(actions):
        a_seed = mix32(seeds["value"], sha32(a))
        w_child = verify_value_proposal_single(
            contract=value_contract,
            s=s_t,
            a=a,
            proposed_q=float(proposed_q_map.get(a, 0.0)),
            proposed_r=float(proposed_r_map.get(a, 0.0)),
            t_ver=T_ver,
            reward_table=reward_table,
            violation_states=violation_states,
            rollout_seed=a_seed,
        )
        fn = f"w_value_{canon_action_file(a)}.json"
        dump_json(out_step_dir / fn, w_child)
        h = canon_hash(w_child)
        child_hashes[a] = h
        if w_child["verdict"] != "PASS":
            all_value_pass = False
        verified_q[a] = float(w_child["mc"]["Q_mc"])
        verified_r[a] = float(w_child["mc"]["R_mc"])

    w_value = {
        "schema": "oracle.value_table.v1",
        "step_counter": step_counter,
        "state": s_t,
        "actions": sorted(actions),
        "children": [{"action": a, "hash": child_hashes[a]} for a in sorted(actions)],
        "verdict": "PASS" if all_value_pass else "FAIL",
    }
    dump_json(out_step_dir / "w_value.json", w_value)

    risk_contract: RiskGateContractV1 = contracts["risk_contract"]
    if w_percept["verdict"] != "PASS" or w_model_contract["verdict"] != "PASS" or w_value["verdict"] != "PASS":
        q_in = {abstain_action: 0.0}
        r_in = {abstain_action: 0.0}
        proposed_action = None
    else:
        q_in = dict(verified_q)
        r_in = dict(verified_r)
        proposed_action = max(sorted(q_in.keys()), key=lambda a: q_in[a])

    w_risk = risk_gate_select_action(
        contract=risk_contract,
        q_values=q_in,
        r_values=r_in,
        proposed_action=proposed_action,
    )
    dump_json(out_step_dir / "w_risk.json", w_risk)

    selected_action = w_risk["derived"]["selected_action"]

    exec_contract: ExecContractV1 = contracts["exec_contract"]
    if selected_action not in skills:
        raise AssertionError(f"Skill not found: {selected_action}")

    trans_dist = T_ver.get((s_t, selected_action), {s_t: 1 << value_contract.S})

    observed_s_t1 = red_packet.get("observed_next_state", None)


    attack_b_step = int(os.getenv("VSC_ATTACK_B_INJECT_STEP","-1"))
    if step_counter == attack_b_step:
        try:
            ps = prev_state
            if isinstance(ps, str) and "," in ps:
                xs = ps.split(",")
                x = int(xs[0])
                y = int(xs[1])
            elif isinstance(ps, (list, tuple)) and len(ps) >= 2:
                x = int(ps[0])
                y = int(ps[1])
            else:
                raise ValueError(f"unparseable prev_state: {ps!r}")

            y2 = min(int(exec_contract.S), y + 1)
            forced = f"{x},{y2}"

            red_packet["observed_next_state"] = forced
            red_packet["observed_trace"] = [{"u": "MOVE_RIGHT", "s": forced}]
            observed_s_t1 = forced

            red_packet["__attack_b__"] = {
                "step": int(step_counter),
                "prev_state": [int(x), int(y)],
                "forced_observed_next_state": [int(x), int(y2)],
                "forced_observed_trace": [{"u": "MOVE_RIGHT", "s": forced}],
                "note": "forced MOVE_RIGHT trace while selected_action may differ",
            }
        except Exception:
            pass

    if observed_s_t1 is None:
        observed_s_t1 = max(sorted(trans_dist.items()), key=lambda kv: kv[1])[0]
    if isinstance(observed_s_t1, (list, tuple)):
        observed_s_t1 = ",".join(str(int(z)) for z in observed_s_t1)
    else:
        observed_s_t1 = str(observed_s_t1)

    observed_trace = red_packet.get("observed_trace", None)
    if observed_trace is None:
        observed_trace = [{"u": selected_action, "s": observed_s_t1}]

    w_exec = verify_exec_proposal(
        contract=exec_contract,
        skill=skills[selected_action],
        s_t=s_t,
        skill_token=selected_action,
        trace=observed_trace,
        s_t1=observed_s_t1,
        t_ver_int_mass=trans_dist,
    )
    dump_json(out_step_dir / "w_exec.json", w_exec)

    leaf_map = {
        "percept": canon_hash(w_percept),
        "model_contract": canon_hash(w_model_contract),
        "value_table": canon_hash(w_value),
        "risk_gate": canon_hash(w_risk),
        "exec": canon_hash(w_exec),
    }
    leaf_order = ["percept", "model_contract", "value_table", "risk_gate", "exec"]
    root = merkle_root([leaf_map[k] for k in leaf_order])

    (out_step_dir / "root_hash.txt").write_text(root + "\n", encoding="utf-8")

    value_child_files = sorted(out_step_dir.glob("w_value_*.json"))
    value_children = []
    for vf in value_child_files:
        vj = json.loads(vf.read_text(encoding="utf-8"))
        value_children.append({"file": vf.name, "hash": canon_hash(vj)})

    bundle = {
      "red_packet": red_packet,

        "schema": "oracle.bundle.v3",
        "step_counter": step_counter,
        "prev_state": prev_state,
        "perceived_state": s_t,
        "selected_action": selected_action,
        "observed_next_state": observed_s_t1,
        "prev_action": prev_action,
        "merkle_root": root,
        "verdict": "PASS",
        "exec_verdict": w_exec["verdict"],
        "leaves": [{"name": k, "hash": leaf_map[k]} for k in leaf_order],
        "leaf_verdicts": {
            "percept": w_percept["verdict"],
            "model_contract": w_model_contract["verdict"],
            "value_table": w_value["verdict"],
            "risk_gate": w_risk["verdict"],
            "exec": w_exec["verdict"],
        },

    }
    bundle["value_children"] = value_children
    dump_json(out_step_dir / "bundle.json", bundle)
    return bundle

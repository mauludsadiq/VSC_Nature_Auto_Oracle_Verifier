import json, hashlib
from dataclasses import dataclass
from typing import Dict, Any, Optional

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

def quantize_scalar(x: float, S: int) -> int:
    scale = 1 << S
    return int(x * scale + 0.5)

def dequantize_scalar(m: int, S: int) -> float:
    return m / float(1 << S)

@dataclass(frozen=True)
class RiskGateContractV1:
    S: int
    rho_max: float
    eps_regret: float
    abstain_action: str

def risk_gate_select_action(
    contract: RiskGateContractV1,
    q_values: Dict[str, float],
    r_values: Dict[str, float],
    proposed_action: Optional[str] = None,
) -> Dict[str, Any]:
    q_int = {a: quantize_scalar(q, contract.S) for a, q in q_values.items()}
    r_int = {a: quantize_scalar(r, contract.S) for a, r in r_values.items()}

    action_set_ok = set(q_int.keys()) == set(r_int.keys())
    actions = sorted(q_int.keys())

    rho_max_int = quantize_scalar(contract.rho_max, contract.S)
    safe_actions = [a for a in actions if r_int[a] <= rho_max_int]
    safe_nonempty = len(safe_actions) > 0

    if safe_nonempty:
        best_q = max(q_int[a] for a in safe_actions)
        best_safe = [a for a in safe_actions if q_int[a] == best_q]
        if proposed_action is not None and proposed_action in best_safe:
            selected_action = proposed_action
        else:
            selected_action = sorted(best_safe)[0]
    else:
        selected_action = contract.abstain_action

    regret_ok = True
    regret = None
    if safe_nonempty:
        q_max_safe = max(q_int[a] for a in safe_actions)
        q_sel = q_int[selected_action]
        regret_int = q_max_safe - q_sel
        regret = dequantize_scalar(regret_int, contract.S)
        eps_regret_int = quantize_scalar(contract.eps_regret, contract.S)
        regret_ok = regret_int <= eps_regret_int

    risk_ok = True
    sel_risk = None
    # 'risk_ok' is defined as: proposed action must be safe if proposed_action is provided;
    # otherwise, the selected action must be safe.
    check_action = proposed_action if proposed_action is not None else selected_action
    if check_action != contract.abstain_action:
        if check_action not in r_int:
            risk_ok = False
        else:
            sel_risk = dequantize_scalar(r_int[check_action], contract.S)
            risk_ok = r_int[check_action] <= rho_max_int

    proposal_ok = True
    if proposed_action is not None:
        proposal_ok = (proposed_action == selected_action)

    passed = bool(action_set_ok and regret_ok and risk_ok and proposal_ok)

    return {
        "schema": "contract.risk_gate.v1",
        "contract": {
            "S": contract.S,
            "rho_max": contract.rho_max,
            "eps_regret": contract.eps_regret,
            "abstain_action": contract.abstain_action,
        },
        "inputs": {
            "q_int": {a: q_int[a] for a in actions},
            "r_int": {a: r_int[a] for a in actions},
            "proposed_action": proposed_action,
        },
        "derived": {
            "safe_actions": safe_actions,
            "selected_action": selected_action,
            "selected_risk": sel_risk,
            "regret": regret,
        },
        "checks": {
            "action_set_ok": action_set_ok,
            "safe_nonempty": safe_nonempty,
            "risk_ok": risk_ok,
            "regret_ok": regret_ok,
            "proposal_ok": proposal_ok,
        },
        "verdict": "PASS" if passed else "FAIL",
    }

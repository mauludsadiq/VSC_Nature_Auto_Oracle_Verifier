import json, hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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

@dataclass(frozen=True)
class SkillSpecV1:
    name: str
    pre_states: List[str]
    post_states: List[str]
    allowed_subactions: List[str]
    max_trace_len: int

@dataclass(frozen=True)
class ExecContractV1:
    S: int
    pi_min: float
    eps_model: float
    forbid_states: List[str]

def verify_exec_proposal(
    contract: ExecContractV1,
    skill: SkillSpecV1,
    s_t: str,
    skill_token: str,
    trace: List[Dict[str, Any]],
    s_t1: str,
    t_ver_int_mass: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    pre_ok = (s_t in skill.pre_states) and (skill_token == skill.name)
    trace_len_ok = (1 <= len(trace) <= skill.max_trace_len)

    allowed = set(skill.allowed_subactions)
    forbid = set(contract.forbid_states)

    subactions_ok = True
    inter_ok = True
    forbid_ok = True

    for step in trace:
        u = step.get("u", None)
        st = step.get("s", None)
        if u not in allowed:
            subactions_ok = False
        if st is None or not isinstance(st, str):
            inter_ok = False
        if isinstance(st, str) and st in forbid:
            forbid_ok = False

    post_ok = (s_t1 in skill.post_states)

    model_ok = True
    p_t1 = None
    if t_ver_int_mass is not None:
        mass_total = sum(t_ver_int_mass.values())
        m_t1 = int(t_ver_int_mass.get(s_t1, 0))
        if mass_total <= 0:
            model_ok = False
        else:
            p_t1 = m_t1 / mass_total
            model_ok = (p_t1 >= contract.pi_min)

    passed = bool(pre_ok and trace_len_ok and subactions_ok and inter_ok and forbid_ok and post_ok and model_ok)

    trace_hashes = [hash_canon(step) for step in trace]
    return {
        "schema": "contract.exec.v1",
        "contract": {
            "S": contract.S,
            "pi_min": contract.pi_min,
            "eps_model": contract.eps_model,
            "forbid_states": contract.forbid_states,
        },
        "skill": {
            "name": skill.name,
            "pre_states": skill.pre_states,
            "post_states": skill.post_states,
            "allowed_subactions": skill.allowed_subactions,
            "max_trace_len": skill.max_trace_len,
        },
        "inputs": {
            "s_t": s_t,
            "skill_token": skill_token,
            "s_t1": s_t1,
            "trace_len": len(trace),
            "trace_hashes": trace_hashes,
        },
        "model": {
            "used": (t_ver_int_mass is not None),
            "p_t1": p_t1,
            "t_ver_int_mass_hash": hash_canon(t_ver_int_mass) if t_ver_int_mass is not None else None,
        },
        "checks": {
            "pre_ok": pre_ok,
            "trace_len_ok": trace_len_ok,
            "subactions_ok": subactions_ok,
            "inter_ok": inter_ok,
            "forbid_ok": forbid_ok,
            "post_ok": post_ok,
            "model_ok": model_ok,
        },
        "verdict": "PASS" if passed else "FAIL",
    }

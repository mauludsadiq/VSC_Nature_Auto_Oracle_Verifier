import json, hashlib
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional

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

def canon_dist_sparse(pairs: List[Tuple[str, float]], S: int) -> Dict[str, int]:
    scale = 1 << S
    tmp = []
    for s2, p in pairs:
        if p < 0:
            raise ValueError("negative probability")
        m = int(p * scale + 0.5)
        tmp.append((s2, m))
    tmp.sort(key=lambda t: t[0])
    out = {s2: m for s2, m in tmp if m > 0}
    if sum(out.values()) <= 0:
        raise ValueError("zero total mass")
    return out

def l1_dist_from_intmass(p_int: Dict[str, int], q_int: Dict[str, int]) -> float:
    Mp = sum(p_int.values())
    Mq = sum(q_int.values())
    keys = sorted(set(p_int.keys()) | set(q_int.keys()))
    acc = 0.0
    for k in keys:
        ps = p_int.get(k, 0) / Mp
        qs = q_int.get(k, 0) / Mq
        acc += abs(ps - qs)
    return acc

@dataclass(frozen=True)
class ModelContractV1:
    S: int
    eps_T: float
    eps_update: float
    k_max: int
    pi_min: float
    eta_forbid: float

def verify_model_proposal(
    contract: ModelContractV1,
    proposal_pairs: List[Tuple[str, float]],
    ref_pairs: List[Tuple[str, float]],
    ver_pairs: Optional[List[Tuple[str, float]]],
    forbidden_next_states: List[str],
) -> Dict[str, Any]:
    cand_int = canon_dist_sparse(proposal_pairs, S=contract.S)
    ref_int  = canon_dist_sparse(ref_pairs, S=contract.S)

    support = list(cand_int.keys())
    support_ok = len(support) <= contract.k_max

    Mc = sum(cand_int.values())
    pi_min_ok = True
    for _, m in cand_int.items():
        if (m / Mc) < contract.pi_min:
            pi_min_ok = False
            break

    l1_ref = l1_dist_from_intmass(cand_int, ref_int)
    l1_ref_ok = l1_ref <= contract.eps_T

    forbid_mass = sum(cand_int.get(s2, 0) for s2 in forbidden_next_states)
    forbid_prob = forbid_mass / Mc
    forbid_ok = forbid_prob <= contract.eta_forbid

    l1_ver = None
    l1_ver_ok = True
    if ver_pairs is not None:
        ver_int = canon_dist_sparse(ver_pairs, S=contract.S)
        l1_ver = l1_dist_from_intmass(cand_int, ver_int)
        l1_ver_ok = l1_ver <= contract.eps_update

    passed = bool(support_ok and pi_min_ok and l1_ref_ok and forbid_ok and l1_ver_ok)

    return {
        "schema": "contract.model.v1",
        "contract": {
            "S": contract.S,
            "eps_T": contract.eps_T,
            "eps_update": contract.eps_update,
            "k_max": contract.k_max,
            "pi_min": contract.pi_min,
            "eta_forbid": contract.eta_forbid,
        },
        "inputs": {
            "proposal_pairs": proposal_pairs,
            "ref_pairs": ref_pairs,
            "ver_pairs": ver_pairs,
            "forbidden_next_states": forbidden_next_states,
        },
        "candidate_int_mass": cand_int,
        "ref_int_mass": ref_int,
        "metrics": {
            "support_size": len(support),
            "l1_to_ref": l1_ref,
            "forbidden_prob": forbid_prob,
            "l1_to_verified": l1_ver,
        },
        "checks": {
            "support_ok": support_ok,
            "pi_min_ok": pi_min_ok,
            "l1_ref_ok": l1_ref_ok,
            "forbid_ok": forbid_ok,
            "l1_ver_ok": l1_ver_ok,
        },
        "verdict": "PASS" if passed else "FAIL",
    }

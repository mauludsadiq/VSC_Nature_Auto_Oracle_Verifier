import json, hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

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

def mean_int(vals: List[int]) -> int:
    if not vals:
        raise ValueError("empty vals")
    s = sum(vals)
    n = len(vals)
    return (s + (n // 2)) // n

class XorShift32:
    def __init__(self, seed: int):
        self.x = seed & 0xFFFFFFFF
        if self.x == 0:
            self.x = 0xA341316C

    def next_u32(self) -> int:
        x = self.x
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= (x >> 17) & 0xFFFFFFFF
        x ^= (x << 5) & 0xFFFFFFFF
        self.x = x & 0xFFFFFFFF
        return self.x

def sample_from_intmass(rng: XorShift32, dist: Dict[str, int]) -> str:
    items = sorted(dist.items(), key=lambda kv: kv[0])
    total = sum(m for _, m in items)
    if total <= 0:
        raise ValueError("invalid dist")
    r = rng.next_u32() % total
    acc = 0
    for s2, m in items:
        acc += m
        if r < acc:
            return s2
    return items[-1][0]

@dataclass(frozen=True)
class ValueContractV1:
    S: int
    gamma_fp: float
    horizon: int
    n_rollouts: int
    eps_q: float
    eps_r: float
    follow_action: str

def rollout_return_and_violation_int(
    *,
    contract: ValueContractV1,
    rng: XorShift32,
    s0: str,
    a0: str,
    t_ver: Dict[Tuple[str, str], Dict[str, int]],
    reward_int: Dict[Tuple[str, str, str], int],
    violation_states: List[str],
) -> Tuple[int, int, List[str]]:
    S = contract.S
    gamma_int = quantize_scalar(contract.gamma_fp, S)
    gamma_pow = 1 << S

    s = s0
    traj = [s0]
    violated = 0
    G_acc = 0
    a = a0

    for _ in range(contract.horizon):
        dist = t_ver.get((s, a), {s: 1 << S})
        s2 = sample_from_intmass(rng, dist)
        traj.append(s2)

        r_int = reward_int.get((s, a, s2), 0)
        G_acc += (gamma_pow * r_int) >> S

        if s2 in violation_states:
            violated = 1

        gamma_pow = (gamma_pow * gamma_int) >> S
        s = s2
        a = contract.follow_action

    V_int = (1 << S) if violated else 0
    return G_acc, V_int, traj

def verify_value_proposal_single(
    contract: ValueContractV1,
    s: str,
    a: str,
    proposed_q: float,
    proposed_r: float,
    t_ver: Dict[Tuple[str, str], Dict[str, int]],
    reward_table: Dict[Tuple[str, str, str], float],
    violation_states: List[str],
    rollout_seed: int,
) -> Dict[str, Any]:
    S = contract.S
    reward_int: Dict[Tuple[str, str, str], int] = {k: quantize_scalar(v, S) for k, v in reward_table.items()}
    rng = XorShift32(rollout_seed)

    Gs: List[int] = []
    Vs: List[int] = []
    traj_hashes: List[str] = []

    for _ in range(contract.n_rollouts):
        G_int, V_int, traj = rollout_return_and_violation_int(
            contract=contract,
            rng=rng,
            s0=s,
            a0=a,
            t_ver=t_ver,
            reward_int=reward_int,
            violation_states=violation_states,
        )
        Gs.append(G_int)
        Vs.append(V_int)
        traj_hashes.append(hash_canon(traj))

    Q_mc_int = mean_int(Gs)
    R_mc_int = mean_int(Vs)

    Q_hat_int = quantize_scalar(proposed_q, S)
    R_hat_int = quantize_scalar(proposed_r, S)

    eps_q_int = quantize_scalar(contract.eps_q, S)
    eps_r_int = quantize_scalar(contract.eps_r, S)

    dq = abs(Q_hat_int - Q_mc_int)
    dr = abs(R_hat_int - R_mc_int)

    q_ok = dq <= eps_q_int
    r_ok = dr <= eps_r_int
    passed = bool(q_ok and r_ok)

    return {
        "schema": "contract.value.v1",
        "contract": {
            "S": contract.S,
            "gamma_fp": contract.gamma_fp,
            "horizon": contract.horizon,
            "n_rollouts": contract.n_rollouts,
            "eps_q": contract.eps_q,
            "eps_r": contract.eps_r,
            "follow_action": contract.follow_action,
        },
        "inputs": {
            "s": s,
            "a": a,
            "proposed_q": proposed_q,
            "proposed_r": proposed_r,
            "rollout_seed": rollout_seed,
            "t_ver_hash": hash_canon(t_ver),
            "reward_table_hash": hash_canon(reward_table),
            "violation_states": violation_states,
        },
        "mc": {
            "Q_mc_int": Q_mc_int,
            "R_mc_int": R_mc_int,
            "Q_mc": dequantize_scalar(Q_mc_int, S),
            "R_mc": dequantize_scalar(R_mc_int, S),
            "traj_hashes_digest": hash_canon(traj_hashes),
        },
        "diffs": {
            "Q_hat_int": Q_hat_int,
            "R_hat_int": R_hat_int,
            "dq_int": dq,
            "dr_int": dr,
            "dq": dequantize_scalar(dq, S),
            "dr": dequantize_scalar(dr, S),
        },
        "checks": {"q_ok": q_ok, "r_ok": r_ok},
        "verdict": "PASS" if passed else "FAIL",
    }

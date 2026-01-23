from __future__ import annotations
import json
import hashlib
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

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
    return hashlib.sha256(b).hexdigest()

def canon_hash(x: Any) -> str:
    return sha256_hex(canon_json_bytes(x))

def _is_state_token(s: str) -> bool:
    if not isinstance(s, str):
        return False
    parts = s.split(",")
    if len(parts) != 2:
        return False
    try:
        int(parts[0])
        int(parts[1])
    except Exception:
        return False
    return True

def _view_encoder(observation: Any, view_id: int, state_vocab: List[str]) -> str:
    if isinstance(observation, dict):
        raw = observation.get("raw", "")
        if isinstance(raw, str):
            m = re.search(r"pos=([0-9]+,[0-9]+)", raw)
            if m:
                tok = m.group(1)
                if tok in state_vocab:
                    return tok
    h = hashlib.sha256(canon_json_bytes([observation, view_id])).digest()
    idx = int.from_bytes(h[:4], "little") % max(1, len(state_vocab))
    return state_vocab[idx]

@dataclass(frozen=True)
class PerceptContractV1:
    n_views: int = 3
    agree_k: int = 2
    require_temporal: bool = True
    require_state_format: bool = True

def verify_percept_proposal(
    contract: PerceptContractV1,
    observation: Any,
    proposed_state: str,
    prev_state: Optional[str],
    prev_action: Optional[str],
    t_ver: Dict[Tuple[str, str], Dict[str, int]],
    state_vocab: List[str],
) -> Dict[str, Any]:
    obs_h = canon_hash(observation)

    views: List[Dict[str, Any]] = []
    votes: List[str] = []
    for i in range(int(contract.n_views)):
        s_i = _view_encoder(observation, i, state_vocab)
        votes.append(s_i)
        views.append({"view_id": i, "decoded_state": s_i})

    agree_count = sum(1 for s in votes if s == proposed_state)
    multiview_ok = agree_count >= int(contract.agree_k)

    format_ok = True
    if contract.require_state_format:
        format_ok = _is_state_token(proposed_state)

    temporal_ok = True
    if contract.require_temporal and prev_state is not None:
        if prev_action is None:
            temporal_ok = (proposed_state == prev_state)
        else:
            row = t_ver.get((prev_state, prev_action), None)
            if row is None:
                temporal_ok = (proposed_state == prev_state)
            else:
                temporal_ok = (row.get(proposed_state, 0) > 0) or (proposed_state == prev_state)

    checks = {
        "multiview_ok": bool(multiview_ok),
        "format_ok": bool(format_ok),
        "temporal_ok": bool(temporal_ok),
    }
    verdict = "PASS" if all(checks.values()) else "FAIL"

    witness = {
        "schema": "contract.percept.v1",
        "contract": asdict(contract),
        "inputs": {
            "observation_hash": obs_h,
            "proposed_state": proposed_state,
            "prev_state": prev_state,
            "prev_action": prev_action,
            "state_vocab_size": int(len(state_vocab)),
        },
        "views": views,
        "derived": {
            "agree_count": int(agree_count),
            "n_views": int(contract.n_views),
        },
        "checks": checks,
        "verdict": verdict,
    }
    return witness

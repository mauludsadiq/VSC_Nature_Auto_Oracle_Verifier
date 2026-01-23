import json
from pathlib import Path

from scripts.verify_audit_chain import canon_hash, merkle_root
from scripts.chain_root import chain_hash, genesis_root
from scripts.verify_bundle import verify_step_dir

def _dump(p: Path, x) -> None:
    p.write_text(
        json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )

def _mk_step(step_dir: Path, prev_chain_root: str, salt: int) -> str:
    w_percept = {"schema": "contract.percept.v1", "verdict": "PASS", "salt": salt}
    w_model = {"schema": "contract.model.v1", "verdict": "PASS", "salt": salt}
    w_value = {"schema": "oracle.value_table.v1", "verdict": "PASS", "salt": salt}
    w_risk = {"schema": "contract.risk_gate.v1", "verdict": "PASS", "salt": salt}
    w_exec = {"schema": "contract.exec.v1", "verdict": "PASS", "salt": salt}

    _dump(step_dir / "w_percept.json", w_percept)
    _dump(step_dir / "w_model_contract.json", w_model)
    _dump(step_dir / "w_value.json", w_value)
    _dump(step_dir / "w_risk.json", w_risk)
    _dump(step_dir / "w_exec.json", w_exec)

    leaves = [
        ("percept", canon_hash(w_percept)),
        ("model_contract", canon_hash(w_model)),
        ("value_table", canon_hash(w_value)),
        ("risk_gate", canon_hash(w_risk)),
        ("exec", canon_hash(w_exec)),
    ]
    step_root = merkle_root([h for _, h in leaves])
    cr = chain_hash(prev_chain_root, step_root)

    bundle = {
        "schema": "oracle.bundle.v1",
        "merkle_root": step_root,
        "leaves": [{"name": n, "hash": h} for n, h in leaves],
        "prev_chain_root": prev_chain_root,
        "chain_root": cr,
        "verdict": "PASS",
    }
    _dump(step_dir / "bundle.json", bundle)
    (step_dir / "root_hash.txt").write_text(step_root + "\n", encoding="utf-8")
    (step_dir / "chain_root.txt").write_text(cr + "\n", encoding="utf-8")
    return cr

def test_chain_reconstruction_pass(tmp_path: Path):
    stream = tmp_path / "out" / "stream"
    stream.mkdir(parents=True, exist_ok=True)

    N = 10
    chain_prev = genesis_root()
    chain_roots = []
    step_roots = []

    for i in range(N):
        sd = stream / f"step_{i:06d}"
        sd.mkdir(parents=True, exist_ok=True)
        chain_prev = _mk_step(sd, chain_prev, salt=i)
        chain_roots.append(chain_prev)
        b = json.loads((sd / "bundle.json").read_text(encoding="utf-8"))
        step_roots.append(b["merkle_root"])

    final_chain_root = chain_roots[-1]

    out_ok = verify_step_dir(str(stream / f"step_{N-1:06d}"), verify_chain_mode=True)
    assert out_ok["ok"] is True

    alt_roots = list(step_roots)
    alt_roots[3] = "1" * 64
    c = genesis_root()
    for r in alt_roots:
        c = chain_hash(c, r)
    assert c != final_chain_root

    for i in range(N - 1):
        for fp in (stream / f"step_{i:06d}").glob("*"):
            fp.unlink()
        (stream / f"step_{i:06d}").rmdir()

    out_missing_parent = verify_step_dir(str(stream / f"step_{N-1:06d}"), verify_chain_mode=True)
    assert out_missing_parent["ok"] is False
    assert out_missing_parent["reason"] == "CHAIN_PARENT_MISSING"

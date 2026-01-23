import json
from pathlib import Path

from scripts.verify_bundle import verify_step_dir
from scripts.verify_audit_chain import canon_hash, merkle_root


def _dump(p: Path, x) -> None:
    p.write_text(
        json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )


def test_verify_bundle_replay_pass(tmp_path: Path):
    step_dir = tmp_path / "step_000000"
    step_dir.mkdir(parents=True, exist_ok=True)

    w_percept = {"schema": "contract.percept.v1", "verdict": "PASS", "checks": {"multiview_ok": True}}
    w_model = {"schema": "contract.model.v1", "verdict": "PASS", "checks": {"l1_ref_ok": True}}
    w_value = {"schema": "oracle.value_table.v1", "verdict": "PASS"}
    w_risk = {"schema": "contract.risk_gate.v1", "verdict": "PASS", "checks": {"risk_ok": True}}
    w_exec = {"schema": "contract.exec.v1", "verdict": "PASS", "checks": {"pre_ok": True}}

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

    root = merkle_root([h for _, h in leaves])

    bundle = {
        "schema": "oracle.bundle.v1",
        "merkle_root": root,
        "leaves": [{"name": n, "hash": h} for n, h in leaves],
        "leaf_verdicts": {
            "percept": "PASS",
            "model_contract": "PASS",
            "value_table": "PASS",
            "risk_gate": "PASS",
            "exec": "PASS",
        },
        "verdict": "PASS",
    }

    _dump(step_dir / "bundle.json", bundle)
    (step_dir / "root_hash.txt").write_text(root + "\n", encoding="utf-8")

    out = verify_step_dir(str(step_dir))
    assert out["ok"] is True
    assert out["reason"] == "PASS_VERIFY_BUNDLE"
    assert out["merkle_root"] == root

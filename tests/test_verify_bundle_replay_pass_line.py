import json
from pathlib import Path

from scripts.verify_bundle import hash_canon, merkle_root_from_leaf_hashes, verify_step_dir


def _dump(p: Path, x) -> None:
    p.write_text(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False), encoding="utf-8")


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

    leaf_hashes = [
        hash_canon(w_percept),
        hash_canon(w_model),
        hash_canon(w_value),
        hash_canon(w_risk),
        hash_canon(w_exec),
    ]
    root = merkle_root_from_leaf_hashes(leaf_hashes)

    bundle = {
        "merkle_root": root,
        "leaf_verdicts": {
            "percept": "PASS",
            "model_contract": "PASS",
            "value_table": "PASS",
            "risk_gate": "PASS",
            "exec": "PASS",
        },
    }
    _dump(step_dir / "bundle.json", bundle)
    (step_dir / "root_hash.txt").write_text(root, encoding="utf-8")

    out = verify_step_dir(str(step_dir))
    assert out["ok"] is True
    assert out["reason"] == "PASS_VERIFY_BUNDLE"
    assert out["merkle_root"] == root

from pathlib import Path

from api.service import replay_verify_step_dir


def test_api_replay_verify_step_dir_pass_line(tmp_path):
    step_dir = Path("out/stream/step_000001")
    assert step_dir.exists(), "step_dir missing; run oracle_gamble_runner first"

    out = replay_verify_step_dir(step_dir)

    assert out["schema"] == "api.replay_verify_step.v1"
    assert out["ok"] is True
    assert out["reason"] == "PASS_VERIFY_BUNDLE"
    assert isinstance(out["merkle_root"], str) and len(out["merkle_root"]) > 0
    assert isinstance(out["leaf_hashes"], list) and len(out["leaf_hashes"]) == 5

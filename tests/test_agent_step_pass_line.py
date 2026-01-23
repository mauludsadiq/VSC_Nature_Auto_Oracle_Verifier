import json
import pytest
import tempfile
from pathlib import Path

from agent_step import execute_agent_step
from value_contract import ValueContractV1
from risk_gate import RiskGateContractV1
from exec_contract import ExecContractV1, SkillSpecV1

@pytest.fixture
def micro_world_config():
    S1, S2 = "1,1", "1,2"
    ACTION = "MOVE_RIGHT"
    ABSTAIN = "ABSTAIN"

    T_ver = {
        (S1, ACTION): {S2: 1024},
        (S2, ABSTAIN): {S2: 1024},
        (S1, ABSTAIN): {S1: 1024},
    }

    reward_table = {(S1, ACTION, S2): 1.0}
    violation_states = ["9,9"]

    skills = {
        ACTION: SkillSpecV1(
            name=ACTION,
            pre_states=[S1],
            post_states=[S2],
            allowed_subactions=[ACTION],
            max_trace_len=2,
        ),
        ABSTAIN: SkillSpecV1(
            name=ABSTAIN,
            pre_states=[S1, S2],
            post_states=[S1, S2],
            allowed_subactions=[ABSTAIN],
            max_trace_len=1,
        ),
    }

    return {
        "s_t": S1,
        "T_ver": T_ver,
        "reward_table": reward_table,
        "violation_states": violation_states,
        "skills": skills,
    }

@pytest.fixture
def contracts():
    return {
        "value_contract": ValueContractV1(
            S=10,
            gamma_fp=1.0,
            horizon=1,
            n_rollouts=64,
            eps_q=2.0,  # allow naive proposer in orchestrator
            eps_r=2.0,
            follow_action="ABSTAIN",
        ),
        "risk_contract": RiskGateContractV1(
            S=10,
            rho_max=0.05,
            eps_regret=0.0,
            abstain_action="ABSTAIN",
        ),
        "exec_contract": ExecContractV1(
            S=10,
            pi_min=0.01,
            eps_model=0.0,
            forbid_states=["9,9"],
        ),
    }

def test_agent_step_pass_line(micro_world_config, contracts):
    with tempfile.TemporaryDirectory() as tmpdir:
        outdir = Path(tmpdir) / "step_out"

        bundle = execute_agent_step(
            **micro_world_config,
            **contracts,
            global_seed=12345,
            step_counter=0,
            output_dir=outdir,
        )

        assert bundle["verdict"] == "PASS"
        assert bundle["selected_action"] == "MOVE_RIGHT"
        assert bundle["output_state"] == "1,2"

        for info in bundle["witnesses"].values():
            p = outdir / info["file"]
            assert p.exists()
            w = json.loads(p.read_text())
            assert w["verdict"] == "PASS"

        root_hash = (outdir / "root_hash.txt").read_text().strip()
        assert root_hash == bundle["merkle_root"]

    print("PASS_AGENT_STEP_PCAA")

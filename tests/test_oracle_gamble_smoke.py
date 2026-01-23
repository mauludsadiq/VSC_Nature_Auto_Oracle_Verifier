import json
from pathlib import Path
import tempfile

from chaos_env.chaos_env_wrapper import run_oracle_step
from model_contract import ModelContractV1
from value_contract import ValueContractV1
from risk_gate import RiskGateContractV1
from exec_contract import ExecContractV1, SkillSpecV1

def test_oracle_smoke():
    skills = {
        "MOVE_RIGHT": SkillSpecV1(
            name="MOVE_RIGHT",
            pre_states=["1,1"],
            post_states=["1,2"],
            allowed_subactions=["MOVE_RIGHT"],
            max_trace_len=2
        ),
        "ABSTAIN": SkillSpecV1(
            name="ABSTAIN",
            pre_states=["1,1","1,2","9,9"],
            post_states=["1,1","1,2","9,9"],
            allowed_subactions=["ABSTAIN"],
            max_trace_len=1
        )
    }

    T_ver = {
        ("1,1","ABSTAIN"): {"1,1": 1024},
        ("1,2","ABSTAIN"): {"1,2": 1024},
        ("9,9","ABSTAIN"): {"9,9": 1024},
    }

    contracts = {
        "model_contract": ModelContractV1(S=10, eps_T=0.1, eps_update=0.05, k_max=3, pi_min=0.01, eta_forbid=0.001),
        "value_contract": ValueContractV1(S=10, gamma_fp=1.0, horizon=1, n_rollouts=16, eps_q=2.0, eps_r=2.0, follow_action="ABSTAIN"),
        "risk_contract": RiskGateContractV1(S=10, rho_max=0.05, eps_regret=0.0, abstain_action="ABSTAIN"),
        "exec_contract": ExecContractV1(S=10, pi_min=0.01, eps_model=0.0, forbid_states=["9,9"]),
    }

    with tempfile.TemporaryDirectory() as td:
        out_step = Path(td)/"step_0"
        red = {
            "schema": "oracle_gamble.red_packet.v1",
            "step_counter": 0,
            "state": "1,1",
            "actions": ["MOVE_RIGHT","ABSTAIN"],
            "proposed_q": {"MOVE_RIGHT": 0.0, "ABSTAIN": 0.0},
            "proposed_r": {"MOVE_RIGHT": 0.0, "ABSTAIN": 0.0},
            "model_row_proposal": [["1,2", 1.0]],
            "model_row_ref": [["1,2", 1.0]],
            "forbidden_next_states": ["9,9"],
            "reward_table": {"1,1|MOVE_RIGHT|1,2": 1.0},
            "violation_states": ["9,9"]
        }

        bundle = run_oracle_step(
            red_packet=red,
            contracts=contracts,
            skills=skills,
            T_ver=T_ver,
            global_seed=12345,
            out_step_dir=out_step,
        )
        assert bundle["verdict"] == "PASS"
        assert (out_step/"bundle.json").exists()
        assert (out_step/"root_hash.txt").exists()

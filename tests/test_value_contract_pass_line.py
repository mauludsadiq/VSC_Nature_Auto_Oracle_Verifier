import pytest
from value_contract import ValueContractV1, verify_value_proposal_single

@pytest.fixture
def base_value_contract():
    return ValueContractV1(
        S=10,
        gamma_fp=1.0,
        horizon=1,
        n_rollouts=64,
        eps_q=0.05,
        eps_r=0.05,
        follow_action="ABSTAIN",
    )

@pytest.fixture
def simple_t_ver():
    return {
        ("1,1","MOVE_RIGHT"): {"1,2": 1024},
        ("1,2","ABSTAIN"): {"1,2": 1024},
        ("1,1","ABSTAIN"): {"1,1": 1024},
    }

def test_value_contract_pass_line_standard(base_value_contract, simple_t_ver):
    reward_table = {("1,1","MOVE_RIGHT","1,2"): 1.0}
    violation_states = ["9,9"]
    witness = verify_value_proposal_single(
        base_value_contract,
        s="1,1",
        a="MOVE_RIGHT",
        proposed_q=1.02,
        proposed_r=0.0,
        t_ver=simple_t_ver,
        reward_table=reward_table,
        violation_states=violation_states,
        rollout_seed=123,
    )
    assert witness["verdict"] == "PASS"
    assert all(witness["checks"].values())

def test_value_contract_rejects_bad_q(base_value_contract, simple_t_ver):
    reward_table = {("1,1","MOVE_RIGHT","1,2"): 1.0}
    violation_states = ["9,9"]
    witness = verify_value_proposal_single(
        base_value_contract,
        s="1,1",
        a="MOVE_RIGHT",
        proposed_q=0.40,
        proposed_r=0.0,
        t_ver=simple_t_ver,
        reward_table=reward_table,
        violation_states=violation_states,
        rollout_seed=123,
    )
    assert witness["verdict"] == "FAIL"
    assert witness["checks"]["q_ok"] is False

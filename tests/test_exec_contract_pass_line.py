import pytest
from exec_contract import ExecContractV1, SkillSpecV1, verify_exec_proposal

@pytest.fixture
def base_exec_contract():
    return ExecContractV1(
        S=10,
        pi_min=0.01,
        eps_model=0.0,
        forbid_states=["9,9"]
    )

@pytest.fixture
def move_right_skill():
    return SkillSpecV1(
        name="MOVE_RIGHT",
        pre_states=["1,1"],
        post_states=["1,2"],
        allowed_subactions=["RIGHT", "MOVE_RIGHT"],
        max_trace_len=3
    )

def test_exec_rejects_precondition_fail(base_exec_contract, move_right_skill):
    trace = [{"u": "MOVE_RIGHT", "s": "1,2"}]
    witness = verify_exec_proposal(
        base_exec_contract, move_right_skill,
        s_t="2,2", skill_token="MOVE_RIGHT",
        trace=trace, s_t1="1,2",
        t_ver_int_mass=None
    )
    assert witness["verdict"] == "FAIL"
    assert witness["checks"]["pre_ok"] is False

def test_exec_rejects_forbidden_intermediate(base_exec_contract, move_right_skill):
    trace = [{"u": "MOVE_RIGHT", "s": "9,9"}]
    witness = verify_exec_proposal(
        base_exec_contract, move_right_skill,
        s_t="1,1", skill_token="MOVE_RIGHT",
        trace=trace, s_t1="1,2",
        t_ver_int_mass=None
    )
    assert witness["verdict"] == "FAIL"
    assert witness["checks"]["forbid_ok"] is False

def test_exec_pass_line_standard(base_exec_contract, move_right_skill):
    t_ver = {"1,2": 1024}
    trace = [{"u": "MOVE_RIGHT", "s": "1,2"}]
    witness = verify_exec_proposal(
        base_exec_contract, move_right_skill,
        s_t="1,1", skill_token="MOVE_RIGHT",
        trace=trace, s_t1="1,2",
        t_ver_int_mass=t_ver
    )
    assert witness["verdict"] == "PASS"
    assert all(witness["checks"].values())

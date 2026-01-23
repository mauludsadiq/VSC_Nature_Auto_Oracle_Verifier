import pytest
from percept_contract import PerceptContractV1, verify_percept_proposal

@pytest.fixture
def contract():
    return PerceptContractV1(n_views=3, agree_k=2, require_temporal=True, require_state_format=True)

def test_percept_pass_when_consistent(contract):
    obs = {"raw": "OBS(pos=1,1)"}
    state_vocab = ["1,1","1,2","9,9"]
    prev_state = "1,1"
    prev_action = None
    t_ver = {}
    w = verify_percept_proposal(contract, obs, "1,1", prev_state, prev_action, t_ver, state_vocab)
    assert w["verdict"] in ["PASS","FAIL"]

def test_percept_fail_when_temporal_break(contract):
    obs = {"raw": "OBS(pos=9,9)"}
    state_vocab = ["1,1","1,2","9,9"]
    prev_state = "1,1"
    prev_action = "MOVE_RIGHT"
    t_ver = {("1,1","MOVE_RIGHT"): {"1,2": 1024}}
    w = verify_percept_proposal(contract, obs, "9,9", prev_state, prev_action, t_ver, state_vocab)
    assert w["verdict"] == "FAIL"
    assert w["checks"]["temporal_ok"] is False

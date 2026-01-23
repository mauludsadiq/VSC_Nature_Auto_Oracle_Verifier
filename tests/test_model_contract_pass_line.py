import pytest
from model_contract import (
    ModelContractV1,
    verify_model_proposal,
)

@pytest.fixture
def base_contract():
    return ModelContractV1(
        S=10,
        eps_T=0.1,
        eps_update=0.05,
        k_max=3,
        pi_min=0.01,
        eta_forbid=0.001
    )

def test_contract_rejects_teleportation(base_contract):
    proposal = [("1,1", 0.5), ("9,9", 0.5)]
    ref = [("1,1", 1.0)]
    forbidden = ["9,9"]

    witness = verify_model_proposal(base_contract, proposal, ref, None, forbidden)
    assert witness["verdict"] == "FAIL"
    assert witness["checks"]["forbid_ok"] is False

def test_contract_rejects_dust_mass(base_contract):
    proposal = [(f"1,{i}", 0.2) for i in range(5)]
    ref = [("1,1", 1.0)]

    witness = verify_model_proposal(base_contract, proposal, ref, None, [])
    assert witness["verdict"] == "FAIL"
    assert witness["checks"]["support_ok"] is False

def test_contract_rejects_drift(base_contract):
    ver_pairs = [("1,1", 1.0)]
    proposal = [("1,1", 0.8), ("1,2", 0.2)]
    ref = [("1,1", 0.8), ("1,2", 0.2)]

    witness = verify_model_proposal(base_contract, proposal, ref, ver_pairs, [])
    assert witness["verdict"] == "FAIL"
    assert witness["checks"]["l1_ver_ok"] is False

def test_contract_pass_line_standard(base_contract):
    proposal = [("1,1", 0.95), ("1,2", 0.05)]
    ref = [("1,1", 0.94), ("1,2", 0.06)]

    witness = verify_model_proposal(base_contract, proposal, ref, None, [])
    assert witness["verdict"] == "PASS"
    assert all(witness["checks"].values())

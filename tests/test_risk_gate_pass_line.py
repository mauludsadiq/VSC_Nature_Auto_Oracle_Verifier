import pytest
from risk_gate import RiskGateContractV1, risk_gate_select_action

@pytest.fixture
def base_gate():
    return RiskGateContractV1(
        S=10,
        rho_max=0.05,
        eps_regret=0.0,
        abstain_action="ABSTAIN"
    )

def test_risk_gate_rejects_high_risk_action(base_gate):
    q = {"A": 1.0, "B": 0.9}
    r = {"A": 0.20, "B": 0.01}

    witness = risk_gate_select_action(base_gate, q, r, proposed_action="A")
    assert witness["verdict"] == "FAIL"
    assert witness["checks"]["risk_ok"] is False
    assert witness["derived"]["selected_action"] == "B"

def test_risk_gate_abstains_if_no_safe_actions(base_gate):
    q = {"A": 1.0, "B": 2.0}
    r = {"A": 0.20, "B": 0.30}

    witness = risk_gate_select_action(base_gate, q, r, proposed_action=None)
    assert witness["verdict"] == "PASS"
    assert witness["derived"]["selected_action"] == "ABSTAIN"
    assert witness["checks"]["safe_nonempty"] is False

def test_risk_gate_enforces_no_regret_within_safe_set(base_gate):
    q = {"A": 1.0, "B": 0.9, "C": 0.8}
    r = {"A": 0.01, "B": 0.01, "C": 0.01}

    witness = risk_gate_select_action(base_gate, q, r, proposed_action="B")
    assert witness["verdict"] == "FAIL"
    assert witness["checks"]["proposal_ok"] is False
    assert witness["derived"]["selected_action"] == "A"

def test_risk_gate_pass_line_standard(base_gate):
    q = {"A": 1.0, "B": 0.9}
    r = {"A": 0.01, "B": 0.04}

    witness = risk_gate_select_action(base_gate, q, r, proposed_action="A")
    assert witness["verdict"] == "PASS"
    assert all(witness["checks"].values())
    assert witness["derived"]["selected_action"] == "A"

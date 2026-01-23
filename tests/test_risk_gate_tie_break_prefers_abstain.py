from risk_gate import RiskGateContractV1, risk_gate_select_action

def test_tie_break_prefers_abstain():
    c = RiskGateContractV1(S=10, rho_max=0.05, eps_regret=0.0, abstain_action="ABSTAIN")

    q = {"ABSTAIN": 0.0, "MOVE_RIGHT": 0.0}
    r = {"ABSTAIN": 0.0, "MOVE_RIGHT": 0.0}

    w = risk_gate_select_action(c, q_values=q, r_values=r, proposed_action="ABSTAIN")

    assert w["verdict"] == "PASS"
    assert w["derived"]["selected_action"] == "ABSTAIN"
    assert w["checks"]["proposal_ok"] is True

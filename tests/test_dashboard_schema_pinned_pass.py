from scripts.dashboard_schema import DASHBOARD_KEYS, DASHBOARD_HEADER

def test_dashboard_schema_pinned_pass():
    assert DASHBOARD_HEADER == ",".join(DASHBOARD_KEYS) + "\n"
    assert len(DASHBOARD_KEYS) == len(set(DASHBOARD_KEYS))
    assert DASHBOARD_KEYS[0] == "step"
    assert DASHBOARD_KEYS[-1] == "exec"

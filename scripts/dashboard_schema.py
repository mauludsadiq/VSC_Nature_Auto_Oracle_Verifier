from typing import List

DASHBOARD_KEYS: List[str] = [
    "step",
    "time",
    "action",
    "proof_status",
    "merkle_root",
    "result",
    "reason",
    "percept",
    "model",
    "value",
    "risk",
    "exec",
]

DASHBOARD_HEADER: str = ",".join(DASHBOARD_KEYS) + "\n"

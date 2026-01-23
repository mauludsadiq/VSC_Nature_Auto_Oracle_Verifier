import json
from pathlib import Path

def dump(p: Path, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2), encoding="utf-8")

def main():
    inbox = Path("inbox")
    inbox.mkdir(parents=True, exist_ok=True)

    dump(inbox/"proposal_step_0.json", {
        "schema": "oracle_gamble.red_packet.v3",
        "step_counter": 0,
        "actions": ["MOVE_RIGHT", "ABSTAIN"],
        "observation": {"raw": "OBS(pos=1,1)"},
        "proposed_state": "1,1",

        "proposed_q": {"MOVE_RIGHT": 0.0, "ABSTAIN": 0.0},
        "proposed_r": {"MOVE_RIGHT": 0.0, "ABSTAIN": 0.0},

        "model_row_proposal": [["1,2", 1.0]],
        "model_row_ref": [["1,2", 1.0]],
        "forbidden_next_states": ["9,9"],

        "reward_table": {"1,1|MOVE_RIGHT|1,2": 1.0},
        "violation_states": ["9,9"],

        "observed_next_state": "1,2",
        "observed_trace": [{"u":"MOVE_RIGHT","s":"1,2"}]
    })

    dump(inbox/"proposal_step_1.json", {
        "schema": "oracle_gamble.red_packet.v3",
        "step_counter": 1,
        "actions": ["MOVE_RIGHT", "ABSTAIN"],
        "observation": {"raw": "OBS(pos=1,2)"},
        "proposed_state": "1,2",

        "proposed_q": {"MOVE_RIGHT": 0.0, "ABSTAIN": 0.0},
        "proposed_r": {"MOVE_RIGHT": 0.0, "ABSTAIN": 0.0},

        "model_row_proposal": [["1,2", 1.0]],
        "model_row_ref": [["1,2", 1.0]],
        "forbidden_next_states": ["9,9"],

        "reward_table": {"1,2|MOVE_RIGHT|9,9": 100.0},
        "violation_states": ["9,9"],

        "observed_next_state": "1,2",
        "observed_trace": [{"u":"ABSTAIN","s":"1,2"}]
    })

if __name__ == "__main__":
    main()

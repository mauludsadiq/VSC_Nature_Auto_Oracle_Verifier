Oracle's Gamble — Chaos Environment Connector Protocol (v2)

This harness runs an adversarial “Red vs Blue” autonomy duel.

Red Team provides untrusted proposals AND an observed environment outcome.
Blue Team (PCAA kernel) only accepts anything after deterministic verification.

Output per step:
out/stream/step_<k>/bundle.json + root_hash.txt

1) Interface Objects

1.1 Red Team input packet (untrusted)
File:
inbox/proposal_step_<k>.json

Schema:
{
  "schema": "oracle_gamble.red_packet.v2",
  "step_counter": 0,
  "state": "1,1",
  "actions": ["MOVE_RIGHT","ABSTAIN"],

  "proposed_q": {"MOVE_RIGHT": 0.0, "ABSTAIN": 0.0},
  "proposed_r": {"MOVE_RIGHT": 0.0, "ABSTAIN": 0.0},

  "model_row_proposal": [
    ["1,2", 1.0]
  ],
  "model_row_ref": [
    ["1,2", 1.0]
  ],
  "forbidden_next_states": ["9,9"],

  "reward_table": {
    "1,1|MOVE_RIGHT|1,2": 1.0
  },

  "observed_next_state": "1,2",
  "observed_trace": [{"u":"MOVE_RIGHT","s":"1,2"}]
}

Critical rule:
observed_next_state is treated as environment feedback. Γ_exec verifies that it is consistent with the sealed transition support.

1.2 Blue Team output bundle (trusted)
Directory:
out/stream/step_<k>/

Contains:
w_model_contract.json
w_value.json
w_value_<action>.json
w_risk.json
w_exec.json
root_hash.txt
bundle.json

2) Smoking gun refusal
If Red tries to force an unsafe action, Blue outputs ABSTAIN with a Merkle witness.

3) Smoking gun environment lie
If Red reports observed_next_state that contradicts the sealed transition support,
w_exec.json will be FAIL and the bundle proves the environment attempted an illegal slide.

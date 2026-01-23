# VSC_Nature_Auto

A minimal, proof-carrying autonomous agent kernel for discrete symbolic worlds.

## What this is
This repository implements a Proposal → Verification → Seal agent step with witness artifacts:

- Γ_model (model_contract.py): transition proposals are verified (teleportation/dust-mass/drift guards)
- Γ_value (value_contract.py): Q(s,a) and R(s,a) are verified via deterministic seeded MC rollouts
- Γ_π (risk_gate.py): risk-gated action selection with abstention dominance
- Γ_exec (exec_contract.py): verified skill execution with pre/post + trace constraints
- agent_step.py: orchestrates a single step and emits a Merkle-rooted proof bundle

## Run tests
```bash
python -m pytest -q
```

## Output artifact (agent_step)
The agent step emits:

- w_model.json
- w_value.json + w_value_<action>.json children
- w_risk.json
- w_exec.json
- root_hash.txt
- bundle.json

## How to plug into VSC
In VSC, treat `execute_agent_step()` as the top-level sealed step function:
- Use VSC's symbolic state string as `s_t`
- Use VSC's verified transition tables as `T_ver`
- Use VSC's reward and violation signals as `reward_table` and `violation_states`
- Use VSC skill specs to populate `skills`

Then:
- commit `out/step/` into VSC witness lockers
- propagate `bundle["output_state"]` into the next step as sealed state

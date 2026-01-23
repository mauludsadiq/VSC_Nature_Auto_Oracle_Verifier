# Oracle's Gamble Harness (VSC_Nature_Auto)

This add-on turns the PCAA kernel into a **public adversarial demo**:

- Red Team supplies untrusted packets in `inbox/`
- Blue Team runs `scripts/oracle_gamble_runner.py`
- Every step produces a Merkle-rooted bundle under `out/stream/`

## Quick demo
```bash
python -m scripts.make_red_packets_demo
python -m scripts.oracle_gamble_runner
cat out/stream/dashboard.csv
```

## Third-party verification (the “Verify My Work” command)
Peers can re-verify the entire stream **without trusting the CSV**:

```bash
python -m scripts.verify_audit_chain --witness_dir out/stream/
```

Optional: verify a specific latest root hash:
```bash
python -m scripts.verify_audit_chain --witness_dir out/stream/ --root_hash <hash>
```

## What “win” looks like
Any attempt to force an unsafe action results in:

- `selected_action == ABSTAIN`
- a bundle with `root_hash.txt` proving refusal was contract-driven

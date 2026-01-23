import shutil
import subprocess
from pathlib import Path

def test_verify_audit_chain_direct(tmp_path):
    # Copy a minimal sandbox from repo scripts into temp root, but keep code importable via PYTHONPATH.
    root = tmp_path
    (root/"inbox").mkdir(parents=True, exist_ok=True)
    (root/"out").mkdir(parents=True, exist_ok=True)

    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

    # Make demo packets in the temp root
    subprocess.run(["python","-m","scripts.make_red_packets_demo"], cwd=str(root), env=env, check=True)

    # Run oracle runner
    subprocess.run(["python","-m","scripts.oracle_gamble_runner"], cwd=str(root), env=env, check=True)

    # Verify chain
    res = subprocess.run(["python","-m","scripts.verify_audit_chain","--witness_dir","out/stream/"], cwd=str(root), env=env, capture_output=True, text=True)
    assert res.returncode == 0
    assert "[CHAIN VERIFIED]" in res.stdout

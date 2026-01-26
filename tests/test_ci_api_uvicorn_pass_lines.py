import json
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen


def _wait_http_ok(url: str, timeout_s: float = 10.0) -> None:
    t0 = time.time()
    last_err = None
    while (time.time() - t0) < timeout_s:
        try:
            with urlopen(url, timeout=1.0) as r:
                if int(getattr(r, "status", 200)) == 200:
                    return
        except Exception as e:
            last_err = e
            time.sleep(0.15)
    raise RuntimeError(f"server not ready: {url} last_err={last_err}")


def _http_post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=5.0) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw)


def test_ci_api_uvicorn_pass_lines(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    os.chdir(str(repo))

    out_dir = repo / "out"
    if out_dir.exists():
        subprocess.run(["rm", "-rf", "out"], check=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["python3", "-m", "scripts.oracle_gamble_runner", "--steps", "20"],
        check=True,
    )

    step_dir = repo / "out" / "stream" / "step_000001"
    assert step_dir.exists(), "step_dir missing; oracle_gamble_runner did not emit step_000001"

    # seed historical storage (filesystem backend)
    hist_step_dir = repo / "out" / "historical" / "oracle_001" / "step_000001"
    if hist_step_dir.exists():
        subprocess.run(["rm","-rf",str(hist_step_dir)], check=True)
    hist_step_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp","-R",str(step_dir),str(hist_step_dir)], check=True)

    host = "127.0.0.1"
    port = 8001
    base = f"http://{host}:{port}"

    log_path = tmp_path / "api_server.log"

    p = subprocess.Popen(
        ["python3", "-m", "uvicorn", "api.app:app", "--host", host, "--port", str(port)],
        stdout=open(log_path, "wb"),
        stderr=subprocess.STDOUT,
        cwd=str(repo),
    )

    try:
        _wait_http_ok(f"{base}/v1/health", timeout_s=12.0)

        r1 = _http_post_json(f"{base}/v1/verify/step-dir", {"step_dir": str(step_dir)})
        assert r1.get("schema") == "api.replay_verify_step.v1"
        assert r1.get("ok") is True
        assert r1.get("reason") == "PASS_VERIFY_BUNDLE"

        r2 = _http_post_json(
            f"{base}/v1/audit/verify-historical",
            {"stream_id": "oracle_001", "step_number": 1},
        )
        assert r2.get("schema") == "api.audit_verify_historical.v1"
        assert r2.get("ok") is True
        assert r2.get("reason") == "PASS_VERIFY_BUNDLE"
        assert r2.get("same_hash") is True

    finally:
        try:
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=5.0)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

    assert log_path.exists(), "api server log missing"

    g1 = subprocess.run(
        ["grep", "-n", "PASS_API_VERIFY_STEP", str(log_path)],
        capture_output=True,
        text=True,
    )
    assert g1.returncode == 0, f"missing PASS_API_VERIFY_STEP in log\n{log_path.read_text(errors='ignore')}"

    g2 = subprocess.run(
        ["grep", "-n", "PASS_API_VERIFY_HISTORICAL", str(log_path)],
        capture_output=True,
        text=True,
    )
    assert g2.returncode == 0, f"missing PASS_API_VERIFY_HISTORICAL in log\n{log_path.read_text(errors='ignore')}"

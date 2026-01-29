from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen


def _wait_ok(url: str, timeout_s: float = 10.0) -> None:
    t0 = time.time()
    while True:
        try:
            with urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        if time.time() - t0 > timeout_s:
            raise RuntimeError("timeout waiting for " + url)
        time.sleep(0.2)


def test_load_smoke_concurrency_ci(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    os.chdir(str(repo))

    host = "127.0.0.1"
    port = 8013
    base = f"http://{host}:{port}"
    log_path = tmp_path / "api_server.log"

    env = os.environ.copy()
    env["VSC_API_AUTH_ENABLED"] = "true"
    env["VSC_API_KEYS"] = "ci_key"
    env["VSC_API_KEY_SCOPES"] = "ci_key:read,verify,promote,sign,admin"

    p = subprocess.Popen(
        ["python3", "-m", "uvicorn", "api.app:app", "--host", host, "--port", str(port)],
        stdout=open(log_path, "wb"),
        stderr=subprocess.STDOUT,
        cwd=str(repo),
        env=env,
    )

    try:
        _wait_ok(f"{base}/v1/health", timeout_s=12.0)

        out = subprocess.check_output(
            [
                "python3",
                "-m",
                "scripts.load_api",
                "--base",
                base,
                "--api-key",
                "ci_key",
                "--concurrency",
                "80",
                "--requests",
                "800",
                "--out",
                str(tmp_path / "load_report.json"),
            ],
            cwd=str(repo),
        ).decode("utf-8", errors="ignore")

        assert '"schema": "load.report.v1"' in out
        assert '"ok_rate"' in out
        assert '"status_counts"' in out
        assert '"200"' in out
    finally:
        p.terminate()
        try:
            p.wait(timeout=3.0)
        except Exception:
            p.kill()

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen


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


def _http_get(url: str, headers=None) -> str:
    req = Request(url, method="GET")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urlopen(req, timeout=5.0) as r:
        return r.read().decode("utf-8", errors="ignore")


def test_metrics_endpoint_text(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    os.chdir(str(repo))

    host = "127.0.0.1"
    port = 8012
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

        hdr = {"Authorization": "Bearer ci_key"}
        _ = _http_get(f"{base}/v1/status", headers=hdr)
        txt = _http_get(f"{base}/v1/metrics", headers=None)

        assert "vsc_http_requests_total" in txt
    finally:
        p.terminate()
        try:
            p.wait(timeout=3.0)
        except Exception:
            p.kill()

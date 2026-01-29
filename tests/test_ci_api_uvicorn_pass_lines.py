from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen


def _http_get_json(url: str, headers: dict | None = None) -> dict:
    req = Request(url, method="GET", headers=headers or {})
    with urlopen(req, timeout=5.0) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    base_headers = {"Content-Type": "application/json"}
    if headers:
        for k, v in headers.items():
            base_headers[k] = v
    req = Request(url, data=data, method="POST", headers=base_headers)
    with urlopen(req, timeout=5.0) as r:
        return json.loads(r.read().decode("utf-8"))


def _wait_http_ok(url: str, timeout_s: float = 12.0) -> None:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        try:
            _http_get_json(url)
            return
        except Exception as e:
            last = e
            time.sleep(0.10)
    raise RuntimeError(f"server did not become ready: {url} last={last}")


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

    host = "127.0.0.1"
    port = 8001
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

    auth_headers = {"Authorization": "Bearer ci_key"}

    try:
        _wait_http_ok(f"{base}/v1/health", timeout_s=12.0)

        r0 = _http_post_json(f"{base}/v1/stream/oracle_001/step/1/promote?sign=0", {}, headers=auth_headers)
        assert bool(r0.get("ok", False)) is True

        r1 = _http_post_json(f"{base}/v1/verify/step-dir", {"step_dir": str(step_dir)}, headers=auth_headers)
        assert bool(r1.get("ok", False)) is True

        rs = _http_get_json(f"{base}/v1/status", headers=auth_headers)
        assert bool(rs.get("ok", False)) is True
        assert "api_version" in rs

        r2 = _http_post_json(
            f"{base}/v1/audit/verify-historical",
            {"stream_id": "oracle_001", "step_number": 1},
            headers=auth_headers,
        )
        assert isinstance(r2, dict)
        assert "api_version" in r2

    finally:
        p.terminate()
        try:
            p.wait(timeout=3.0)
        except Exception:
            p.kill()

    log_txt = log_path.read_text(errors="ignore")
    assert "PASS_API_STATUS" in log_txt

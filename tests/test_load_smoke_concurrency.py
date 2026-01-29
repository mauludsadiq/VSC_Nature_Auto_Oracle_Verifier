from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def _wait_for_health(base: str, timeout_s: float = 10.0) -> None:
    t0 = time.time()
    while True:
        try:
            out = subprocess.check_output(["curl", "-fsS", f"{base}/v1/health"], text=True, stderr=subprocess.DEVNULL)
            j = json.loads(out)
            if bool(j.get("ok", False)) is True:
                return
        except Exception:
            pass
        if time.time() - t0 > timeout_s:
            raise AssertionError("health did not become ok")
        time.sleep(0.1)


def test_load_smoke_concurrency(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    os.chdir(str(repo))

    host = "127.0.0.1"
    port = 8022
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
        _wait_for_health(base, timeout_s=12.0)

        out_report = repo / "out" / "load" / "load_report_ci.json"
        if out_report.exists():
            out_report.unlink()

        subprocess.run(
            [
                "sh",
                "scripts/run_load_api.sh",
            ],
            check=True,
            env=dict(
                os.environ,
                API_KEY="ci_key",
                HOST=host,
                PORT=str(port),
                CONCURRENCY="200",
                REQUESTS="2000",
                TIMEOUT_S="15",
                MIX="health,status,metrics",
                OUT=str(out_report),
            ),
        )

        assert out_report.exists()
        rep = json.loads(out_report.read_text(encoding="utf-8"))

        codes = rep.get("http_codes", {})
        assert isinstance(codes, dict)

        # CI assertion surface: we do not allow code "0" in the CI smoke.
        assert str(codes.get("0", 0)) in ("0", 0)

        # sanity: expect some 200s
        assert int(codes.get("200", 0)) > 0

    finally:
        p.terminate()
        try:
            p.wait(timeout=3.0)
        except Exception:
            p.kill()

from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _now_ms() -> int:
    return int(time.time() * 1000)


def _pct(xs: List[float], q: float) -> float:
    if not xs:
        return 0.0
    xs2 = sorted(xs)
    if q <= 0.0:
        return xs2[0]
    if q >= 1.0:
        return xs2[-1]
    idx = int(round((len(xs2) - 1) * q))
    return xs2[idx]


def _http(
    url: str,
    method: str,
    body: Optional[Dict[str, Any]],
    headers: Dict[str, str],
    timeout_s: float,
) -> Tuple[int, Optional[str]]:
    data: Optional[bytes] = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            code = int(resp.getcode())
            _ = resp.read()
            return code, None
    except urllib.error.HTTPError as e:
        code = int(getattr(e, "code", 0) or 0)
        return code, "HTTPError_%d" % code
    except urllib.error.URLError:
        return 0, "EXC_connect"
    except TimeoutError:
        return 0, "EXC_timeout"
    except Exception:
        return 0, "EXC_unknown"


def _headers(which: str, api_key: str) -> Dict[str, str]:
    h: Dict[str, str] = {}
    if which in ("status", "verify_step_dir") and api_key:
        h["Authorization"] = "Bearer %s" % api_key
    if which == "verify_step_dir":
        h["Content-Type"] = "application/json"
    return h


def _one(base: str, which: str, api_key: str, timeout_s: float, verify_step_dir: str) -> Tuple[int, Optional[str]]:
    base2 = base.rstrip("/")

    if which == "health":
        return _http(base2 + "/v1/health", "GET", None, _headers("health", api_key), timeout_s)

    if which == "status":
        return _http(base2 + "/v1/status", "GET", None, _headers("status", api_key), timeout_s)

    if which == "metrics":
        code, err = _http(base2 + "/v1/metrics", "GET", None, _headers("metrics", api_key), timeout_s)
        if code == 200 and err and err.startswith("HTTPError_"):
            return code, None
        return code, err

    if which == "verify_step_dir":
        if not verify_step_dir:
            return 0, "CFG_missing_VERIFY_STEP_DIR"
        body = {"step_dir": verify_step_dir}
        return _http(base2 + "/v1/verify/step-dir", "POST", body, _headers("verify_step_dir", api_key), timeout_s)

    return 0, "CFG_unknown_mix_item"


def main() -> int:
    host = os.getenv("HOST", "127.0.0.1").strip()
    port = os.getenv("PORT", "8000").strip()
    base = os.getenv("BASE", "").strip()
    if not base:
        base = "http://%s:%s" % (host, port)

    api_key = os.getenv("API_KEY", "").strip()
    concurrency = int(os.getenv("CONCURRENCY", "50"))
    requests = int(os.getenv("REQUESTS", "1000"))
    timeout_s = float(os.getenv("TIMEOUT_S", "10"))

    mix_raw = os.getenv("MIX", "health,status").strip()
    mix = [x.strip() for x in mix_raw.split(",") if x.strip()]
    if not mix:
        mix = ["health"]

    verify_step_dir = os.getenv("VERIFY_STEP_DIR", "").strip()

    out_path = os.getenv("OUT", "out/load/load_report.json").strip()
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    per = requests // max(concurrency, 1)
    rem = requests - per * max(concurrency, 1)

    lat_all: List[float] = []
    codes: Dict[str, int] = {}
    errors: Dict[str, int] = {}

    lock = threading.Lock()

    def worker(n: int) -> None:
        lat_local: List[float] = []
        codes_local: Dict[str, int] = {}
        errors_local: Dict[str, int] = {}
        for _ in range(n):
            which = random.choice(mix)
            t0 = time.time()
            code, err = _one(base, which, api_key, timeout_s, verify_step_dir)
            dt = time.time() - t0
            lat_local.append(dt)
            codes_local[str(code)] = codes_local.get(str(code), 0) + 1
            if err:
                errors_local[err] = errors_local.get(err, 0) + 1
        with lock:
            lat_all.extend(lat_local)
            for k, v in codes_local.items():
                codes[k] = codes.get(k, 0) + v
            for k, v in errors_local.items():
                errors[k] = errors.get(k, 0) + v

    threads: List[threading.Thread] = []
    t_start = time.time()
    for i in range(concurrency):
        n = per + (1 if i < rem else 0)
        th = threading.Thread(target=worker, args=(n,))
        th.daemon = True
        threads.append(th)
        th.start()

    for th in threads:
        th.join()

    elapsed = time.time() - t_start

    report: Dict[str, Any] = {
        "schema": "vsc.load_report.v1",
        "ts_ms": _now_ms(),
        "base": base,
        "concurrency": concurrency,
        "requests": requests,
        "elapsed_s": float(elapsed),
        "rps": float(requests) / float(elapsed) if elapsed > 0 else 0.0,
        "http_codes": dict(codes),
        "errors": dict(errors),
        "latency_s": {
            "min": min(lat_all) if lat_all else 0.0,
            "max": max(lat_all) if lat_all else 0.0,
            "mean": (sum(lat_all) / float(len(lat_all))) if lat_all else 0.0,
            "p50": _pct(lat_all, 0.50),
            "p90": _pct(lat_all, 0.90),
            "p95": _pct(lat_all, 0.95),
            "p99": _pct(lat_all, 0.99),
        },
    }

    out_p.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("WROTE %s" % str(out_p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

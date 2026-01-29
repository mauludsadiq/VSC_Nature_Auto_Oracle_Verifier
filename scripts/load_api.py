from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx


def _pct(xs: List[float], p: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    k = int(round((p / 100.0) * (len(ys) - 1)))
    k = max(0, min(len(ys) - 1, k))
    return float(ys[k])


async def _worker(
    client: httpx.AsyncClient,
    base: str,
    headers: Dict[str, str],
    n: int,
    lat_ms: List[float],
    status_counts: Dict[int, int],
):
    for _ in range(n):
        t0 = time.time()
        try:
            r = await client.get(f"{base}/v1/status", headers=headers, timeout=5.0)
            code = int(r.status_code)
        except Exception:
            code = 0
        dt = (time.time() - t0) * 1000.0
        lat_ms.append(dt)
        status_counts[code] = int(status_counts.get(code, 0)) + 1


async def run(base: str, api_key: str, concurrency: int, requests_total: int) -> Dict[str, Any]:
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    per = requests_total // concurrency
    rem = requests_total - (per * concurrency)

    lat_ms: List[float] = []
    status_counts: Dict[int, int] = {}

    t0 = time.time()
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(concurrency):
            n = per + (1 if i < rem else 0)
            tasks.append(asyncio.create_task(_worker(client, base, headers, n, lat_ms, status_counts)))
        await asyncio.gather(*tasks)
    dt = time.time() - t0

    ok = int(status_counts.get(200, 0))
    total = sum(status_counts.values()) if status_counts else 0
    ok_rate = (ok / float(total)) if total else 0.0
    rps = (total / dt) if dt > 0 else 0.0

    return {
        "schema": "load.report.v1",
        "base": base,
        "concurrency": int(concurrency),
        "requests": int(requests_total),
        "ok_rate": float(ok_rate),
        "p50_ms": _pct(lat_ms, 50.0),
        "p95_ms": _pct(lat_ms, 95.0),
        "p99_ms": _pct(lat_ms, 99.0),
        "rps": float(rps),
        "status_counts": {str(k): int(v) for k, v in sorted(status_counts.items(), key=lambda kv: kv[0])},
    }


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--api-key", default="")
    ap.add_argument("--concurrency", type=int, default=1000)
    ap.add_argument("--requests", type=int, default=20000)
    ap.add_argument("--out", default="out/load/load_report.json")
    args = ap.parse_args(argv[1:])

    rep = asyncio.run(run(args.base, args.api_key, int(args.concurrency), int(args.requests)))

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(rep, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))

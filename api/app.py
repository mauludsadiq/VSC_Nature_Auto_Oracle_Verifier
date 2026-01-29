from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse

from api.settings import APISettings
from api.metrics import MetricsMiddleware, metrics_response
from api.auth import require_scopes

import api.service as service


settings = APISettings.from_env()

app = FastAPI(
    title="VSC Nature Auto Oracle Verifier API",
    version="v1",
)


@app.middleware("http")
async def size_limit_middleware(request: Request, call_next):
    body = await request.body()
    if len(body) > settings.max_body_bytes:
        return JSONResponse(status_code=413, content={"schema": "api.error.v1", "error": "BODY_TOO_LARGE"})
    request._body = body
    return await call_next(request)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    return await MetricsMiddleware()(request, call_next)


@app.get("/v1/health")
def health():
    return service._with_api_meta(
        {
            "schema": "api.health.v1",
            "ok": True,
            "host": settings.host,
            "port": settings.port,
        }
    )


@app.get("/v1/status", dependencies=[Depends(require_scopes(["read"]))])
def status():
    return service.api_status()


@app.get("/v1/metrics")
def metrics():
    return metrics_response()


@app.post("/v1/verify/step-dir", dependencies=[Depends(require_scopes(["verify"]))])
async def verify_step_dir(payload: dict):
    step_dir_raw = payload.get("step_dir", "")
    if not isinstance(step_dir_raw, str) or not step_dir_raw:
        raise HTTPException(status_code=400, detail="BAD_REQUEST missing step_dir")

    step_dir = Path(step_dir_raw)
    if not step_dir.exists():
        raise HTTPException(status_code=404, detail="NOT_FOUND step_dir does not exist")

    try:
        out = service.replay_verify_step_dir(step_dir)
    except Exception as e:
        msg = f"INTERNAL_ERROR {type(e).__name__} {str(e)}"
        print(f"FAIL_API_VERIFY_STEP step_dir={step_dir_raw}")
        return JSONResponse(status_code=500, content={"schema": "api.error.v1", "error": msg})

    ok = bool(out.get("ok", False))
    if ok:
        print(f"PASS_API_VERIFY_STEP {step_dir_raw}")
    else:
        print(f"FAIL_API_VERIFY_STEP step_dir={step_dir_raw}")

    return out


@app.post("/v1/audit/verify-historical", dependencies=[Depends(require_scopes(["verify"]))])
def verify_historical(req: dict):
    try:
        stream_id = str(req.get("stream_id") or "")
        step_number = int(req.get("step_number") or 0)
        out = service.audit_verify_historical(stream_id, step_number)
        if isinstance(out, dict) and ("api_version" not in out):
            out = service._with_api_meta(out)
        return out
    except Exception as e:
        return service._with_api_meta(
            {
                "schema": "api.audit_verify_historical.v1",
                "stream_id": str(req.get("stream_id") or ""),
                "step_number": int(req.get("step_number") or 0),
                "ok": False,
                "reason": "EXC_" + e.__class__.__name__,
                "merkle_root": "",
                "root_hash_txt": "",
                "leaf_hashes": [],
                "same_hash": False,
                "storage": {
                    "backend": "filesystem",
                    "historical_root": str(settings.historical_root),
                    "object_prefix": "",
                    "fetched_ok": False,
                },
                "signature_valid": False,
                "ts_ms": 0,
            }
        )


@app.post("/v1/stream/{stream_id}/step/{step_number}/promote", dependencies=[Depends(require_scopes(["promote"]))])
def promote(stream_id: str, step_number: int, sign: int = 0):
    out = service.promote_step(stream_id=str(stream_id), step_number=int(step_number), sign=bool(int(sign)))
    return out


@app.post("/v1/stream/{stream_id}/step/{step_number}/sign", dependencies=[Depends(require_scopes(["sign"]))])
def sign(stream_id: str, step_number: int):
    return service.sign_step(stream_id=str(stream_id), step_number=int(step_number))

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from api.models import VerifyHistoricalRequest, VerifyHistoricalResponse

from api.service import replay_verify_step_dir, audit_verify_historical
from api.settings import APISettings

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


@app.get("/v1/health")
def health():
    return {
        "schema": "api.health.v1",
        "ok": True,
        "host": settings.host,
        "port": settings.port,
    }


@app.post("/v1/verify/step-dir")
async def verify_step_dir(payload: dict):
    step_dir_raw = payload.get("step_dir", "")
    if not isinstance(step_dir_raw, str) or not step_dir_raw:
        raise HTTPException(status_code=400, detail="BAD_REQUEST missing step_dir")

    step_dir = Path(step_dir_raw)
    if not step_dir.exists():
        raise HTTPException(status_code=404, detail="NOT_FOUND step_dir does not exist")

    try:
        out = replay_verify_step_dir(step_dir)
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
@app.post("/v1/audit/verify-historical", response_model=VerifyHistoricalResponse)
async def verify_historical(req: VerifyHistoricalRequest):
    out = audit_verify_historical(req.stream_id, req.step_number)

    if bool(out.get("ok", False)):
        print(f'PASS_API_VERIFY_HISTORICAL stream_id={req.stream_id} step={int(req.step_number)}')
    else:
        print(f'FAIL_API_VERIFY_HISTORICAL stream_id={req.stream_id} step={int(req.step_number)} reason={out.get("reason","")}')

    return out

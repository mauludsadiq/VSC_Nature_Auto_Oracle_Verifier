from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

import api.service as service
from api.models import (
    APIStatusResponse,
    PromoteStepResponse,
    SignStepResponse,
    StreamFileResponse,
    StreamManifestResponse,
    VerifyHistoricalRequest,
    VerifyHistoricalResponse,
    VerifyRedPacketResponse,
)
from api.settings import APISettings

from api.auth import load_auth_config, authenticate_request, require_scopes

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


AUTH_CFG = load_auth_config()

@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    try:
        key, scopes, err, code = authenticate_request(
            path=request.url.path,
            authorization=request.headers.get("authorization", ""),
            cfg=AUTH_CFG,
        )
        if err is not None:
            return JSONResponse(status_code=code, content=err)
        request.state.api_key = key
        request.state.api_scopes = scopes
        return await call_next(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"schema": "api.auth_error.v1", "ok": False, "reason": "AUTH_ERROR", "detail": str(e)})

@app.get("/v1/health")
def health() -> Dict[str, Any]:
    out = {
        "schema": "api.health.v1",
        "ok": True,
        "host": settings.host,
        "port": settings.port,
    }
    if "api_version" not in out:
        out = service._with_api_meta(out)
    return out

@app.get("/v1/status", response_model=APIStatusResponse)
def status() -> Dict[str, Any]:
    out = service.api_status()
    if isinstance(out, dict) and ("api_version" not in out):
        out = service._with_api_meta(out)
    return out

@app.post("/v1/verify/red-packet", response_model=VerifyRedPacketResponse)
def verify_red_packet(payload: Dict[str, Any]) -> Dict[str, Any]:
    red_packet = payload.get("red_packet", None)
    if not isinstance(red_packet, dict):
        raise HTTPException(status_code=400, detail="BAD_REQUEST missing red_packet")
    out = service.verify_red_packet(red_packet)
    if isinstance(out, dict) and ("api_version" not in out):
        out = service._with_api_meta(out)
    return out

@app.post("/v1/verify/step-dir")
async def verify_step_dir(payload: Dict[str, Any]) -> Dict[str, Any]:
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

@app.post("/v1/audit/verify-historical", response_model=VerifyHistoricalResponse)
def verify_historical(request: Request, req: VerifyHistoricalRequest) -> Dict[str, Any]:
    scopes = list(getattr(request.state, 'api_scopes', []) or [])
    if not require_scopes(scopes, ['verify']):
        return JSONResponse(status_code=403, content={'schema': 'api.auth_error.v1', 'ok': False, 'reason': 'INSUFFICIENT_SCOPE'})
    out = service.audit_verify_historical(str(req.stream_id), int(req.step_number))
    if isinstance(out, dict) and ("api_version" not in out):
        out = service._with_api_meta(out)
    return out

@app.post("/v1/stream/{stream_id}/step/{step_number}/promote", response_model=PromoteStepResponse)
def promote_step(
    stream_id: str,
    step_number: int,
    sign: int = Query(0),
) -> Dict[str, Any]:
    out = service.promote_step(stream_id=str(stream_id), step_number=int(step_number), sign=int(sign))
    if isinstance(out, dict) and ("api_version" not in out):
        out = service._with_api_meta(out)
    return out

@app.post("/v1/stream/{stream_id}/step/{step_number}/sign", response_model=SignStepResponse)
def sign_step(
    stream_id: str,
    step_number: int,
) -> Dict[str, Any]:
    out = service.sign_step(stream_id=str(stream_id), step_number=int(step_number))
    if isinstance(out, dict) and ("api_version" not in out):
        out = service._with_api_meta(out)
    return out

@app.get("/v1/stream/{stream_id}", response_model=StreamManifestResponse)
def stream_manifest(stream_id: str) -> Dict[str, Any]:
    out = service.stream_get_manifest_or_file(stream_id=str(stream_id), rel_path=None)
    if isinstance(out, dict) and ("api_version" not in out):
        out = service._with_api_meta(out)
    return out

@app.get("/v1/stream/{stream_id}/file/{rel_path:path}", response_model=StreamFileResponse)
def stream_file(stream_id: str, rel_path: str) -> Dict[str, Any]:
    out = service.stream_get_manifest_or_file(stream_id=str(stream_id), rel_path=str(rel_path))
    if isinstance(out, dict) and ("api_version" not in out):
        out = service._with_api_meta(out)
    return out

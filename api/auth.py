from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, Request, status


AUTH_ERROR_SCHEMA = "api.auth_error.v1"


def _parse_keys_csv(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _parse_scopes_map(s: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    raw = (s or "").strip()
    if not raw:
        return out
    for mapping in raw.split(";"):
        mapping = mapping.strip()
        if not mapping or ":" not in mapping:
            continue
        k, scopes = mapping.split(":", 1)
        k = k.strip()
        if not k:
            continue
        out[k] = [x.strip() for x in scopes.split(",") if x.strip()]
    return out


def _error(reason: str, detail: str = "") -> Dict[str, object]:
    d: Dict[str, object] = {"schema": AUTH_ERROR_SCHEMA, "ok": False, "reason": reason}
    if detail:
        d["detail"] = detail
    return d


def _is_public_path(path: str) -> bool:
    publics = (
        "/v1/health",
        "/v1/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
    )
    for p in publics:
        if path == p or path.startswith(p + "/"):
            return True
    return False


def _auth_enabled() -> bool:
    return (os.getenv("VSC_API_AUTH_ENABLED", "false") or "false").strip().lower() in ("1", "true", "yes", "on")


def authenticate_request(request: Request) -> Optional[Tuple[str, List[str]]]:
    if not _auth_enabled():
        return None
    if _is_public_path(request.url.path):
        return None

    keys = _parse_keys_csv(os.getenv("VSC_API_KEYS", "") or "")
    if not keys:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_error("NO_KEYS_CONFIGURED"))

    scopes_map = _parse_scopes_map(os.getenv("VSC_API_KEY_SCOPES", "") or "")
    if not scopes_map:
        for k in keys:
            scopes_map[k] = ["read", "verify", "promote", "sign", "admin"]

    auth = request.headers.get("authorization", "") or request.headers.get("Authorization", "") or ""
    auth = auth.strip()
    if not auth:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_error("MISSING_AUTH"))

    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_error("BAD_SCHEME"))

    key = parts[1].strip()
    if key not in keys:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_error("BAD_KEY"))

    return key, scopes_map.get(key, ["read"])


def require_scopes(required: List[str]):
    def _dep(request: Request) -> None:
        res = authenticate_request(request)
        if res is None:
            return
        _, scopes = res
        if "admin" in scopes:
            return
        for r in required:
            if r not in scopes:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_error("INSUFFICIENT_SCOPE"))
        return

    return _dep

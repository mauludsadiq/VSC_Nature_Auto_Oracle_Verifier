from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

AUTH_ERROR_SCHEMA = "api.auth_error.v1"

DEFAULT_ALL_SCOPES = ["read", "verify", "promote", "sign", "admin"]

PUBLIC_PATHS = {
    "/v1/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}

@dataclass(frozen=True)
class AuthConfig:
    enabled: bool
    keys: Set[str]
    key_scopes: Dict[str, List[str]]

def _parse_bool(s: str) -> bool:
    return s.strip().lower() in {"1", "true", "yes", "on"}

def load_auth_config() -> AuthConfig:
    enabled = _parse_bool(os.getenv("VSC_API_AUTH_ENABLED", "false"))
    keys_raw = os.getenv("VSC_API_KEYS", "").strip()
    keys = {k.strip() for k in keys_raw.split(",") if k.strip()}

    scopes_raw = os.getenv("VSC_API_KEY_SCOPES", "").strip()
    key_scopes: Dict[str, List[str]] = {}

    if scopes_raw:
        for mapping in scopes_raw.split(";"):
            mapping = mapping.strip()
            if not mapping:
                continue
            if ":" not in mapping:
                continue
            k, scopes = mapping.split(":", 1)
            k = k.strip()
            if not k:
                continue
            sc = [s.strip() for s in scopes.split(",") if s.strip()]
            key_scopes[k] = sc

    if keys and not key_scopes:
        for k in keys:
            key_scopes[k] = list(DEFAULT_ALL_SCOPES)

    return AuthConfig(enabled=enabled, keys=keys, key_scopes=key_scopes)

def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/docs/"):
        return True
    return False

def error_body(reason: str, detail: str = "") -> dict:
    d = {"schema": AUTH_ERROR_SCHEMA, "ok": False, "reason": reason}
    if detail:
        d["detail"] = detail
    return d

def parse_bearer_token(auth_header: str) -> Optional[str]:
    if not auth_header:
        return None
    parts = auth_header.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, token = parts[0].strip(), parts[1].strip()
    if scheme.lower() != "bearer":
        return None
    return token if token else None

def authenticate_request(path: str, authorization: str, cfg: AuthConfig) -> Tuple[Optional[str], List[str], Optional[dict], int]:
    if (not cfg.enabled) or is_public_path(path):
        return None, [], None, 200

    token = parse_bearer_token(authorization or "")
    if token is None:
        return None, [], error_body("MISSING_AUTH"), 401

    if token not in cfg.keys:
        return None, [], error_body("BAD_KEY"), 401

    scopes = cfg.key_scopes.get(token, ["read"])
    return token, scopes, None, 200

def require_scopes(user_scopes: List[str], required: List[str]) -> bool:
    if "admin" in user_scopes:
        return True
    for r in required:
        if r not in user_scopes:
            return False
    return True

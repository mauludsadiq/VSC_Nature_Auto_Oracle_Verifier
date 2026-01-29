from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(k: str, default: bool) -> bool:
    v = (os.getenv(k, "") or "").strip().lower()
    if not v:
        return bool(default)
    return v in ("1", "true", "yes", "y", "on")


def _env_int(k: str, default: int) -> int:
    v = (os.getenv(k, "") or "").strip()
    if not v:
        return int(default)
    try:
        return int(v)
    except Exception:
        return int(default)


def _env_str(k: str, default: str) -> str:
    v = os.getenv(k, "")
    return (v if v is not None else default).strip() or default


@dataclass(frozen=True)
class APISettings:
    host: str
    port: int
    max_body_bytes: int

    allow_schema: str

    historical_root: Path
    tmp_root: Path

    notary_on: bool
    signature_scheme: str
    ledger_pubkey_path: str
    ledger_privkey_path: str

    storage_backend: str
    s3_bucket: str
    s3_prefix: str
    s3_region: str
    s3_endpoint_url: str

    api_auth_enabled: bool
    api_keys_csv: str
    api_key_scopes: str

    @staticmethod
    def from_env() -> "APISettings":
        host = _env_str("VSC_API_HOST", "127.0.0.1")
        port = _env_int("VSC_API_PORT", 8000)
        max_body_bytes = _env_int("VSC_MAX_BODY_BYTES", 2_000_000)

        allow_schema = _env_str("VSC_ALLOW_SCHEMA", "oracle_gamble.red_packet.v1")

        historical_root = Path(_env_str("VSC_HISTORICAL_ROOT", "out/historical"))
        tmp_root = Path(_env_str("VSC_TMP_ROOT", "out/tmp"))

        notary_on = _env_bool("VSC_NOTARY_ENABLED", False)
        signature_scheme = _env_str("VSC_SIGNATURE_SCHEME", "")
        ledger_pubkey_path = _env_str("VSC_LEDGER_PUBKEY_PATH", "")
        ledger_privkey_path = _env_str("VSC_LEDGER_PRIVKEY_PATH", "")

        storage_backend = _env_str("VSC_STORAGE_BACKEND", "filesystem").lower()
        s3_bucket = _env_str("VSC_S3_BUCKET", "")
        s3_prefix = _env_str("VSC_S3_PREFIX", "")
        s3_region = _env_str("VSC_S3_REGION", "")
        s3_endpoint_url = _env_str("VSC_S3_ENDPOINT_URL", "")

        api_auth_enabled = _env_bool("VSC_API_AUTH_ENABLED", False)
        api_keys_csv = _env_str("VSC_API_KEYS", "")
        api_key_scopes = _env_str("VSC_API_KEY_SCOPES", "")

        return APISettings(
            host=host,
            port=port,
            max_body_bytes=max_body_bytes,
            allow_schema=allow_schema,
            historical_root=historical_root,
            tmp_root=tmp_root,
            notary_on=notary_on,
            signature_scheme=signature_scheme,
            ledger_pubkey_path=ledger_pubkey_path,
            ledger_privkey_path=ledger_privkey_path,
            storage_backend=storage_backend,
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            s3_region=s3_region,
            s3_endpoint_url=s3_endpoint_url,
            api_auth_enabled=api_auth_enabled,
            api_keys_csv=api_keys_csv,
            api_key_scopes=api_key_scopes,
        )

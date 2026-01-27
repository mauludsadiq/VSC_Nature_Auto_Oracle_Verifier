from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class APISettings:
    host: str
    port: int
    out_root: Path
    stream_root: Path
    historical_root: Path
    max_body_bytes: int
    allow_schema: str
    signature_scheme: str
    ledger_pubkey_path: Path
    ledger_privkey_path: Path

    @staticmethod
    def from_env() -> "APISettings":
        repo_root = Path(__file__).resolve().parents[1]

        out_root = Path(os.getenv("VSC_API_OUT_ROOT", str(repo_root / "out" / "api_runs")))
        stream_root = Path(os.getenv("VSC_STREAM_ROOT", str(repo_root / "out" / "stream")))
        historical_root = Path(os.getenv("VSC_HISTORICAL_ROOT", str(repo_root / "out" / "historical")))

        signature_scheme = os.getenv("VSC_SIGNATURE_SCHEME", "")
        ledger_pubkey_path = Path(os.getenv("VSC_LEDGER_PUBKEY_PATH", ""))
        ledger_privkey_path = Path(os.getenv("VSC_LEDGER_PRIVKEY_PATH", ""))

        return APISettings(
            host=os.getenv("VSC_API_HOST", "127.0.0.1"),
            port=int(os.getenv("VSC_API_PORT", "8000")),
            out_root=out_root,
            stream_root=stream_root,
            historical_root=historical_root,
            max_body_bytes=int(os.getenv("VSC_API_MAX_BODY_BYTES", str(256 * 1024))),
            allow_schema=os.getenv("VSC_API_ALLOW_SCHEMA", "oracle_gamble.red_packet.v1"),
            signature_scheme=signature_scheme,
            ledger_pubkey_path=ledger_pubkey_path,
            ledger_privkey_path=ledger_privkey_path,
        )

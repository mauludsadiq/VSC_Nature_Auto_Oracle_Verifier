from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class APISettings:
    host: str
    port: int
    out_root: Path
    max_body_bytes: int
    allow_schema: str

    @staticmethod
    def from_env() -> "APISettings":
        repo_root = Path(__file__).resolve().parents[1]
        out_root = os.getenv("VSC_API_OUT_ROOT", str(repo_root / "out" / "api_runs"))

        return APISettings(
            host=os.getenv("VSC_API_HOST", "127.0.0.1"),
            port=int(os.getenv("VSC_API_PORT", "8000")),
            out_root=Path(out_root),
            max_body_bytes=int(os.getenv("VSC_API_MAX_BODY_BYTES", str(256 * 1024))),
            allow_schema=os.getenv("VSC_API_ALLOW_SCHEMA", "oracle_gamble.red_packet.v1"),
        )

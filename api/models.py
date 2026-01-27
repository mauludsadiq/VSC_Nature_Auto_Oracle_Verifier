from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class _Base(BaseModel):
    class Config:
        allow_population_by_field_name = True
        extra = "allow"


class HealthResponse(_Base):
    schema_: str = Field("api.health.v1", alias="schema")
    ok: bool = True
    host: Optional[str] = None


class VerifyRedPacketRequest(_Base):
    red_packet: Dict[str, Any]


class VerifyRedPacketResponse(_Base):
    schema_: str = Field("api.verify_red_packet.response.v1", alias="schema")
    ok: bool
    reason: str
    step_counter: Optional[int] = None
    merkle_root: Optional[str] = None
    leaf_hashes: Optional[List[str]] = None
    leaf_verdicts: Optional[Dict[str, str]] = None


class VerifyStepDirRequest(_Base):
    step_dir: str


class VerifyStepDirResponse(_Base):
    schema_: str = Field("api.verify_step_dir.response.v1", alias="schema")
    ok: bool
    reason: str
    step_dir: str
    merkle_root: str
    leaf_hashes: List[str]
class VerifyHistoricalRequest(BaseModel):
    stream_id: str
    step_number: int


class VerifyHistoricalResponse(BaseModel):
    schema: str
    stream_id: str
    step_number: int

    ok: bool
    reason: str

    merkle_root: str
    root_hash_txt: str
    leaf_hashes: list[str]

    same_hash: bool

    storage: dict
    signature_valid: bool
    ts_ms: int



class VerifyRedPacketResponse(BaseModel):
    schema: str = "api.verify_red_packet.v1"
    ok: bool
    reason: str
    allow_schema: str
    packet_schema: str
    step_number: int
    stream_id: str
    ts_ms: int


class APIStatusResponse(BaseModel):
    schema: str = "api.status.v1"
    ok: bool
    host: str
    port: int
    allow_schema: str
    historical_root: str
    signature_scheme: str
    ledger_pubkey_path: str
    ts_ms: int


class StreamManifestEntry(BaseModel):
    name: str
    bytes: int
    sha256: str


class StreamManifestResponse(BaseModel):
    schema: str = "api.stream_manifest.v1"
    stream_id: str
    step_number: int
    ok: bool
    reason: str
    step_dir: str
    files: List[StreamManifestEntry]
    ts_ms: int


class StreamFileResponse(BaseModel):
    schema: str = "api.stream_file.v1"
    stream_id: str
    step_number: int
    ok: bool
    reason: str
    step_dir: str
    file: str
    bytes: int
    sha256: str
    text: str
    ts_ms: int


class PromoteStepResponse(BaseModel):
    schema: str = "api.promote_step.v1"
    stream_id: str
    step_number: int
    ok: bool
    reason: str
    src_step_dir: str
    dst_step_dir: str
    signed: bool
    signature_scheme: str
    ts_ms: int

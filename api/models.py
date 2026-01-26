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

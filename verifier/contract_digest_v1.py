from __future__ import annotations

import hashlib
from pathlib import Path


CONTRACT_FILES = [
    "swarm_verifier/byzantine_resistance_v1.py",
    "swarm_verifier/hash_chain_v1.py",
    "swarm_verifier/oracle_gamble_red_packet_v1.py",
    "api/service.py",
    "api/models.py",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def verifier_contract_digest_v1(root: Path) -> str:
    parts = []
    for rel in CONTRACT_FILES:
        p = root / rel
        if not p.exists():
            parts.append(f"{rel}:MISSING")
        else:
            parts.append(f"{rel}:{sha256_file(p)}")
    joined = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()

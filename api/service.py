from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def replay_verify_step_dir(step_dir: Path) -> Dict[str, Any]:
    from scripts.verify_bundle import verify_step_dir as _verify_step_dir

    out = _verify_step_dir(str(step_dir))

    ok = False
    reason = "NONE"
    merkle_root = ""
    leaf_hashes: List[str] = []
    step_dir_s = str(step_dir)

    if isinstance(out, dict):
        ok = bool(out.get("ok", False))
        reason = str(out.get("reason") or "NONE")
        merkle_root = str(out.get("merkle_root") or "")
        leaf_hashes_raw = out.get("leaf_hashes", [])
        if isinstance(leaf_hashes_raw, list):
            leaf_hashes = [str(x) for x in leaf_hashes_raw]
        step_dir_s = str(out.get("step_dir") or step_dir_s)

    elif isinstance(out, tuple):
        ok = bool(out[0]) if len(out) >= 1 else False
        reason = str(out[1] or "NONE") if len(out) >= 2 else "NONE"
        merkle_root = str(out[2] or "") if len(out) >= 3 else ""
        leaf_hashes = []

    root_hash_txt = ""
    try:
        root_hash_txt = _read_text(step_dir / "root_hash.txt")
    except Exception:
        root_hash_txt = ""

    if not merkle_root:
        try:
            b = _read_json(step_dir / "bundle.json")
            merkle_root = str(b.get("merkle_root") or "")
        except Exception:
            merkle_root = ""

    if not merkle_root:
        merkle_root = root_hash_txt

    signature_valid = False
    scheme = getattr(settings, "signature_scheme", "") or ""
    pk_path_s = getattr(settings, "ledger_pubkey_path", "") or ""

    if scheme == "ed25519.v1" and pk_path_s:
        try:
            pk_hex = _read_text(Path(pk_path_s))
            sig_path = step_dir / "root.sig"
            if sig_path.exists():
                sig_hex = _read_text(sig_path)
                msg = (root_hash_txt or merkle_root).strip().encode("utf-8")
                signature_valid = _verify_signature_ed25519_v1(msg, sig_hex, pk_hex)
        except Exception:
            signature_valid = False

    if signature_valid:
        print(f"PASS_API_VERIFY_HISTORICAL_SIGNATURE stream_id={stream_id} step={step_number} scheme={scheme}")



    return {
        "schema": "api.replay_verify_step.v1",
        "step_dir": step_dir_s,
        "ok": bool(ok),
        "reason": str(reason or "NONE"),
        "merkle_root": str(merkle_root or ""),
        "leaf_hashes": leaf_hashes,
        "root_hash_txt": str(root_hash_txt or ""),
        "ts_ms": int(time.time() * 1000),
    }

def _historical_step_dir(stream_id: str, step_number: int) -> Path:
    import os

    root = Path(os.getenv("VSC_HISTORICAL_ROOT", "out/historical"))
    step_name = f"step_{int(step_number):06d}"
    return root / str(stream_id) / step_name


def audit_verify_historical(stream_id: str, step_number: int) -> dict:
    from api.settings import APISettings

    settings = APISettings.from_env()

    step_dir = settings.historical_root / str(stream_id) / f"step_{int(step_number):06d}"
    object_prefix = f"{stream_id}/step_{int(step_number):06d}/"

    if not step_dir.exists():
        return {
            "schema": "api.audit_verify_historical.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": False,
            "reason": "MISSING_STEP_DIR",
            "merkle_root": "",
            "root_hash_txt": "",
            "leaf_hashes": [],
            "same_hash": False,
            "storage": {
                "backend": "filesystem",
                "historical_root": str(settings.historical_root),
                "object_prefix": object_prefix,
                "fetched_ok": False,
            },
            "signature_valid": signature_valid,
            "ts_ms": int(time.time() * 1000),
        }

    out = _verify_step_dir_disk(step_dir)

    ok = bool(out.get("ok", False))
    reason = str(out.get("reason", ""))
    merkle_root = str(out.get("merkle_root", ""))
    leaf_hashes = list(out.get("leaf_hashes", []))

    root_hash_txt = ""
    try:
        root_hash_txt = _read_text(step_dir / "root_hash.txt").strip()
    except Exception:
        root_hash_txt = ""

    same_hash = False
    if merkle_root and root_hash_txt:
        same_hash = (merkle_root.strip() == root_hash_txt.strip())

    sig = _verify_root_signature(
        step_dir=step_dir,
        root_hash_txt=root_hash_txt,
        pubkey_path=settings.ledger_pubkey_path,
        scheme=settings.signature_scheme,
    )

    resp = {
        "schema": "api.audit_verify_historical.v1",
        "stream_id": str(stream_id),
        "step_number": int(step_number),
        "ok": bool(ok),
        "reason": str(reason),
        "merkle_root": str(merkle_root),
        "root_hash_txt": str(root_hash_txt),
        "leaf_hashes": list(leaf_hashes),
        "same_hash": bool(same_hash),
        "storage": {
            "backend": "filesystem",
            "historical_root": str(settings.historical_root),
            "object_prefix": object_prefix,
            "fetched_ok": True,
        },
        "signature_valid": bool(sig["signature_valid"]),
        "ts_ms": int(time.time() * 1000),
    }

    if ok:
        print(f"PASS_API_VERIFY_HISTORICAL stream_id={stream_id} step={int(step_number)}")
    if sig["signature_valid"]:
        print(f"PASS_API_VERIFY_HISTORICAL_SIGNATURE stream_id={stream_id} step={int(step_number)} scheme={settings.signature_scheme}")

    return resp

def _verify_step_dir_disk(step_dir: Path) -> dict:
    from scripts.verify_bundle import verify_step_dir as _verify_step_dir

    out = _verify_step_dir(str(step_dir))
    if isinstance(out, dict):
        return out
    return {"ok": False, "reason": "VERIFY_STEP_DIR_BAD_RETURN", "merkle_root": "", "leaf_hashes": [], "step_dir": str(step_dir)}

def _verify_root_signature(step_dir: Path, root_hash_txt: str, pubkey_path: Path, scheme: str) -> dict:
    pubkey_path = Path(pubkey_path)
    sig_path = step_dir / "root.sig"
    if not sig_path.exists():
        return {"signature_valid": signature_valid, "reason": "NO_SIGNATURE"}

    if not root_hash_txt:
        return {"signature_valid": signature_valid, "reason": "NO_ROOT_HASH"}

    sig_raw = ""
    try:
        sig_raw = _read_text(sig_path).strip()
    except Exception:
        return {"signature_valid": signature_valid, "reason": "SIG_READ_FAIL"}

    sig_bytes = b""
    try:
        sig_bytes = bytes.fromhex(sig_raw)
    except Exception:
        return {"signature_valid": signature_valid, "reason": "SIG_PARSE_FAIL"}

    if not pubkey_path.exists():
        return {"signature_valid": signature_valid, "reason": "NO_PUBKEY"}

    pub_bytes = b""
    pub_text = ""
    try:
        pub_text = _read_text(pubkey_path).strip()
    except Exception:
        pub_text = ""

    msg = root_hash_txt.strip().encode("utf-8")

    if scheme != "ed25519.v1":
        return {"signature_valid": signature_valid, "reason": "UNSUPPORTED_SCHEME"}

    # Try cryptography (preferred)
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives import serialization

        if pub_text.startswith("-----BEGIN"):
            pk = serialization.load_pem_public_key(pub_text.encode("utf-8"))
            pk.verify(sig_bytes, msg)
            return {"signature_valid": True, "reason": "OK"}
        else:
            pub_bytes = bytes.fromhex(pub_text)
            pk = Ed25519PublicKey.from_public_bytes(pub_bytes)
            pk.verify(sig_bytes, msg)
            return {"signature_valid": True, "reason": "OK"}
    except Exception:
        pass

    # Try PyNaCl fallback
    try:
        from nacl.signing import VerifyKey

        if pub_text.startswith("-----BEGIN"):
            return {"signature_valid": signature_valid, "reason": "PEM_UNSUPPORTED_NO_CRYPTO"}
        pub_bytes = bytes.fromhex(pub_text)
        vk = VerifyKey(pub_bytes)
        vk.verify(msg, sig_bytes)
        return {"signature_valid": True, "reason": "OK"}
    except Exception:
        return {"signature_valid": signature_valid, "reason": "VERIFY_FAIL"}



def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _verify_signature_ed25519_v1(msg: bytes, sig_hex: str, pubkey_hex: str) -> bool:
    if not sig_hex or not pubkey_hex:
        return False
    try:
        sig = bytes.fromhex(sig_hex.strip())
        pk = bytes.fromhex(pubkey_hex.strip())
    except Exception:
        return False

    # ed25519 signatures are 64 bytes
    if len(sig) != 64:
        return False
    if len(pk) != 32:
        return False

    # preferred: cryptography
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pub = Ed25519PublicKey.from_public_bytes(pk)
        pub.verify(sig, msg)
        return True
    except Exception:
        pass

    # fallback: PyNaCl
    try:
        from nacl.signing import VerifyKey

        vk = VerifyKey(pk)
        vk.verify(msg, sig)
        return True
    except Exception:
        return False

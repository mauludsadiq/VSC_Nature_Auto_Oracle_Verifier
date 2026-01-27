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
            "signature_valid": False,
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
    signature_valid = False
    pubkey_path = Path(pubkey_path)
    sig_path = step_dir / "root.sig"
    if not sig_path.exists():
        return {"signature_valid": False, "reason": "NO_SIGNATURE"}

    if not root_hash_txt:
        return {"signature_valid": False, "reason": "NO_ROOT_HASH"}

    sig_raw = ""
    try:
        sig_raw = _read_text(sig_path).strip()
    except Exception:
        return {"signature_valid": False, "reason": "SIG_READ_FAIL"}

    sig_bytes = b""
    try:
        sig_bytes = bytes.fromhex(sig_raw)
    except Exception:
        return {"signature_valid": False, "reason": "SIG_PARSE_FAIL"}

    if not pubkey_path.exists():
        return {"signature_valid": False, "reason": "NO_PUBKEY"}

    pub_bytes = b""
    pub_text = ""
    try:
        pub_text = _read_text(pubkey_path).strip()
    except Exception:
        pub_text = ""

    msg = root_hash_txt.strip().encode("utf-8")

    if scheme != "ed25519.v1":
        return {"signature_valid": False, "reason": "UNSUPPORTED_SCHEME"}

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
            return {"signature_valid": False, "reason": "PEM_UNSUPPORTED_NO_CRYPTO"}
        pub_bytes = bytes.fromhex(pub_text)
        vk = VerifyKey(pub_bytes)
        vk.verify(msg, sig_bytes)
        return {"signature_valid": True, "reason": "OK"}
    except Exception:
        return {"signature_valid": False, "reason": "VERIFY_FAIL"}



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


import hashlib
import time
from typing import Tuple

from api.settings import APISettings

settings = APISettings.from_env()


def _ts_ms() -> int:
    return int(time.time() * 1000)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _safe_file_name(raw: str) -> str:
    s = (raw or "").strip()
    if s == "":
        return ""
    if "/" in s or "\\" in s or ".." in s:
        return ""
    return Path(s).name


def api_status() -> Dict[str, Any]:
    from api.settings import APISettings

    settings = APISettings.from_env()
    scheme = (getattr(settings, "signature_scheme", "") or "").strip()
    pk = Path(getattr(settings, "ledger_pubkey_path", "") or "")

    notary_on = False
    effective_scheme = ""
    effective_pubkey_path = ""

    if scheme != "" and str(pk) not in ("", ".") and pk.exists() and pk.is_file():
        notary_on = True
        effective_scheme = scheme
        effective_pubkey_path = str(pk)

    out = {
        "schema": "api.status.v1",
        "ok": True,
        "host": settings.host,
        "port": settings.port,
        "allow_schema": settings.allow_schema,
        "historical_root": str(settings.historical_root),
        "notary_on": bool(notary_on),
        "signature_scheme": effective_scheme,
        "ledger_pubkey_path": effective_pubkey_path,
        "ts_ms": int(time.time() * 1000),
    }
    print(f"PASS_API_STATUS notary_on={int(notary_on)} scheme={(effective_scheme or 'OFF')}")
    return out

def verify_red_packet(payload: Dict[str, Any]) -> Dict[str, Any]:
    pkt_schema = str(payload.get("schema", "") or "")
    allow = settings.allow_schema

    if pkt_schema != allow:
        out = {
            "schema": "api.verify_red_packet.v1",
            "ok": False,
            "reason": "SCHEMA_NOT_ALLOWED",
            "allow_schema": allow,
            "packet_schema": pkt_schema,
            "step_number": int(payload.get("step_number", -1) or -1),
            "stream_id": str(payload.get("stream_id", "") or ""),
            "ts_ms": _ts_ms(),
        }
        return out

    step_number = int(payload.get("step_number", -1) or -1)
    stream_id = str(payload.get("stream_id", "") or "")

    if step_number < 0 or stream_id == "":
        out = {
            "schema": "api.verify_red_packet.v1",
            "ok": False,
            "reason": "INVALID_PACKET",
            "allow_schema": allow,
            "packet_schema": pkt_schema,
            "step_number": step_number,
            "stream_id": stream_id,
            "ts_ms": _ts_ms(),
        }
        return out

    out = {
        "schema": "api.verify_red_packet.v1",
        "ok": True,
        "reason": "PASS_RED_PACKET_SCHEMA",
        "allow_schema": allow,
        "packet_schema": pkt_schema,
        "step_number": step_number,
        "stream_id": stream_id,
        "ts_ms": _ts_ms(),
    }
    print(f"PASS_API_VERIFY_RED_PACKET stream_id={stream_id} step={step_number}")
    return out


def stream_manifest(stream_id: str, step_number: int) -> Tuple[Path, List[Dict[str, Any]]]:
    step_dir = settings.historical_root / stream_id / f"step_{step_number:06d}"
    files: List[Dict[str, Any]] = []
    if not step_dir.exists() or not step_dir.is_dir():
        return step_dir, files

    for p in sorted(step_dir.iterdir(), key=lambda x: x.name):
        if not p.is_file():
            continue
        b = p.read_bytes()
        files.append({"name": p.name, "bytes": len(b), "sha256": _sha256_bytes(b)})
    return step_dir, files


def stream_get_manifest_or_file(stream_id: str, step_number: int, file: str) -> Dict[str, Any]:
    step_dir, files = stream_manifest(stream_id, step_number)
    if not step_dir.exists() or not step_dir.is_dir():
        out = {
            "schema": "api.stream_manifest.v1",
            "stream_id": stream_id,
            "step_number": step_number,
            "ok": False,
            "reason": "MISSING_STEP_DIR",
            "step_dir": str(step_dir),
            "files": [],
            "ts_ms": _ts_ms(),
        }
        return out

    safe = _safe_file_name(file)
    if safe == "":
        out = {
            "schema": "api.stream_manifest.v1",
            "stream_id": stream_id,
            "step_number": step_number,
            "ok": True,
            "reason": "PASS_STREAM_MANIFEST",
            "step_dir": str(step_dir),
            "files": files,
            "ts_ms": _ts_ms(),
        }
        print(f"PASS_API_STREAM_MANIFEST stream_id={stream_id} step={step_number}")
        return out

    target = step_dir / safe
    if not target.exists() or not target.is_file():
        out = {
            "schema": "api.stream_file.v1",
            "stream_id": stream_id,
            "step_number": step_number,
            "ok": False,
            "reason": "MISSING_FILE",
            "step_dir": str(step_dir),
            "file": safe,
            "bytes": 0,
            "sha256": "",
            "text": "",
            "ts_ms": _ts_ms(),
        }
        return out

    b = target.read_bytes()
    try:
        text = b.decode("utf-8")
    except Exception:
        out = {
            "schema": "api.stream_file.v1",
            "stream_id": stream_id,
            "step_number": step_number,
            "ok": False,
            "reason": "BINARY_NOT_ALLOWED",
            "step_dir": str(step_dir),
            "file": safe,
            "bytes": len(b),
            "sha256": _sha256_bytes(b),
            "text": "",
            "ts_ms": _ts_ms(),
        }
        return out

    out = {
        "schema": "api.stream_file.v1",
        "stream_id": stream_id,
        "step_number": step_number,
        "ok": True,
        "reason": "PASS_STREAM_FILE",
        "step_dir": str(step_dir),
        "file": safe,
        "bytes": len(b),
        "sha256": _sha256_bytes(b),
        "text": text,
        "ts_ms": _ts_ms(),
    }
    print(f"PASS_API_STREAM_FILE stream_id={stream_id} step={step_number} file={safe}")
    return out

import shutil

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except Exception:
    Ed25519PrivateKey = None


def _copytree_strict(src: Path, dst: Path) -> None:
    shutil.copytree(str(src), str(dst), dirs_exist_ok=False)


def _read_hex_file(p: Path) -> bytes:
    s = p.read_text(encoding="utf-8").strip()
    return bytes.fromhex(s)


def _sign_root_hash_txt_ed25519(step_dir: Path, privkey_path: Path) -> bool:
    if Ed25519PrivateKey is None:
        return False
    if not privkey_path.exists():
        return False
    root_path = step_dir / "root_hash.txt"
    if not root_path.exists():
        return False
    root_hex = root_path.read_text(encoding="utf-8").strip()
    if root_hex == "":
        return False
    sk = _read_hex_file(privkey_path)
    if len(sk) != 32:
        return False
    priv = Ed25519PrivateKey.from_private_bytes(sk)
    sig = priv.sign(root_hex.encode("utf-8"))
    sig_hex = sig.hex() + "\n"
    (step_dir / "root.sig").write_text(sig_hex, encoding="utf-8")
    return True


def promote_step(stream_id: str, step_number: int, sign: bool) -> Dict[str, Any]:
    stream_id = str(stream_id or "").strip()
    if stream_id == "" or step_number < 0:
        out = {
            "schema": "api.promote_step.v1",
            "stream_id": stream_id,
            "step_number": step_number,
            "ok": False,
            "reason": "INVALID_REQUEST",
            "src_step_dir": "",
            "dst_step_dir": "",
            "signed": False,
            "signature_scheme": settings.signature_scheme,
            "ts_ms": _ts_ms(),
        }
        return out

    src = settings.stream_root / f"step_{step_number:06d}"
    dst = settings.historical_root / stream_id / f"step_{step_number:06d}"

    if not src.exists() or not src.is_dir():
        out = {
            "schema": "api.promote_step.v1",
            "stream_id": stream_id,
            "step_number": step_number,
            "ok": False,
            "reason": "MISSING_SOURCE_STEP_DIR",
            "src_step_dir": str(src),
            "dst_step_dir": str(dst),
            "signed": False,
            "signature_scheme": settings.signature_scheme,
            "ts_ms": _ts_ms(),
        }
        return out

    if dst.exists():
        out = {
            "schema": "api.promote_step.v1",
            "stream_id": stream_id,
            "step_number": step_number,
            "ok": False,
            "reason": "DEST_ALREADY_EXISTS",
            "src_step_dir": str(src),
            "dst_step_dir": str(dst),
            "signed": False,
            "signature_scheme": settings.signature_scheme,
            "ts_ms": _ts_ms(),
        }
        return out

    dst.parent.mkdir(parents=True, exist_ok=True)
    _copytree_strict(src, dst)

    signed = False
    if sign and settings.signature_scheme == "ed25519.v1":
        signed = _sign_root_hash_txt_ed25519(dst, settings.ledger_privkey_path)

    out = {
        "schema": "api.promote_step.v1",
        "stream_id": stream_id,
        "step_number": step_number,
        "ok": True,
        "reason": "PASS_PROMOTE_STEP",
        "src_step_dir": str(src),
        "dst_step_dir": str(dst),
        "signed": bool(signed),
        "signature_scheme": settings.signature_scheme,
        "ts_ms": _ts_ms(),
    }
    print(f"PASS_API_PROMOTE_STEP stream_id={stream_id} step={step_number} signed={int(signed)} scheme={settings.signature_scheme}")
    return out



def _sign_ed25519_v1(msg: bytes, sk_hex: str) -> str:
    sk_hex = (sk_hex or "").strip()
    if not sk_hex:
        raise ValueError("EMPTY_PRIVKEY")

    try:
        sk_bytes = bytes.fromhex(sk_hex)
    except Exception as e:
        raise ValueError("PRIVKEY_NOT_HEX") from e

    if len(sk_bytes) not in (32, 64):
        raise ValueError(f"PRIVKEY_BAD_LEN_{len(sk_bytes)}")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except Exception as e:
        raise RuntimeError("CRYPTOGRAPHY_NOT_INSTALLED") from e

    if len(sk_bytes) == 32:
        sk = Ed25519PrivateKey.from_private_bytes(sk_bytes)
    else:
        sk = Ed25519PrivateKey.from_private_bytes(sk_bytes[:32])

    sig = sk.sign(msg)
    return sig.hex()

def sign_step(stream_id: str, step_number: int) -> Dict[str, Any]:
    import time

    settings = APISettings.from_env()
    step_dir = settings.historical_root / str(stream_id) / f"step_{int(step_number):06d}"

    if not step_dir.exists() or not step_dir.is_dir():
        return {
            "schema": "api.sign_step.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": False,
            "reason": "MISSING_STEP_DIR",
            "step_dir": str(step_dir),
            "signed": False,
            "signature_scheme": str(settings.signature_scheme or ""),
            "ts_ms": int(time.time() * 1000),
        }

    sig_path = step_dir / "root.sig"
    if sig_path.exists():
        return {
            "schema": "api.sign_step.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": False,
            "reason": "SIG_ALREADY_EXISTS",
            "step_dir": str(step_dir),
            "signed": True,
            "signature_scheme": str(settings.signature_scheme or ""),
            "ts_ms": int(time.time() * 1000),
        }

    scheme = str(settings.signature_scheme or "")
    pk_path = Path(str(settings.ledger_pubkey_path or "")).expanduser()
    sk_path = pk_path.parent / "ledger_privkey.hex"

    if scheme != "ed25519.v1":
        return {
            "schema": "api.sign_step.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": False,
            "reason": "UNSUPPORTED_SCHEME",
            "step_dir": str(step_dir),
            "signed": False,
            "signature_scheme": scheme,
            "ts_ms": int(time.time() * 1000),
        }

    if not sk_path.exists():
        return {
            "schema": "api.sign_step.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": False,
            "reason": "MISSING_PRIVKEY",
            "step_dir": str(step_dir),
            "signed": False,
            "signature_scheme": scheme,
            "ts_ms": int(time.time() * 1000),
        }

    root_hash_txt = ""
    try:
        root_hash_txt = _read_text(step_dir / "root_hash.txt").strip()
    except Exception:
        root_hash_txt = ""

    if not root_hash_txt:
        return {
            "schema": "api.sign_step.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": False,
            "reason": "NO_ROOT_HASH",
            "step_dir": str(step_dir),
            "signed": False,
            "signature_scheme": scheme,
            "ts_ms": int(time.time() * 1000),
        }
    sk_hex = _read_text(sk_path).strip()
    msg = root_hash_txt.encode("utf-8")
    try:
        sig_hex = _sign_ed25519_v1(msg, sk_hex)
    except Exception as e:
        return {
            "schema": "api.sign_step.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": False,
            "reason": str(e),
            "step_dir": str(step_dir),
            "signed": False,
            "signature_scheme": scheme,
            "ts_ms": int(time.time() * 1000),
        }

    sig_path.write_text(sig_hex + "\n", encoding="utf-8")

    print(f"PASS_API_SIGN_STEP stream_id={stream_id} step={int(step_number)} scheme={scheme}")
    return {
        "schema": "api.sign_step.v1",
        "stream_id": str(stream_id),
        "step_number": int(step_number),
        "ok": True,
        "reason": "PASS_SIGN_STEP",
        "step_dir": str(step_dir),
        "signed": True,
        "signature_scheme": scheme,
        "ts_ms": int(time.time() * 1000),
    }

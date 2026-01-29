from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.settings import APISettings
from api.versioning import build_meta
from api.storage import build_storage_from_env
from verifier.contract_digest_v1 import verifier_contract_digest_v1


def _with_api_meta(d: dict) -> dict:
    m = build_meta()
    d2 = dict(d)
    d2["api_version"] = m.api_version
    d2["repo_version"] = m.repo_version
    d2["build_git_sha"] = m.build_git_sha
    return d2


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _tmp_step_dir(settings: APISettings, stream_id: str, step_number: int) -> Path:
    return settings.tmp_root / "audit" / str(stream_id) / f"step_{int(step_number):06d}"


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
            if isinstance(b, dict):
                merkle_root = str(b.get("merkle_root") or "")
        except Exception:
            merkle_root = ""

    if not merkle_root:
        merkle_root = root_hash_txt

    return _with_api_meta(
        {
            "schema": "api.replay_verify_step.v1",
            "step_dir": step_dir_s,
            "ok": bool(ok),
            "reason": str(reason or "NONE"),
            "merkle_root": str(merkle_root or ""),
            "leaf_hashes": leaf_hashes,
            "root_hash_txt": str(root_hash_txt or ""),
            "ts_ms": int(time.time() * 1000),
        }
    )


def api_status() -> Dict[str, Any]:
    settings = APISettings.from_env()
    notary_on = bool(settings.notary_on)
    scheme = str(settings.signature_scheme or "")
    contracts = verifier_contract_digest_v1(Path.cwd())

    print(
        f"PASS_API_STATUS notary_on={int(notary_on)} scheme={scheme} "
        f"api={build_meta().api_version} contracts={contracts}"
    )

    return _with_api_meta(
        {
            "schema": "api.status.v1",
            "ok": True,
            "host": settings.host,
            "port": settings.port,
            "allow_schema": settings.allow_schema,
            "historical_root": str(settings.historical_root),
            "notary_on": bool(settings.notary_on),
            "signature_scheme": str(settings.signature_scheme or ""),
            "ledger_pubkey_path": str(settings.ledger_pubkey_path or ""),
            "ts_ms": int(time.time() * 1000),
        }
    )


def _verify_signature_ed25519_v1(msg: bytes, sig_hex: str, vk_hex: str) -> bool:
    try:
        from scripts.ed25519_utils import verify_sig_ed25519
        return bool(verify_sig_ed25519(msg, sig_hex, vk_hex))
    except Exception:
        return False


def audit_verify_historical(stream_id: str, step_number: int) -> Dict[str, Any]:
    settings = APISettings.from_env()
    storage = build_storage_from_env(settings.historical_root)

    tmp_dir = _tmp_step_dir(settings, stream_id, step_number)
    if tmp_dir.exists():
        for p in sorted(tmp_dir.rglob("*"), reverse=True):
            try:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    p.rmdir()
            except Exception:
                pass
        try:
            tmp_dir.rmdir()
        except Exception:
            pass

    capsule = storage.fetch_step_dir(stream_id, step_number, tmp_dir)

    if not capsule.fetched_ok or not tmp_dir.exists():
        return _with_api_meta(
            {
                "schema": "api.audit_verify_historical.v1",
                "stream_id": str(stream_id),
                "step_number": int(step_number),
                "ok": False,
                "reason": "MISSING_STEP_DIR",
                "merkle_root": "",
                "root_hash_txt": "",
                "leaf_hashes": [],
                "same_hash": False,
                "storage": capsule.as_dict(),
                "signature_valid": False,
                "ts_ms": int(time.time() * 1000),
            }
        )

    out = replay_verify_step_dir(tmp_dir)

    merkle_root = str(out.get("merkle_root") or "")
    leaf_hashes = out.get("leaf_hashes", [])
    if not isinstance(leaf_hashes, list):
        leaf_hashes = []

    root_hash_txt = ""
    try:
        root_hash_txt = _read_text(tmp_dir / "root_hash.txt")
    except Exception:
        root_hash_txt = ""

    same_hash = bool(root_hash_txt) and bool(merkle_root) and (root_hash_txt.strip() == merkle_root.strip())

    signature_valid = False
    if bool(settings.notary_on) and (settings.signature_scheme or "") == "ed25519.v1":
        pk_path_s = str(settings.ledger_pubkey_path or "")
        if pk_path_s:
            try:
                pk_hex = _read_text(Path(pk_path_s))
                sig_path = tmp_dir / "root.sig"
                if sig_path.exists():
                    sig_hex = _read_text(sig_path)
                    msg = (root_hash_txt or merkle_root).strip().encode("utf-8")
                    signature_valid = _verify_signature_ed25519_v1(msg, sig_hex, pk_hex)
            except Exception:
                signature_valid = False

    if bool(out.get("ok", False)):
        print(f"PASS_API_VERIFY_HISTORICAL stream_id={stream_id} step={int(step_number)}")

    if signature_valid:
        print(
            f"PASS_API_VERIFY_HISTORICAL_SIGNATURE stream_id={stream_id} step={int(step_number)} "
            f"scheme={settings.signature_scheme}"
        )

    return _with_api_meta(
        {
            "schema": "api.audit_verify_historical.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": bool(out.get("ok", False)),
            "reason": str(out.get("reason") or "NONE"),
            "merkle_root": merkle_root,
            "root_hash_txt": root_hash_txt,
            "leaf_hashes": [str(x) for x in leaf_hashes],
            "same_hash": bool(same_hash),
            "storage": capsule.as_dict(),
            "signature_valid": bool(signature_valid),
            "ts_ms": int(time.time() * 1000),
        }
    )


def promote_step(stream_id: str, step_number: int, sign: bool = False) -> Dict[str, Any]:
    settings = APISettings.from_env()
    storage = build_storage_from_env(settings.historical_root)

    src_step_dir = Path("out/stream") / f"step_{int(step_number):06d}"
    dst_uri = ""
    ok = False
    reason = "NONE"

    if not src_step_dir.exists():
        return _with_api_meta(
            {
                "schema": "api.promote_step.v1",
                "stream_id": str(stream_id),
                "step_number": int(step_number),
                "ok": False,
                "reason": "MISSING_SRC_STEP_DIR",
                "src_step_dir": str(src_step_dir),
                "dst_step_dir": "",
                "signed": False,
                "signature_scheme": str(settings.signature_scheme or ""),
                "ts_ms": int(time.time() * 1000),
            }
        )

    capsule = storage.promote_step_dir(stream_id, step_number, src_step_dir)
    dst_uri = f"{capsule.historical_root}/{capsule.object_prefix}".rstrip("/")

    if capsule.fetched_ok:
        ok = True
        reason = "PASS_PROMOTE_STEP"
    else:
        ok = False
        reason = "DEST_ALREADY_EXISTS" if capsule.backend == "filesystem" else "PROMOTE_FAILED"

    signed = False
    if ok and bool(sign):
        s = sign_step(stream_id, step_number)
        signed = bool(s.get("ok", False)) and bool(s.get("signed", False))

    return _with_api_meta(
        {
            "schema": "api.promote_step.v1",
            "stream_id": str(stream_id),
            "step_number": int(step_number),
            "ok": bool(ok),
            "reason": str(reason),
            "src_step_dir": str(src_step_dir),
            "dst_step_dir": str(dst_uri),
            "signed": bool(signed),
            "signature_scheme": str(settings.signature_scheme or ""),
            "ts_ms": int(time.time() * 1000),
        }
    )


def sign_step(stream_id: str, step_number: int) -> Dict[str, Any]:
    settings = APISettings.from_env()
    if not bool(settings.notary_on) or (settings.signature_scheme or "") != "ed25519.v1":
        return _with_api_meta(
            {
                "schema": "api.sign_step.v1",
                "stream_id": str(stream_id),
                "step_number": int(step_number),
                "ok": False,
                "reason": "NOTARY_DISABLED",
                "step_dir": "",
                "signed": False,
                "signature_scheme": str(settings.signature_scheme or ""),
                "ts_ms": int(time.time() * 1000),
            }
        )

    if not settings.ledger_privkey_path or not settings.ledger_pubkey_path:
        return _with_api_meta(
            {
                "schema": "api.sign_step.v1",
                "stream_id": str(stream_id),
                "step_number": int(step_number),
                "ok": False,
                "reason": "MISSING_LEDGER_KEYS",
                "step_dir": "",
                "signed": False,
                "signature_scheme": "ed25519.v1",
                "ts_ms": int(time.time() * 1000),
            }
        )

    step_dir = settings.historical_root / str(stream_id) / f"step_{int(step_number):06d}"
    if not step_dir.exists():
        return _with_api_meta(
            {
                "schema": "api.sign_step.v1",
                "stream_id": str(stream_id),
                "step_number": int(step_number),
                "ok": False,
                "reason": "MISSING_STEP_DIR",
                "step_dir": str(step_dir),
                "signed": False,
                "signature_scheme": "ed25519.v1",
                "ts_ms": int(time.time() * 1000),
            }
        )

    try:
        from scripts.ed25519_utils import sign_merkle_root

        sk_hex = _read_text(Path(settings.ledger_privkey_path))
        root = _read_text(step_dir / "root_hash.txt")
        sig_hex = sign_merkle_root(sk_hex, root)
        _write_text(step_dir / "root.sig", sig_hex + "\n")

        print(f"PASS_API_SIGN_STEP stream_id={stream_id} step={int(step_number)} scheme=ed25519.v1")

        return _with_api_meta(
            {
                "schema": "api.sign_step.v1",
                "stream_id": str(stream_id),
                "step_number": int(step_number),
                "ok": True,
                "reason": "PASS_SIGN_STEP",
                "step_dir": str(step_dir),
                "signed": True,
                "signature_scheme": "ed25519.v1",
                "ts_ms": int(time.time() * 1000),
            }
        )
    except Exception as e:
        return _with_api_meta(
            {
                "schema": "api.sign_step.v1",
                "stream_id": str(stream_id),
                "step_number": int(step_number),
                "ok": False,
                "reason": "EXC_" + e.__class__.__name__,
                "step_dir": str(step_dir),
                "signed": False,
                "signature_scheme": "ed25519.v1",
                "ts_ms": int(time.time() * 1000),
            }
        )

from __future__ import annotations

import argparse
from pathlib import Path


def _write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="keys", help="output directory for key material")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ed25519.v1
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        sk = Ed25519PrivateKey.generate()
        pk = sk.public_key()

        sk_raw = sk.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pk_raw = pk.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        _write_text(out_dir / "ledger_privkey.hex", sk_raw.hex())
        _write_text(out_dir / "ledger_pubkey.hex", pk_raw.hex())

        print("PASS_LEDGER_KEYGEN_ED25519")
        print(f"WROTE: {out_dir/'ledger_privkey.hex'}")
        print(f"WROTE: {out_dir/'ledger_pubkey.hex'}")
        return 0
    except Exception:
        pass

    # fallback: PyNaCl
    try:
        from nacl.signing import SigningKey

        sk = SigningKey.generate()
        pk = sk.verify_key

        _write_text(out_dir / "ledger_privkey.hex", bytes(sk).hex())
        _write_text(out_dir / "ledger_pubkey.hex", bytes(pk).hex())

        print("PASS_LEDGER_KEYGEN_ED25519")
        print(f"WROTE: {out_dir/'ledger_privkey.hex'}")
        print(f"WROTE: {out_dir/'ledger_pubkey.hex'}")
        return 0
    except Exception as e:
        raise SystemExit(f"ERROR: cannot keygen ed25519 via cryptography or nacl: {e}")


if __name__ == "__main__":
    raise SystemExit(main())

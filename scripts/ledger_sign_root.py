from __future__ import annotations

import argparse
from pathlib import Path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step-dir", required=True, help="step dir containing root_hash.txt")
    ap.add_argument("--privkey-hex", default="keys/ledger_privkey.hex", help="path to private key hex")
    ap.add_argument("--out-sig", default="root.sig", help="signature filename inside step dir")
    args = ap.parse_args()

    step_dir = Path(args.step_dir)
    if not step_dir.exists():
        raise SystemExit(f"ERROR: step_dir not found: {step_dir}")

    root_path = step_dir / "root_hash.txt"
    if not root_path.exists():
        raise SystemExit(f"ERROR: missing root_hash.txt: {root_path}")

    sk_path = Path(args.privkey_hex)
    if not sk_path.exists():
        raise SystemExit(f"ERROR: missing privkey: {sk_path}")

    root_hash_txt = _read_text(root_path)
    if not root_hash_txt:
        raise SystemExit("ERROR: root_hash.txt empty")

    msg = root_hash_txt.strip().encode("utf-8")
    sk_hex = _read_text(sk_path)
    sk_bytes = bytes.fromhex(sk_hex)

    sig_hex = ""

    # preferred: cryptography
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        sk = Ed25519PrivateKey.from_private_bytes(sk_bytes)
        sig = sk.sign(msg)
        sig_hex = sig.hex()
    except Exception:
        # fallback: PyNaCl
        try:
            from nacl.signing import SigningKey

            sk = SigningKey(sk_bytes)
            sig = sk.sign(msg).signature
            sig_hex = sig.hex()
        except Exception as e:
            raise SystemExit(f"ERROR: cannot sign via cryptography or nacl: {e}")

    sig_path = step_dir / args.out_sig
    _write_text(sig_path, sig_hex)

    print("PASS_LEDGER_SIGN_ROOT")
    print(f"STEP_DIR: {step_dir}")
    print(f"WROTE: {sig_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

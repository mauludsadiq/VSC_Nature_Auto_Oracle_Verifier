from __future__ import annotations
import os
from typing import Tuple

from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder


def load_or_create_keypair(key_dir: str = "out/keys") -> Tuple[str, str]:
    os.makedirs(key_dir, exist_ok=True)
    sk_path = os.path.join(key_dir, "ed25519_sk.hex")
    vk_path = os.path.join(key_dir, "ed25519_vk.hex")

    if os.path.isfile(sk_path) and os.path.isfile(vk_path):
        sk_hex = open(sk_path, "r", encoding="utf-8").read().strip()
        vk_hex = open(vk_path, "r", encoding="utf-8").read().strip()
        return sk_hex, vk_hex

    sk = SigningKey.generate()
    vk = sk.verify_key

    sk_hex = sk.encode(encoder=HexEncoder).decode("utf-8")
    vk_hex = vk.encode(encoder=HexEncoder).decode("utf-8")

    open(sk_path, "w", encoding="utf-8").write(sk_hex + "\n")
    open(vk_path, "w", encoding="utf-8").write(vk_hex + "\n")
    return sk_hex, vk_hex


def sign_merkle_root(sk_hex: str, merkle_root_hex: str) -> str:
    sk = SigningKey(sk_hex, encoder=HexEncoder)
    sig = sk.sign(merkle_root_hex.encode("utf-8")).signature
    return sig.hex()


def verify_merkle_root_sig(vk_hex: str, merkle_root_hex: str, sig_hex: str) -> bool:
    vk = VerifyKey(vk_hex, encoder=HexEncoder)
    sig = bytes.fromhex(sig_hex)
    vk.verify(merkle_root_hex.encode("utf-8"), sig)
    return True

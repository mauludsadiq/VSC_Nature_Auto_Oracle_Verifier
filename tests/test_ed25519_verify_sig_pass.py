from __future__ import annotations

from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

from scripts.ed25519_utils import verify_sig_ed25519


def test_verify_sig_ed25519_roundtrip_pass() -> None:
    sk = SigningKey.generate()
    vk = sk.verify_key

    msg = b"deadbeef"
    sig_hex = sk.sign(msg).signature.hex()
    vk_hex = vk.encode(encoder=HexEncoder).decode("utf-8")

    assert verify_sig_ed25519(msg, sig_hex, vk_hex) is True

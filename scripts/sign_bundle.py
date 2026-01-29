from __future__ import annotations
import os
import sys
import json
from typing import Any, Dict, List

from verifier.contract_digest_v1 import verifier_contract_digest_v1

from scripts.ed25519_utils import load_or_create_keypair, sign_merkle_root


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: str, x: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(x, f, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        f.write("\n")


def sign_step_dir(step_dir: str, key_dir: str = "out/keys") -> Dict[str, Any]:
    bundle_path = os.path.join(step_dir, "bundle.json")
    if not os.path.isfile(bundle_path):
        raise FileNotFoundError(bundle_path)

    bundle = load_json(bundle_path)
    bundle.setdefault("bundle_schema_version", "v1")
    bundle.setdefault("verifier_contract_digest", verifier_contract_digest_v1())
    root = bundle.get("merkle_root")
    if root is None or not isinstance(root, str):
        return {"ok": False, "reason": "BUNDLE_MISSING_MERKLE_ROOT", "step_dir": step_dir}

    sk_hex, vk_hex = load_or_create_keypair(key_dir=key_dir)
    sig_hex = sign_merkle_root(sk_hex, root)

    bundle["verifier_pubkey"] = vk_hex
    bundle["signature"] = sig_hex
    bundle["signature_scheme"] = "ed25519"
    dump_json(bundle_path, bundle)

    return {
        "ok": True,
        "reason": "PASS_SIGN_BUNDLE",
        "step_dir": step_dir,
        "merkle_root": root,
        "verifier_pubkey": vk_hex,
        "signature": sig_hex,
    }


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m scripts.sign_bundle <out/stream/step_000123>", file=sys.stderr)
        return 2
    step_dir = argv[1]
    out = sign_step_dir(step_dir)
    print(json.dumps(out, sort_keys=True))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

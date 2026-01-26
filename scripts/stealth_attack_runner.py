from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

from chaos_env.chaos_env_wrapper import run_oracle_step


def _inject_forbidden_mass(obj: Any, eta: float, forbidden_key: str) -> Tuple[Any, bool]:
    if not isinstance(obj, dict):
        return obj, False

    def _inject_into_map(m: Dict[str, Any]) -> bool:
        keys = [k for k in m.keys() if isinstance(m.get(k), (int, float))]
        if not keys:
            return False

        total = 0.0
        for k in keys:
            total += float(m[k])

        if total <= 0.0:
            return False

        scale = max(0.0, 1.0 - eta)
        for k in keys:
            m[k] = float(m[k]) * scale

        m[forbidden_key] = float(eta)
        return True

    def _inject_into_support_list(supp: Any) -> bool:
        if not isinstance(supp, list):
            return False
        if not supp:
            return False

        p_key = None
        for cand in ["p", "prob", "probability"]:
            if isinstance(supp[0], dict) and cand in supp[0]:
                p_key = cand
                break
        if p_key is None:
            return False

        total = 0.0
        for row in supp:
            if isinstance(row, dict) and p_key in row:
                total += float(row[p_key])

        if total <= 0.0:
            return False

        scale = max(0.0, 1.0 - eta)
        for row in supp:
            if isinstance(row, dict) and p_key in row:
                row[p_key] = float(row[p_key]) * scale

        supp.append({"action": forbidden_key, p_key: float(eta)})
        return True

    for key in ["pi_hat", "policy", "action_probs"]:
        if key in obj and isinstance(obj[key], dict):
            ok = _inject_into_map(obj[key])
            if ok:
                return obj, True

    if "support" in obj:
        ok = _inject_into_support_list(obj["support"])
        if ok:
            return obj, True

    for k, v in obj.items():
        if isinstance(v, dict):
            mutated, did = _inject_forbidden_mass(v, eta, forbidden_key)
            obj[k] = mutated
            if did:
                return obj, True

        if isinstance(v, list):
            for i in range(len(v)):
                if isinstance(v[i], dict):
                    mutated, did = _inject_forbidden_mass(v[i], eta, forbidden_key)
                    v[i] = mutated
                    if did:
                        return obj, True

    return obj, False


@dataclass
class InjectSpec:
    inject_step: int
    eta: float
    forbidden_key: str


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, required=True)
    ap.add_argument("--out-dir", type=str, default="out/stream")
    ap.add_argument("--inject-step", type=int, default=25)
    ap.add_argument("--eta", type=float, default=1e-12)
    ap.add_argument("--forbidden-key", type=str, default="FORBIDDEN")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    spec = InjectSpec(
        inject_step=args.inject_step,
        eta=args.eta,
        forbidden_key=args.forbidden_key,
    )

    out_dir = Path(args.out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    prev_bundle: Dict[str, Any] | None = None

    for t in range(args.steps):
        os.environ["VSC_STEALTH_FORBID_INJECT_STEP"] = str(spec.inject_step)
        os.environ["VSC_STEALTH_FORBID_ETA"] = repr(spec.eta)
        os.environ["VSC_STEALTH_FORBID_KEY"] = spec.forbidden_key

        bundle = run_oracle_step(
            step_counter=t,
            out_dir=str(out_dir),
            prev_bundle=prev_bundle,
            seed=args.seed,
        )

        prev_bundle = bundle

    print("DONE_STEALTH_ATTACK_RUN")
    print(f"OUT_DIR={out_dir}")


if __name__ == "__main__":
    main()

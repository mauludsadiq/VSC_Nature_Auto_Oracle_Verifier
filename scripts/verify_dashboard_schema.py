from pathlib import Path
from scripts.dashboard_schema import DASHBOARD_HEADER

def main():
    p = Path("out/stream/dashboard.csv")
    if not p.exists():
        raise SystemExit("dashboard.csv not found")

    head = p.read_text(encoding="utf-8").splitlines()[0] + "\n"
    if head != DASHBOARD_HEADER:
        raise SystemExit("FAIL_DASHBOARD_SCHEMA_MISMATCH")

    print("PASS_DASHBOARD_SCHEMA_PINNED")

if __name__ == "__main__":
    main()

import sys

from datagate.contract import load_contract


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m datagate.cli <contract.yaml>")
        return 2

    try:
        contract = load_contract(sys.argv[1])
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 2

    print("✔ Contract loaded successfully")
    print()
    print(f"Version  : {contract['version']}")
    print(f"Database : {contract['database']}")
    print(f"Schema   : {contract['schema']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

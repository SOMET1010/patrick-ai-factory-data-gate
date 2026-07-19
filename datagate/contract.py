from pathlib import Path
from typing import Any

import yaml


REQUIRED_KEYS = {"version", "database", "schema", "structure", "audit"}


def load_contract(path: str | Path) -> dict[str, Any]:
    contract_path = Path(path)

    if not contract_path.is_file():
        raise ValueError(f"Contract file not found: {contract_path}")

    with contract_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise ValueError("Contract root must be a YAML object")

    missing_keys = REQUIRED_KEYS - data.keys()
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ValueError(f"Missing required keys: {missing}")

    return data

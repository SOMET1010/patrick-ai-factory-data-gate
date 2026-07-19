"""Tests for contract loading and parsing."""

from __future__ import annotations

import pytest

from datagate.contract import Contract, load_contract
from datagate.exceptions import ContractError


def test_load_valid_contract() -> None:
    contract = load_contract("contracts/hermes-review.yaml")

    assert contract["version"] == 1
    assert contract["database"] == "hermes-review"
    assert contract["schema"] == "public"
    assert contract["structure"] == []
    assert contract["audit"] == []


def test_load_contract_missing_file() -> None:
    with pytest.raises(ContractError, match="not found"):
        load_contract("contracts/does-not-exist.yaml")


def test_load_contract_missing_keys(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("version: 1\n", encoding="utf-8")
    with pytest.raises(ContractError, match="Missing required keys"):
        load_contract(path)


def test_contract_from_file_empty_sections() -> None:
    contract = Contract.from_file("contracts/hermes-review.yaml")
    assert contract.version == 1
    assert contract.database == "hermes-review"
    assert contract.schema == "public"
    assert contract.structure == ()
    assert contract.audit == ()


def test_contract_from_mapping_full() -> None:
    data = {
        "version": 2,
        "database": "db",
        "schema": "public",
        "structure": [
            {
                "table": "users",
                "columns": [
                    {"name": "id", "type": "integer", "nullable": False},
                    "email",
                ],
                "primary_key": "id",
                "foreign_keys": [
                    {
                        "columns": ["org_id"],
                        "references_table": "orgs",
                        "references_columns": ["id"],
                    }
                ],
                "indexes": [
                    {"name": "users_email_idx", "columns": ["email"], "unique": True}
                ],
            }
        ],
        "audit": [{"table": "users", "required_columns": ["created_at"]}],
    }
    contract = Contract.from_mapping(data)

    assert contract.version == 2
    table = contract.structure[0]
    assert table.name == "users"
    assert table.primary_key == ("id",)
    assert table.columns[0].type == "integer"
    assert table.columns[0].nullable is False
    # Bare string column becomes a name-only spec.
    assert table.columns[1].name == "email"
    assert table.columns[1].type is None
    assert table.foreign_keys[0].references_table == "orgs"
    assert table.indexes[0].unique is True
    assert contract.audit[0].required_columns == ("created_at",)


def test_contract_rejects_non_list_structure() -> None:
    with pytest.raises(ContractError, match="must be a list"):
        Contract.from_mapping(
            {
                "version": 1,
                "database": "d",
                "schema": "s",
                "structure": {"not": "a list"},
                "audit": [],
            }
        )

"""Tests for the contract generator."""

from __future__ import annotations

import yaml

from datagate.contract import Contract
from datagate.generator import contract_from_schema, dump_contract
from tests.helpers import sample_schema


def test_contract_from_schema_shape() -> None:
    mapping = contract_from_schema(sample_schema(), "mydb")
    assert mapping["version"] == 1
    assert mapping["database"] == "mydb"
    assert mapping["schema"] == "public"

    tables = {t["table"]: t for t in mapping["structure"]}
    assert set(tables) == {"organizations", "users"}

    users = tables["users"]
    assert users["primary_key"] == ["id"]
    id_col = next(c for c in users["columns"] if c["name"] == "id")
    assert id_col["type"] == "integer"
    assert id_col["nullable"] is False
    # sample users has a FK to organizations and a unique email index
    assert users["foreign_keys"][0]["references_table"] == "organizations"
    assert users["indexes"][0]["name"] == "users_email_idx"
    assert users["indexes"][0]["unique"] is True


def test_generated_contract_round_trips() -> None:
    # A generated contract must be parseable by the contract loader.
    mapping = contract_from_schema(sample_schema(), "mydb")
    text = dump_contract(mapping)
    reparsed = yaml.safe_load(text)
    contract = Contract.from_mapping(reparsed)
    assert contract.database == "mydb"
    assert {t.name for t in contract.structure} == {"organizations", "users"}


def test_generated_contract_verifies_against_its_own_schema() -> None:
    # Generating from a schema and verifying that schema must yield zero findings.
    from datagate.engine import run_checks

    schema = sample_schema()
    contract = Contract.from_mapping(
        yaml.safe_load(dump_contract(contract_from_schema(schema, "mydb")))
    )
    assert run_checks(contract, schema) == []


def test_dump_contract_has_header() -> None:
    text = dump_contract(contract_from_schema(sample_schema(), "mydb"))
    assert text.startswith("# Draft contract generated")

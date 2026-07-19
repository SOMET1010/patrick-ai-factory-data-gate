"""Tests for the individual verification checks."""

from __future__ import annotations

from datagate.checks import (
    AuditCheck,
    ColumnsCheck,
    ConstraintsCheck,
    IndexesCheck,
    StructureCheck,
    default_checks,
)
from datagate.contract import Contract
from datagate.report import Severity
from tests.helpers import sample_schema


def _contract(structure=None, audit=None) -> Contract:
    return Contract.from_mapping(
        {
            "version": 1,
            "database": "db",
            "schema": "public",
            "structure": structure or [],
            "audit": audit or [],
        }
    )


def test_default_checks_names() -> None:
    assert [c.name for c in default_checks()] == [
        "structure",
        "columns",
        "constraints",
        "indexes",
        "audit",
    ]


def test_structure_missing_table() -> None:
    contract = _contract(structure=[{"table": "ghost"}])
    findings = StructureCheck().run(contract, sample_schema())
    assert len(findings) == 1
    assert findings[0].target == "table:ghost"
    assert findings[0].severity is Severity.ERROR


def test_structure_present_table_ok() -> None:
    contract = _contract(structure=[{"table": "users"}])
    assert StructureCheck().run(contract, sample_schema()) == []


def test_columns_type_and_nullable_mismatch() -> None:
    contract = _contract(
        structure=[
            {
                "table": "users",
                "columns": [
                    {"name": "id", "type": "bigint"},
                    {"name": "email", "nullable": True},
                    {"name": "ghost"},
                ],
            }
        ]
    )
    findings = ColumnsCheck().run(contract, sample_schema())
    targets = {f.target: f.message for f in findings}
    assert "column:users.id" in targets  # integer != bigint
    assert "column:users.email" in targets  # nullable mismatch
    assert "column:users.ghost" in targets  # missing column
    assert len(findings) == 3


def test_columns_type_alias_matches() -> None:
    # 'int' is an alias for 'integer' and 'varchar' etc. should not false-positive
    contract = _contract(
        structure=[{"table": "users", "columns": [{"name": "id", "type": "int"}]}]
    )
    assert ColumnsCheck().run(contract, sample_schema()) == []


def test_columns_skips_missing_table() -> None:
    contract = _contract(structure=[{"table": "ghost", "columns": [{"name": "id"}]}])
    # ColumnsCheck must not duplicate the missing-table finding.
    assert ColumnsCheck().run(contract, sample_schema()) == []


def test_constraints_primary_key_mismatch() -> None:
    contract = _contract(structure=[{"table": "users", "primary_key": ["id", "org_id"]}])
    findings = ConstraintsCheck().run(contract, sample_schema())
    assert len(findings) == 1
    assert findings[0].target == "primary_key:users"


def test_constraints_foreign_key_ok_and_missing() -> None:
    ok = _contract(
        structure=[
            {
                "table": "users",
                "foreign_keys": [
                    {"columns": ["org_id"], "references_table": "organizations"}
                ],
            }
        ]
    )
    assert ConstraintsCheck().run(ok, sample_schema()) == []

    missing = _contract(
        structure=[
            {
                "table": "users",
                "foreign_keys": [
                    {"columns": ["nope"], "references_table": "organizations"}
                ],
            }
        ]
    )
    findings = ConstraintsCheck().run(missing, sample_schema())
    assert len(findings) == 1
    assert findings[0].check == "constraints"


def test_indexes_present_and_missing() -> None:
    ok = _contract(
        structure=[
            {
                "table": "users",
                "indexes": [
                    {"name": "users_email_idx", "columns": ["email"], "unique": True}
                ],
            }
        ]
    )
    assert IndexesCheck().run(ok, sample_schema()) == []

    missing = _contract(
        structure=[{"table": "users", "indexes": [{"columns": ["created_at"]}]}]
    )
    findings = IndexesCheck().run(missing, sample_schema())
    assert len(findings) == 1
    assert findings[0].target == "index:users"


def test_audit_required_columns() -> None:
    ok = _contract(
        audit=[{"table": "users", "required_columns": ["created_at", "updated_at"]}]
    )
    assert AuditCheck().run(ok, sample_schema()) == []

    missing_col = _contract(
        audit=[{"table": "organizations", "required_columns": ["created_at"]}]
    )
    findings = AuditCheck().run(missing_col, sample_schema())
    assert len(findings) == 1
    assert findings[0].target == "column:organizations.created_at"

    missing_table = _contract(audit=[{"table": "ghost", "required_columns": ["x"]}])
    findings = AuditCheck().run(missing_table, sample_schema())
    assert findings[0].target == "table:ghost"

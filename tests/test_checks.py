"""Tests for the individual verification checks."""

from __future__ import annotations

from datagate.checks import (
    AuditCheck,
    ColumnsCheck,
    ConstraintsCheck,
    DriftCheck,
    IndexesCheck,
    StructureCheck,
    default_checks,
)
from datagate.contract import Contract
from datagate.report import Severity
from tests.helpers import sample_schema


def _contract(structure=None, audit=None, settings=None) -> Contract:
    data = {
        "version": 1,
        "database": "db",
        "schema": "public",
        "structure": structure or [],
        "audit": audit or [],
    }
    if settings is not None:
        data["settings"] = settings
    return Contract.from_mapping(data)


def test_default_checks_names() -> None:
    assert [c.name for c in default_checks()] == [
        "structure",
        "columns",
        "constraints",
        "indexes",
        "audit",
        "drift",
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


def test_columns_precision_and_length() -> None:
    # sample_schema has no length/precision info, so declaring them should fail.
    contract = _contract(
        structure=[
            {
                "table": "users",
                "columns": [{"name": "email", "type": "varchar(255)"}],
            }
        ]
    )
    findings = ColumnsCheck().run(contract, sample_schema())
    # email is 'text' in the sample schema -> type mismatch + length mismatch
    assert any("max length" in f.message for f in findings)


def test_columns_default_normalisation() -> None:
    from datagate.models import Column, Schema, Table

    schema = Schema(
        name="public",
        tables=(
            Table(
                name="t",
                columns=(
                    Column(
                        name="status",
                        data_type="text",
                        is_nullable=False,
                        default="'active'::text",
                    ),
                ),
            ),
        ),
    )
    # Contract declares the logical default 'active'; the cast/quotes must not
    # produce a false positive.
    ok = _contract(
        structure=[{"table": "t", "columns": [{"name": "status", "default": "active"}]}]
    )
    assert ColumnsCheck().run(ok, schema) == []

    bad = _contract(
        structure=[{"table": "t", "columns": [{"name": "status", "default": "off"}]}]
    )
    findings = ColumnsCheck().run(bad, schema)
    assert len(findings) == 1
    assert "default" in findings[0].message


def test_drift_ignored_by_default() -> None:
    contract = _contract(structure=[{"table": "users"}])
    # organizations is undeclared but drift defaults to 'ignore'.
    assert DriftCheck().run(contract, sample_schema()) == []


def test_drift_unexpected_table() -> None:
    contract = _contract(
        structure=[{"table": "users"}],
        settings={"unexpected_tables": "error"},
    )
    findings = DriftCheck().run(contract, sample_schema())
    assert len(findings) == 1
    assert findings[0].target == "table:organizations"
    assert findings[0].severity is Severity.ERROR


def test_drift_unexpected_table_warning() -> None:
    contract = _contract(
        structure=[{"table": "users"}, {"table": "organizations"}],
        settings={"unexpected_tables": "warning"},
    )
    assert DriftCheck().run(contract, sample_schema()) == []


def test_drift_unexpected_columns() -> None:
    contract = _contract(
        structure=[
            {
                "table": "users",
                "columns": [{"name": "id"}, {"name": "email"}],
            }
        ],
        settings={"unexpected_columns": "warning"},
    )
    findings = DriftCheck().run(contract, sample_schema())
    # users has org_id, created_at, updated_at beyond the declared id/email.
    undeclared = {f.target for f in findings}
    assert "column:users.org_id" in undeclared
    assert "column:users.created_at" in undeclared
    assert all(f.severity is Severity.WARNING for f in findings)


def test_drift_columns_skipped_when_not_declared() -> None:
    # A table declared without a columns list must not trigger column drift.
    contract = _contract(
        structure=[{"table": "users"}],
        settings={"unexpected_columns": "error"},
    )
    assert DriftCheck().run(contract, sample_schema()) == []

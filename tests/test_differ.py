"""Tests for the schema differ."""

from __future__ import annotations

import json

from datagate.differ import Impact, diff_contracts


def _mapping(structure):
    return {"version": 1, "database": "db", "schema": "public", "structure": structure}


def _table(name, columns):
    return {"table": name, "columns": columns}


def test_added_and_removed_table() -> None:
    source = _mapping([_table("users", [{"name": "id"}])])
    target = _mapping(
        [
            _table("users", [{"name": "id"}]),
            _table("audit_log", [{"name": "id"}]),
        ]
    )
    result = diff_contracts(source, target)
    kinds = {(c.kind.value, c.target): c.impact for c in result.changes}
    assert kinds[("added_table", "audit_log")] is Impact.SAFE

    # reverse: audit_log removed -> breaking
    result_rev = diff_contracts(target, source)
    rev = {(c.kind.value, c.target): c.impact for c in result_rev.changes}
    assert rev[("removed_table", "audit_log")] is Impact.BREAKING
    assert result_rev.compatibility == "BREAKING"
    assert result_rev.exit_code == 1


def test_added_column_nullability_impact() -> None:
    source = _mapping([_table("users", [{"name": "id"}])])
    target = _mapping(
        [
            _table(
                "users",
                [
                    {"name": "id"},
                    {"name": "bio", "nullable": True},
                    {"name": "email", "nullable": False},
                ],
            )
        ]
    )
    result = diff_contracts(source, target)
    impacts = {c.target: c.impact for c in result.changes}
    assert impacts["users.bio"] is Impact.SAFE
    assert impacts["users.email"] is Impact.WARNING


def test_removed_column_is_breaking() -> None:
    source = _mapping([_table("users", [{"name": "id"}, {"name": "legacy"}])])
    target = _mapping([_table("users", [{"name": "id"}])])
    result = diff_contracts(source, target)
    assert any(
        c.kind.value == "removed_column" and c.target == "users.legacy"
        for c in result.changes
    )
    assert result.compatibility == "BREAKING"


def test_modified_type_and_nullability() -> None:
    source = _mapping(
        [_table("customers", [{"name": "email", "type": "varchar", "nullable": True}])]
    )
    target = _mapping(
        [_table("customers", [{"name": "email", "type": "text", "nullable": False}])]
    )
    result = diff_contracts(source, target)
    details = [c.detail for c in result.changes]
    assert any("type" in d for d in details)
    assert any("nullable True -> False" in d for d in details)
    # type change + tightening null are both breaking
    assert result.breaking >= 2


def test_length_change_is_warning() -> None:
    source = _mapping(
        [_table("t", [{"name": "c", "type": "varchar", "max_length": 128}])]
    )
    target = _mapping([_table("t", [{"name": "c", "type": "varchar", "max_length": 64}])])
    result = diff_contracts(source, target)
    assert result.warnings == 1
    assert result.compatibility == "WARNING"
    assert result.exit_code == 0  # warnings do not fail


def test_no_changes_is_ok() -> None:
    m = _mapping([_table("users", [{"name": "id", "type": "integer"}])])
    result = diff_contracts(m, m)
    assert result.changes == ()
    assert result.compatibility == "OK"
    assert result.exit_code == 0


def test_diff_json_and_text() -> None:
    source = _mapping([_table("a", [{"name": "id"}])])
    target = _mapping([_table("a", [{"name": "id"}]), _table("b", [{"name": "id"}])])
    result = diff_contracts(source, target)

    payload = json.loads(result.to_json())
    assert payload["compatibility"] == "OK"
    assert payload["summary"]["safe"] == 1
    assert payload["changes"][0]["target"] == "b"

    text = result.to_text()
    assert "+ b" in text
    assert "Compatibility    : OK" in text

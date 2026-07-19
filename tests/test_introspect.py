"""Tests for the introspection row mappers and the Introspector."""

from __future__ import annotations

import pytest

from datagate.exceptions import IntrospectionError
from datagate.introspect import (
    Introspector,
    build_columns,
    build_foreign_keys,
    build_indexes,
    build_primary_keys,
)
from tests.helpers import FakeConnection


def test_build_columns_groups_by_table() -> None:
    rows = [
        ("users", "id", "integer", "NO", None, 1, None, 32, 0),
        ("users", "email", "character varying", "YES", None, 2, 255, None, None),
        ("orgs", "id", "integer", "NO", None, 1, None, 32, 0),
    ]
    columns = build_columns(rows)
    assert [c.name for c in columns["users"]] == ["id", "email"]
    assert columns["users"][0].is_nullable is False
    assert columns["users"][0].numeric_precision == 32
    assert columns["users"][1].is_nullable is True
    assert columns["users"][1].char_max_length == 255
    assert columns["orgs"][0].name == "id"


def test_build_primary_keys_preserves_order() -> None:
    rows = [("t", "a"), ("t", "b")]
    assert build_primary_keys(rows)["t"] == ("a", "b")


def test_build_foreign_keys_composite() -> None:
    rows = [
        ("fk", "child", "a", "parent", "x"),
        ("fk", "child", "b", "parent", "y"),
    ]
    fks = build_foreign_keys(rows)["child"]
    assert len(fks) == 1
    assert fks[0].columns == ("a", "b")
    assert fks[0].referenced_columns == ("x", "y")
    assert fks[0].referenced_table == "parent"


def test_build_indexes_flags() -> None:
    rows = [
        ("t", "t_pkey", "id", True, True),
        ("t", "t_email_idx", "email", True, False),
    ]
    indexes = {idx.name: idx for idx in build_indexes(rows)["t"]}
    assert indexes["t_pkey"].is_primary is True
    assert indexes["t_email_idx"].is_unique is True
    assert indexes["t_email_idx"].is_primary is False


def test_introspector_builds_schema_with_views() -> None:
    connection = FakeConnection(
        {
            "tables": [
                ("users", "BASE TABLE"),
                ("active_users", "VIEW"),
            ],
            "columns": [
                ("users", "id", "integer", "NO", None, 1, None, 32, 0),
                ("active_users", "id", "integer", "YES", None, 1, None, 32, 0),
            ],
            "primary_keys": [("users", "id")],
            "foreign_keys": [],
            "indexes": [("users", "users_pkey", "id", True, True)],
        }
    )
    schema = Introspector(connection).introspect("public")

    assert schema.name == "public"
    assert schema.table_names == ("users",)
    assert schema.view_names == ("active_users",)
    users = schema.table("users")
    assert users.primary_key == ("id",)
    assert users.indexes[0].name == "users_pkey"


def test_introspector_wraps_errors() -> None:
    class BoomConnection:
        def cursor(self):  # noqa: D401 - test stub
            raise RuntimeError("boom")

    with pytest.raises(IntrospectionError, match="Failed to read schema"):
        Introspector(BoomConnection()).introspect("public")

"""Tests for the schema domain model helpers."""

from __future__ import annotations

from datagate.models import Column, Schema, Table, View


def test_table_column_lookup() -> None:
    table = Table(
        name="t",
        columns=(
            Column(name="a", data_type="integer", is_nullable=False),
            Column(name="b", data_type="text", is_nullable=True),
        ),
    )
    assert table.column("a").data_type == "integer"
    assert table.column("missing") is None
    assert table.column_names == ("a", "b")


def test_schema_lookups() -> None:
    schema = Schema(
        name="public",
        tables=(Table(name="users"),),
        views=(View(name="v"),),
    )
    assert schema.table("users") is not None
    assert schema.table("nope") is None
    assert schema.view("v") is not None
    assert schema.view("nope") is None
    assert schema.table_names == ("users",)
    assert schema.view_names == ("v",)

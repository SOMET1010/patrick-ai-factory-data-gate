"""Shared test fixtures and fakes."""

from __future__ import annotations

from datagate.models import Column, ForeignKey, Index, Schema, Table, View


class FakeCursor:
    """Minimal cursor that returns canned rows keyed by a query tag."""

    def __init__(self, rows_by_tag: dict[str, list[tuple]]):
        self._rows_by_tag = rows_by_tag
        self._current: list[tuple] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, query: str, params=None) -> None:
        for tag, rows in self._rows_by_tag.items():
            if f"datagate:{tag}" in query:
                self._current = rows
                return
        self._current = []

    def fetchall(self) -> list[tuple]:
        return self._current

    def fetchone(self) -> tuple | None:
        return self._current[0] if self._current else None


class FakeConnection:
    """Connection stub yielding :class:`FakeCursor` instances."""

    def __init__(self, rows_by_tag: dict[str, list[tuple]]):
        self._rows_by_tag = rows_by_tag

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._rows_by_tag)


def sample_schema() -> Schema:
    """A small, well-formed schema used across check tests."""
    organizations = Table(
        name="organizations",
        columns=(
            Column(name="id", data_type="integer", is_nullable=False, ordinal=1),
            Column(name="name", data_type="text", is_nullable=False, ordinal=2),
        ),
        primary_key=("id",),
    )
    users = Table(
        name="users",
        columns=(
            Column(name="id", data_type="integer", is_nullable=False, ordinal=1),
            Column(name="org_id", data_type="integer", is_nullable=False, ordinal=2),
            Column(name="email", data_type="text", is_nullable=False, ordinal=3),
            Column(
                name="created_at",
                data_type="timestamp without time zone",
                is_nullable=False,
                ordinal=4,
            ),
            Column(
                name="updated_at",
                data_type="timestamp without time zone",
                is_nullable=True,
                ordinal=5,
            ),
        ),
        primary_key=("id",),
        foreign_keys=(
            ForeignKey(
                name="users_org_id_fkey",
                columns=("org_id",),
                referenced_table="organizations",
                referenced_columns=("id",),
            ),
        ),
        indexes=(Index(name="users_email_idx", columns=("email",), is_unique=True),),
    )
    return Schema(
        name="public",
        tables=(organizations, users),
        views=(View(name="active_users"),),
    )

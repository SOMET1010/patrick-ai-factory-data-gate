"""Read-only introspection of a live PostgreSQL schema.

The :class:`Introspector` runs a handful of ``SELECT`` statements against the
system catalogs and ``information_schema`` and assembles the result into the
immutable domain model defined in :mod:`datagate.models`.

Every query is a pure read. The row-to-model mapping is implemented as standalone
functions so it can be unit-tested without a live database.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from datagate.exceptions import IntrospectionError
from datagate.models import Column, ForeignKey, Index, Schema, Table, View

logger = logging.getLogger(__name__)


class _Cursor(Protocol):
    def execute(self, query: str, params: Sequence[Any] | None = ...) -> Any: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def __enter__(self) -> _Cursor: ...

    def __exit__(self, *exc: object) -> Any: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...


# --- SQL statements (strictly read-only) --------------------------------------

SQL_TABLES = """
-- datagate:tables
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = %s
  AND table_type IN ('BASE TABLE', 'VIEW')
ORDER BY table_name
"""

SQL_COLUMNS = """
-- datagate:columns
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default,
    ordinal_position,
    character_maximum_length,
    numeric_precision,
    numeric_scale
FROM information_schema.columns
WHERE table_schema = %s
ORDER BY table_name, ordinal_position
"""

SQL_PRIMARY_KEYS = """
-- datagate:primary_keys
-- Read from pg_catalog rather than information_schema.table_constraints, which
-- is privilege-aware and hides constraints from least-privilege (read-only)
-- roles that only hold SELECT.
SELECT
    rel.relname AS table_name,
    att.attname AS column_name
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.attnum
WHERE ns.nspname = %s
  AND con.contype = 'p'
ORDER BY rel.relname, k.ord
"""

SQL_FOREIGN_KEYS = """
-- datagate:foreign_keys
SELECT
    con.conname AS constraint_name,
    rel.relname AS table_name,
    att.attname AS column_name,
    frel.relname AS referenced_table,
    fatt.attname AS referenced_column
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
JOIN pg_namespace ns ON ns.oid = rel.relnamespace
JOIN LATERAL unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.attnum
JOIN pg_class frel ON frel.oid = con.confrelid
JOIN LATERAL unnest(con.confkey) WITH ORDINALITY AS fk(attnum, ord) ON fk.ord = k.ord
JOIN pg_attribute fatt ON fatt.attrelid = con.confrelid AND fatt.attnum = fk.attnum
WHERE ns.nspname = %s
  AND con.contype = 'f'
ORDER BY rel.relname, con.conname, k.ord
"""

SQL_INDEXES = """
-- datagate:indexes
SELECT
    t.relname AS table_name,
    i.relname AS index_name,
    a.attname AS column_name,
    ix.indisunique AS is_unique,
    ix.indisprimary AS is_primary
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace ns ON ns.oid = t.relnamespace
JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
WHERE ns.nspname = %s
  AND t.relkind = 'r'
ORDER BY t.relname, i.relname, k.ord
"""


def _to_bool(value: Any) -> bool:
    """Normalise the many ways PostgreSQL reports a boolean flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() in {"YES", "TRUE", "T", "Y", "1"}
    return bool(value)


# --- Row mappers (pure) -------------------------------------------------------


def _to_int(value: Any) -> int | None:
    return None if value is None else int(value)


def build_columns(rows: Iterable[Sequence[Any]]) -> dict[str, list[Column]]:
    """Map ``information_schema.columns`` rows to columns keyed by table."""
    columns: dict[str, list[Column]] = defaultdict(list)
    for row in rows:
        (
            table_name,
            name,
            data_type,
            is_nullable,
            default,
            ordinal,
            char_max_length,
            numeric_precision,
            numeric_scale,
        ) = row
        columns[table_name].append(
            Column(
                name=name,
                data_type=data_type,
                is_nullable=_to_bool(is_nullable),
                default=default,
                ordinal=int(ordinal) if ordinal is not None else 0,
                char_max_length=_to_int(char_max_length),
                numeric_precision=_to_int(numeric_precision),
                numeric_scale=_to_int(numeric_scale),
            )
        )
    return columns


def build_primary_keys(rows: Iterable[Sequence[Any]]) -> dict[str, tuple[str, ...]]:
    keys: dict[str, list[str]] = defaultdict(list)
    for table_name, column_name in rows:
        keys[table_name].append(column_name)
    return {table: tuple(cols) for table, cols in keys.items()}


def build_foreign_keys(rows: Iterable[Sequence[Any]]) -> dict[str, list[ForeignKey]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for constraint_name, table_name, column_name, ref_table, ref_column in rows:
        key = (table_name, constraint_name)
        if key not in grouped:
            grouped[key] = {
                "table": table_name,
                "name": constraint_name,
                "columns": [],
                "ref_table": ref_table,
                "ref_columns": [],
            }
            order.append(key)
        grouped[key]["columns"].append(column_name)
        grouped[key]["ref_columns"].append(ref_column)

    result: dict[str, list[ForeignKey]] = defaultdict(list)
    for key in order:
        data = grouped[key]
        result[data["table"]].append(
            ForeignKey(
                name=data["name"],
                columns=tuple(data["columns"]),
                referenced_table=data["ref_table"],
                referenced_columns=tuple(data["ref_columns"]),
            )
        )
    return result


def build_indexes(rows: Iterable[Sequence[Any]]) -> dict[str, list[Index]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for table_name, index_name, column_name, is_unique, is_primary in rows:
        key = (table_name, index_name)
        if key not in grouped:
            grouped[key] = {
                "table": table_name,
                "name": index_name,
                "columns": [],
                "unique": _to_bool(is_unique),
                "primary": _to_bool(is_primary),
            }
            order.append(key)
        grouped[key]["columns"].append(column_name)

    result: dict[str, list[Index]] = defaultdict(list)
    for key in order:
        data = grouped[key]
        result[data["table"]].append(
            Index(
                name=data["name"],
                columns=tuple(data["columns"]),
                is_unique=data["unique"],
                is_primary=data["primary"],
            )
        )
    return result


class Introspector:
    """Reads the live schema from a read-only connection."""

    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    def introspect(self, schema: str) -> Schema:
        """Return the :class:`~datagate.models.Schema` for ``schema``."""
        logger.info("Introspecting schema '%s'", schema)
        try:
            table_rows = self._fetch(SQL_TABLES, (schema,))
            columns = build_columns(self._fetch(SQL_COLUMNS, (schema,)))
            primary_keys = build_primary_keys(self._fetch(SQL_PRIMARY_KEYS, (schema,)))
            foreign_keys = build_foreign_keys(self._fetch(SQL_FOREIGN_KEYS, (schema,)))
            indexes = build_indexes(self._fetch(SQL_INDEXES, (schema,)))
        except Exception as exc:  # noqa: BLE001 - re-raised as a domain error
            raise IntrospectionError(f"Failed to read schema '{schema}': {exc}") from exc

        tables: list[Table] = []
        views: list[View] = []
        for table_name, table_type in table_rows:
            table_columns = tuple(columns.get(table_name, []))
            if table_type == "VIEW":
                views.append(View(name=table_name, columns=table_columns))
            else:
                tables.append(
                    Table(
                        name=table_name,
                        columns=table_columns,
                        primary_key=primary_keys.get(table_name, ()),
                        foreign_keys=tuple(foreign_keys.get(table_name, [])),
                        indexes=tuple(indexes.get(table_name, [])),
                    )
                )

        logger.info(
            "Introspection complete: %d table(s), %d view(s)", len(tables), len(views)
        )
        return Schema(name=schema, tables=tuple(tables), views=tuple(views))

    def current_database(self) -> str:
        """Return the name of the database the connection is attached to."""
        with self._connection.cursor() as cursor:
            cursor.execute("-- datagate:current_database\nSELECT current_database()")
            row = cursor.fetchone()
        return str(row[0]) if row else ""

    def _fetch(self, sql: str, params: Sequence[Any]) -> list[tuple[Any, ...]]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

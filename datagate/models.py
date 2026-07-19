"""Domain model describing the *actual* state of a PostgreSQL schema.

These immutable dataclasses are the single representation of the database that
the verification checks consume. They are deliberately decoupled from psycopg
and from the YAML contract so that the introspection layer, the checks and the
tests can all share one clean, typed model.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Column:
    """A single column of a table or view."""

    name: str
    data_type: str
    is_nullable: bool
    default: str | None = None
    ordinal: int = 0


@dataclass(frozen=True)
class ForeignKey:
    """A foreign-key constraint, possibly spanning several columns."""

    name: str
    columns: tuple[str, ...]
    referenced_table: str
    referenced_columns: tuple[str, ...]


@dataclass(frozen=True)
class Index:
    """An index defined on a table."""

    name: str
    columns: tuple[str, ...]
    is_unique: bool = False
    is_primary: bool = False


@dataclass(frozen=True)
class Table:
    """A base table together with the structural objects attached to it."""

    name: str
    columns: tuple[Column, ...] = ()
    primary_key: tuple[str, ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()
    indexes: tuple[Index, ...] = ()

    def column(self, name: str) -> Column | None:
        """Return the column named ``name`` (case-sensitive) or ``None``."""
        for column in self.columns:
            if column.name == name:
                return column
        return None

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


@dataclass(frozen=True)
class View:
    """A view. Only its projected columns are tracked."""

    name: str
    columns: tuple[Column, ...] = ()

    def column(self, name: str) -> Column | None:
        for column in self.columns:
            if column.name == name:
                return column
        return None


@dataclass(frozen=True)
class Schema:
    """The introspected state of a whole PostgreSQL schema."""

    name: str
    tables: tuple[Table, ...] = field(default_factory=tuple)
    views: tuple[View, ...] = field(default_factory=tuple)

    def table(self, name: str) -> Table | None:
        for table in self.tables:
            if table.name == name:
                return table
        return None

    def view(self, name: str) -> View | None:
        for view in self.views:
            if view.name == name:
                return view
        return None

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(table.name for table in self.tables)

    @property
    def view_names(self) -> tuple[str, ...]:
        return tuple(view.name for view in self.views)

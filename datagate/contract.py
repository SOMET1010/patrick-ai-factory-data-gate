"""Loading and parsing of the YAML *contract*.

The contract expresses the **expectations** about a schema. The live database
remains the source of truth; the contract only declares what must be present.

Two public entry points are provided:

* :func:`load_contract` returns the raw ``dict`` after minimal validation. It is
  kept for backward compatibility with earlier versions of the tool.
* :class:`Contract` (via :meth:`Contract.from_file` / :meth:`Contract.from_mapping`)
  returns a fully typed model that the verification engine consumes.

The contract keeps ``structure`` and ``audit`` as *lists* of rules so that an
empty contract (``structure: []`` / ``audit: []``) stays valid.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from datagate.exceptions import ContractError

REQUIRED_KEYS = {"version", "database", "schema", "structure", "audit"}


def load_contract(path: str | Path) -> dict[str, Any]:
    """Load a contract file and return the raw mapping.

    Performs only structural validation (presence of the required top-level
    keys). Raises :class:`ContractError` on any problem.
    """
    contract_path = Path(path)

    if not contract_path.is_file():
        raise ContractError(f"Contract file not found: {contract_path}")

    try:
        with contract_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as exc:  # pragma: no cover - passthrough of parser msg
        raise ContractError(f"Invalid YAML in {contract_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ContractError("Contract root must be a YAML object")

    missing_keys = REQUIRED_KEYS - data.keys()
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ContractError(f"Missing required keys: {missing}")

    return data


@dataclass(frozen=True)
class ColumnSpec:
    """Expectation about a single column."""

    name: str
    type: str | None = None
    nullable: bool | None = None


@dataclass(frozen=True)
class ForeignKeySpec:
    """Expectation about a foreign key."""

    columns: tuple[str, ...]
    references_table: str
    references_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class IndexSpec:
    """Expectation about an index."""

    columns: tuple[str, ...]
    name: str | None = None
    unique: bool = False


@dataclass(frozen=True)
class TableSpec:
    """Expectation about a table and its structural objects."""

    name: str
    columns: tuple[ColumnSpec, ...] = ()
    primary_key: tuple[str, ...] = ()
    foreign_keys: tuple[ForeignKeySpec, ...] = ()
    indexes: tuple[IndexSpec, ...] = ()


@dataclass(frozen=True)
class AuditRule:
    """Governance rule: a table must expose a set of required columns."""

    table: str
    required_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Contract:
    """A fully parsed, typed contract."""

    version: int
    database: str
    schema: str
    structure: tuple[TableSpec, ...] = ()
    audit: tuple[AuditRule, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> Contract:
        """Load and parse a contract file into a :class:`Contract`."""
        return cls.from_mapping(load_contract(path))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Contract:
        """Parse an already-loaded mapping into a :class:`Contract`."""
        missing_keys = REQUIRED_KEYS - data.keys()
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ContractError(f"Missing required keys: {missing}")

        return cls(
            version=int(data["version"]),
            database=str(data["database"]),
            schema=str(data["schema"]),
            structure=_parse_structure(data.get("structure") or []),
            audit=_parse_audit(data.get("audit") or []),
            raw=dict(data),
        )


def _as_sequence(value: Any, context: str) -> Sequence[Any]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ContractError(f"'{context}' must be a list")
    return value


def _as_str_tuple(value: Any, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    raise ContractError(f"'{context}' must be a string or a list of strings")


def _parse_structure(raw: Any) -> tuple[TableSpec, ...]:
    tables: list[TableSpec] = []
    for entry in _as_sequence(raw, "structure"):
        if not isinstance(entry, Mapping):
            raise ContractError("each 'structure' entry must be a mapping")
        name = entry.get("table") or entry.get("name")
        if not name:
            raise ContractError("each 'structure' entry needs a 'table' name")
        tables.append(
            TableSpec(
                name=str(name),
                columns=_parse_columns(entry.get("columns")),
                primary_key=_as_str_tuple(entry.get("primary_key"), "primary_key"),
                foreign_keys=_parse_foreign_keys(entry.get("foreign_keys")),
                indexes=_parse_indexes(entry.get("indexes")),
            )
        )
    return tuple(tables)


def _parse_columns(raw: Any) -> tuple[ColumnSpec, ...]:
    columns: list[ColumnSpec] = []
    for entry in _as_sequence(raw, "columns"):
        if isinstance(entry, str):
            columns.append(ColumnSpec(name=entry))
            continue
        if not isinstance(entry, Mapping):
            raise ContractError("each 'columns' entry must be a string or mapping")
        name = entry.get("name")
        if not name:
            raise ContractError("each 'columns' entry needs a 'name'")
        column_type = entry.get("type")
        nullable = entry.get("nullable")
        columns.append(
            ColumnSpec(
                name=str(name),
                type=None if column_type is None else str(column_type),
                nullable=None if nullable is None else bool(nullable),
            )
        )
    return tuple(columns)


def _parse_foreign_keys(raw: Any) -> tuple[ForeignKeySpec, ...]:
    keys: list[ForeignKeySpec] = []
    for entry in _as_sequence(raw, "foreign_keys"):
        if not isinstance(entry, Mapping):
            raise ContractError("each 'foreign_keys' entry must be a mapping")
        references_table = entry.get("references_table") or entry.get("references")
        if not references_table:
            raise ContractError("each foreign key needs a 'references_table'")
        keys.append(
            ForeignKeySpec(
                columns=_as_str_tuple(entry.get("columns"), "foreign_keys.columns"),
                references_table=str(references_table),
                references_columns=_as_str_tuple(
                    entry.get("references_columns"), "foreign_keys.references_columns"
                ),
            )
        )
    return tuple(keys)


def _parse_indexes(raw: Any) -> tuple[IndexSpec, ...]:
    indexes: list[IndexSpec] = []
    for entry in _as_sequence(raw, "indexes"):
        if not isinstance(entry, Mapping):
            raise ContractError("each 'indexes' entry must be a mapping")
        name = entry.get("name")
        indexes.append(
            IndexSpec(
                columns=_as_str_tuple(entry.get("columns"), "indexes.columns"),
                name=None if name is None else str(name),
                unique=bool(entry.get("unique", False)),
            )
        )
    return tuple(indexes)


def _parse_audit(raw: Any) -> tuple[AuditRule, ...]:
    rules: list[AuditRule] = []
    for entry in _as_sequence(raw, "audit"):
        if not isinstance(entry, Mapping):
            raise ContractError("each 'audit' entry must be a mapping")
        table = entry.get("table") or entry.get("name")
        if not table:
            raise ContractError("each 'audit' entry needs a 'table' name")
        rules.append(
            AuditRule(
                table=str(table),
                required_columns=_as_str_tuple(
                    entry.get("required_columns"), "audit.required_columns"
                ),
            )
        )
    return tuple(rules)

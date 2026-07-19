"""Compare two schema sources and classify the changes.

A *source* is normalised to a contract mapping (the same shape produced by
``datagate generate`` and accepted by ``verify``). Either side may come from a
YAML file or from a live database, but the diff itself works purely on mappings,
so it is deterministic and easy to test.

Each change is classified by its impact on consumers:

* ``SAFE``     – additive, cannot break existing readers/writers
* ``WARNING``  – potentially disruptive (narrowing, new mandatory column)
* ``BREAKING`` – removes or tightens something consumers may rely on
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Impact(StrEnum):
    SAFE = "safe"
    WARNING = "warning"
    BREAKING = "breaking"


class ChangeKind(StrEnum):
    ADDED_TABLE = "added_table"
    REMOVED_TABLE = "removed_table"
    ADDED_COLUMN = "added_column"
    REMOVED_COLUMN = "removed_column"
    MODIFIED_COLUMN = "modified_column"


_SYMBOL = {
    ChangeKind.ADDED_TABLE: "+",
    ChangeKind.ADDED_COLUMN: "+",
    ChangeKind.REMOVED_TABLE: "-",
    ChangeKind.REMOVED_COLUMN: "-",
    ChangeKind.MODIFIED_COLUMN: "~",
}


@dataclass(frozen=True)
class Change:
    kind: ChangeKind
    impact: Impact
    target: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind.value,
            "impact": self.impact.value,
            "target": self.target,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DiffResult:
    changes: tuple[Change, ...] = ()

    @property
    def breaking(self) -> int:
        return sum(1 for c in self.changes if c.impact is Impact.BREAKING)

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.changes if c.impact is Impact.WARNING)

    @property
    def safe(self) -> int:
        return sum(1 for c in self.changes if c.impact is Impact.SAFE)

    @property
    def compatibility(self) -> str:
        if self.breaking:
            return "BREAKING"
        if self.warnings:
            return "WARNING"
        return "OK"

    @property
    def exit_code(self) -> int:
        """0 when there are no breaking changes, 1 otherwise."""
        return 1 if self.breaking else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "compatibility": self.compatibility,
            "breaking_changes": self.breaking > 0,
            "summary": {
                "safe": self.safe,
                "warnings": self.warnings,
                "breaking": self.breaking,
                "total": len(self.changes),
            },
            "changes": [c.to_dict() for c in self.changes],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def to_text(self) -> str:
        lines: list[str] = []
        for change in self.changes:
            symbol = _SYMBOL[change.kind]
            suffix = f"  ({change.detail})" if change.detail else ""
            lines.append(f"{symbol} {change.target}{suffix}")
        lines.append("")
        lines.append("Summary")
        lines.append("-------")
        lines.append(f"Safe additions   : {self.safe}")
        lines.append(f"Warnings         : {self.warnings}")
        lines.append(f"Breaking changes : {self.breaking}")
        lines.append("")
        lines.append(f"Compatibility    : {self.compatibility}")
        return "\n".join(lines)


def _normalise_type(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip().lower()


def _index_tables(mapping: Mapping[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Return ``{table: {column: column_spec}}`` from a contract mapping."""
    tables: dict[str, dict[str, dict[str, Any]]] = {}
    for entry in mapping.get("structure") or []:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("table") or entry.get("name")
        if not name:
            continue
        columns: dict[str, dict[str, Any]] = {}
        for column in entry.get("columns") or []:
            if isinstance(column, str):
                columns[column] = {"name": column}
            elif isinstance(column, Mapping) and column.get("name"):
                columns[str(column["name"])] = dict(column)
        tables[str(name)] = columns
    return tables


def _nullable(spec: Mapping[str, Any]) -> bool:
    # Unknown nullability is treated as nullable (the permissive default).
    value = spec.get("nullable")
    return True if value is None else bool(value)


def _column_changes(table: str, source: dict, target: dict) -> list[Change]:
    changes: list[Change] = []

    for name, spec in target.items():
        if name not in source:
            impact = Impact.SAFE if _nullable(spec) else Impact.WARNING
            detail = "" if _nullable(spec) else "new NOT NULL column"
            changes.append(
                Change(ChangeKind.ADDED_COLUMN, impact, f"{table}.{name}", detail)
            )

    for name, spec in source.items():
        if name not in target:
            changes.append(
                Change(ChangeKind.REMOVED_COLUMN, Impact.BREAKING, f"{table}.{name}")
            )
            continue
        changes.extend(_modified_column(table, name, spec, target[name]))

    return changes


def _modified_column(table: str, name: str, before: dict, after: dict) -> list[Change]:
    changes: list[Change] = []
    target = f"{table}.{name}"

    b_type, a_type = _normalise_type(before.get("type")), _normalise_type(
        after.get("type")
    )
    if b_type is not None and a_type is not None and b_type != a_type:
        changes.append(
            Change(
                ChangeKind.MODIFIED_COLUMN,
                Impact.BREAKING,
                target,
                f"type {before.get('type')} -> {after.get('type')}",
            )
        )

    b_null, a_null = _nullable(before), _nullable(after)
    if b_null != a_null:
        # Becoming NOT NULL can reject existing writers; relaxing is safe.
        impact = Impact.BREAKING if (b_null and not a_null) else Impact.SAFE
        changes.append(
            Change(
                ChangeKind.MODIFIED_COLUMN,
                impact,
                target,
                f"nullable {b_null} -> {a_null}",
            )
        )

    for attr in ("max_length", "precision", "scale"):
        before_val, after_val = before.get(attr), after.get(attr)
        if before_val != after_val and (before_val is not None or after_val is not None):
            changes.append(
                Change(
                    ChangeKind.MODIFIED_COLUMN,
                    Impact.WARNING,
                    target,
                    f"{attr} {before_val} -> {after_val}",
                )
            )

    return changes


def diff_contracts(source: Mapping[str, Any], target: Mapping[str, Any]) -> DiffResult:
    """Diff two contract mappings (source -> target)."""
    source_tables = _index_tables(source)
    target_tables = _index_tables(target)
    changes: list[Change] = []

    for table in target_tables:
        if table not in source_tables:
            changes.append(Change(ChangeKind.ADDED_TABLE, Impact.SAFE, table))

    for table in source_tables:
        if table not in target_tables:
            changes.append(Change(ChangeKind.REMOVED_TABLE, Impact.BREAKING, table))
            continue
        changes.extend(_column_changes(table, source_tables[table], target_tables[table]))

    # Stable ordering: added tables, then per-table column changes, then removals.
    order = {
        ChangeKind.ADDED_TABLE: 0,
        ChangeKind.ADDED_COLUMN: 1,
        ChangeKind.MODIFIED_COLUMN: 2,
        ChangeKind.REMOVED_COLUMN: 3,
        ChangeKind.REMOVED_TABLE: 4,
    }
    changes.sort(key=lambda c: (order[c.kind], c.target))
    return DiffResult(changes=tuple(changes))

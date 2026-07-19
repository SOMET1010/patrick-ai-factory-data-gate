"""Columns check: verify presence, type, nullability, precision and default."""

from __future__ import annotations

from datagate.contract import ColumnSpec, Contract
from datagate.models import Column, Schema
from datagate.report import Finding, Severity

# Common aliases so a contract can use a friendly type name and still match the
# canonical name reported by ``information_schema.columns``.
_TYPE_ALIASES: dict[str, str] = {
    "int": "integer",
    "int4": "integer",
    "int8": "bigint",
    "int2": "smallint",
    "serial": "integer",
    "bigserial": "bigint",
    "varchar": "character varying",
    "char": "character",
    "bool": "boolean",
    "timestamp": "timestamp without time zone",
    "timestamptz": "timestamp with time zone",
    "timetz": "time with time zone",
    "decimal": "numeric",
    "float8": "double precision",
    "float4": "real",
}


def _normalise_type(value: str) -> str:
    key = value.strip().lower()
    return _TYPE_ALIASES.get(key, key)


def _normalise_default(value: str | None) -> str | None:
    """Best-effort normalisation of a column default for comparison.

    Strips PostgreSQL type casts (``::text``) and surrounding quotes so that a
    contract can declare ``active`` and match a stored ``'active'::text``.
    """
    if value is None:
        return None
    text = value.strip()
    if "::" in text:
        text = text.split("::", 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1]
    return text.lower()


class ColumnsCheck:
    """Compare each contracted column against the live column definition."""

    name = "columns"

    def run(self, contract: Contract, schema: Schema) -> list[Finding]:
        findings: list[Finding] = []
        for table_spec in contract.structure:
            table = schema.table(table_spec.name)
            if table is None:
                # Missing tables are reported by StructureCheck; skip here to
                # avoid duplicate, redundant findings.
                continue

            for column_spec in table_spec.columns:
                column = table.column(column_spec.name)
                if column is None:
                    findings.append(
                        self._finding(
                            table_spec.name,
                            column_spec.name,
                            f"Expected column '{column_spec.name}' is missing "
                            f"from table '{table_spec.name}'.",
                        )
                    )
                    continue
                findings.extend(self._compare(table_spec.name, column_spec, column))
        return findings

    def _compare(self, table: str, spec: ColumnSpec, column: Column) -> list[Finding]:
        findings: list[Finding] = []
        qualified = f"{table}.{spec.name}"

        if spec.type is not None and _normalise_type(spec.type) != _normalise_type(
            column.data_type
        ):
            findings.append(
                self._finding(
                    table,
                    spec.name,
                    f"Column '{qualified}' has type '{column.data_type}', "
                    f"expected '{spec.type}'.",
                )
            )

        if spec.nullable is not None and spec.nullable != column.is_nullable:
            findings.append(
                self._finding(
                    table,
                    spec.name,
                    f"Column '{qualified}' nullability is {column.is_nullable}, "
                    f"expected {spec.nullable}.",
                )
            )

        for label, expected, actual in (
            ("max length", spec.max_length, column.char_max_length),
            ("precision", spec.precision, column.numeric_precision),
            ("scale", spec.scale, column.numeric_scale),
        ):
            if expected is not None and expected != actual:
                findings.append(
                    self._finding(
                        table,
                        spec.name,
                        f"Column '{qualified}' {label} is {actual}, "
                        f"expected {expected}.",
                    )
                )

        if spec.default is not None and _normalise_default(
            spec.default
        ) != _normalise_default(column.default):
            findings.append(
                self._finding(
                    table,
                    spec.name,
                    f"Column '{qualified}' default is {column.default!r}, "
                    f"expected {spec.default!r}.",
                )
            )

        return findings

    def _finding(self, table: str, column: str, message: str) -> Finding:
        return Finding(
            check=self.name,
            severity=Severity.ERROR,
            target=f"column:{table}.{column}",
            message=message,
        )

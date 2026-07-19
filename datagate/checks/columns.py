"""Columns check: verify column presence, data type and nullability."""

from __future__ import annotations

from datagate.contract import Contract
from datagate.models import Schema
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
                target = f"column:{table_spec.name}.{column_spec.name}"
                column = table.column(column_spec.name)
                if column is None:
                    findings.append(
                        Finding(
                            check=self.name,
                            severity=Severity.ERROR,
                            target=target,
                            message=(
                                f"Expected column '{column_spec.name}' is missing "
                                f"from table '{table_spec.name}'."
                            ),
                        )
                    )
                    continue

                if column_spec.type is not None:
                    expected = _normalise_type(column_spec.type)
                    actual = _normalise_type(column.data_type)
                    if expected != actual:
                        findings.append(
                            Finding(
                                check=self.name,
                                severity=Severity.ERROR,
                                target=target,
                                message=(
                                    f"Column '{table_spec.name}.{column_spec.name}' "
                                    f"has type '{column.data_type}', expected "
                                    f"'{column_spec.type}'."
                                ),
                            )
                        )

                if (
                    column_spec.nullable is not None
                    and column_spec.nullable != column.is_nullable
                ):
                    findings.append(
                        Finding(
                            check=self.name,
                            severity=Severity.ERROR,
                            target=target,
                            message=(
                                f"Column '{table_spec.name}.{column_spec.name}' "
                                f"nullability is {column.is_nullable}, expected "
                                f"{column_spec.nullable}."
                            ),
                        )
                    )
        return findings

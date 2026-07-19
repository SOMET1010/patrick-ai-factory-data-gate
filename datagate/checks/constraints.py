"""Constraints check: verify primary keys and foreign keys."""

from __future__ import annotations

from datagate.contract import Contract
from datagate.models import Schema, Table
from datagate.report import Finding, Severity


class ConstraintsCheck:
    """Verify that primary and foreign keys match the contract."""

    name = "constraints"

    def run(self, contract: Contract, schema: Schema) -> list[Finding]:
        findings: list[Finding] = []
        for table_spec in contract.structure:
            table = schema.table(table_spec.name)
            if table is None:
                continue
            findings.extend(self._check_primary_key(table_spec, table))
            findings.extend(self._check_foreign_keys(table_spec, table))
        return findings

    def _check_primary_key(self, table_spec, table: Table) -> list[Finding]:
        if not table_spec.primary_key:
            return []
        expected = tuple(table_spec.primary_key)
        if table.primary_key != expected:
            actual = ", ".join(table.primary_key) or "(none)"
            return [
                Finding(
                    check=self.name,
                    severity=Severity.ERROR,
                    target=f"primary_key:{table_spec.name}",
                    message=(
                        f"Table '{table_spec.name}' primary key is ({actual}), "
                        f"expected ({', '.join(expected)})."
                    ),
                )
            ]
        return []

    def _check_foreign_keys(self, table_spec, table: Table) -> list[Finding]:
        findings: list[Finding] = []
        for fk_spec in table_spec.foreign_keys:
            match = self._find_matching_fk(fk_spec, table)
            if match is None:
                columns = ", ".join(fk_spec.columns) or "(unspecified)"
                findings.append(
                    Finding(
                        check=self.name,
                        severity=Severity.ERROR,
                        target=f"foreign_key:{table_spec.name}({columns})",
                        message=(
                            f"Table '{table_spec.name}' is missing a foreign key on "
                            f"({columns}) referencing '{fk_spec.references_table}'."
                        ),
                    )
                )
        return findings

    @staticmethod
    def _find_matching_fk(fk_spec, table: Table):
        for actual in table.foreign_keys:
            if actual.referenced_table != fk_spec.references_table:
                continue
            if fk_spec.columns and tuple(fk_spec.columns) != actual.columns:
                continue
            if (
                fk_spec.references_columns
                and tuple(fk_spec.references_columns) != actual.referenced_columns
            ):
                continue
            return actual
        return None

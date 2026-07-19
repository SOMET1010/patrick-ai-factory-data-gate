"""Indexes check: verify that expected indexes exist."""

from __future__ import annotations

from datagate.contract import Contract
from datagate.models import Schema, Table
from datagate.report import Finding, Severity


class IndexesCheck:
    """Verify that each contracted index exists on its table."""

    name = "indexes"

    def run(self, contract: Contract, schema: Schema) -> list[Finding]:
        findings: list[Finding] = []
        for table_spec in contract.structure:
            table = schema.table(table_spec.name)
            if table is None:
                continue
            for index_spec in table_spec.indexes:
                if self._find_matching_index(index_spec, table) is None:
                    findings.append(self._missing_finding(table_spec.name, index_spec))
        return findings

    def _missing_finding(self, table_name: str, index_spec) -> Finding:
        if index_spec.name:
            descriptor = f"named '{index_spec.name}'"
        else:
            descriptor = f"on ({', '.join(index_spec.columns)})"
        unique = " unique" if index_spec.unique else ""
        return Finding(
            check=self.name,
            severity=Severity.ERROR,
            target=f"index:{table_name}",
            message=(f"Table '{table_name}' is missing a{unique} index {descriptor}."),
        )

    @staticmethod
    def _find_matching_index(index_spec, table: Table):
        for actual in table.indexes:
            if index_spec.name and actual.name != index_spec.name:
                continue
            if index_spec.columns and tuple(index_spec.columns) != actual.columns:
                continue
            if index_spec.unique and not actual.is_unique:
                continue
            return actual
        return None

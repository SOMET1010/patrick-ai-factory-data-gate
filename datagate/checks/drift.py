"""Drift check: detect objects present in the database but not in the contract.

This is the opposite direction of the other checks: instead of asking "is what I
declared present?", it asks "is anything present that I did not declare?". It is
governed by :class:`~datagate.contract.Settings` and is a no-op unless the
contract opts in, so partial contracts remain valid.
"""

from __future__ import annotations

from datagate.contract import Contract
from datagate.models import Schema
from datagate.report import Finding, Severity

_SEVERITY = {"error": Severity.ERROR, "warning": Severity.WARNING}


class DriftCheck:
    """Report unexpected tables and columns according to the contract policy."""

    name = "drift"

    def run(self, contract: Contract, schema: Schema) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._unexpected_tables(contract, schema))
        findings.extend(self._unexpected_columns(contract, schema))
        return findings

    def _unexpected_tables(self, contract: Contract, schema: Schema) -> list[Finding]:
        policy = contract.settings.unexpected_tables
        if policy == "ignore":
            return []
        declared = {spec.name for spec in contract.structure}
        return [
            Finding(
                check=self.name,
                severity=_SEVERITY[policy],
                target=f"table:{table.name}",
                message=(
                    f"Unexpected table '{table.name}' is present in schema "
                    f"'{schema.name}' but not declared in the contract."
                ),
            )
            for table in schema.tables
            if table.name not in declared
        ]

    def _unexpected_columns(self, contract: Contract, schema: Schema) -> list[Finding]:
        policy = contract.settings.unexpected_columns
        if policy == "ignore":
            return []
        findings: list[Finding] = []
        for spec in contract.structure:
            # Only tables whose columns are explicitly declared can be checked
            # for column drift; otherwise every column would look unexpected.
            if not spec.columns:
                continue
            table = schema.table(spec.name)
            if table is None:
                continue
            declared = {column.name for column in spec.columns}
            for column in table.columns:
                if column.name not in declared:
                    findings.append(
                        Finding(
                            check=self.name,
                            severity=_SEVERITY[policy],
                            target=f"column:{spec.name}.{column.name}",
                            message=(
                                f"Unexpected column '{column.name}' is present on "
                                f"table '{spec.name}' but not declared in the "
                                "contract."
                            ),
                        )
                    )
        return findings

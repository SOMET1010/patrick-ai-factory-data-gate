"""Audit check: enforce governance rules such as mandatory audit columns.

Typical use: require every business table to expose ``created_at`` / ``updated_at``
columns. The rule targets a table and lists the columns that must be present.
"""

from __future__ import annotations

from datagate.contract import Contract
from datagate.models import Schema
from datagate.report import Finding, Severity


class AuditCheck:
    """Verify that audit rules (required columns per table) are satisfied."""

    name = "audit"

    def run(self, contract: Contract, schema: Schema) -> list[Finding]:
        findings: list[Finding] = []
        for rule in contract.audit:
            table = schema.table(rule.table)
            if table is None:
                findings.append(
                    Finding(
                        check=self.name,
                        severity=Severity.ERROR,
                        target=f"table:{rule.table}",
                        message=(
                            f"Audited table '{rule.table}' is missing from schema "
                            f"'{schema.name}'."
                        ),
                    )
                )
                continue

            existing = set(table.column_names)
            for column in rule.required_columns:
                if column not in existing:
                    findings.append(
                        Finding(
                            check=self.name,
                            severity=Severity.ERROR,
                            target=f"column:{rule.table}.{column}",
                            message=(
                                f"Audit rule requires column '{column}' on table "
                                f"'{rule.table}', but it is missing."
                            ),
                        )
                    )
        return findings

"""Structure check: verify that expected tables exist in the schema."""

from __future__ import annotations

from datagate.contract import Contract
from datagate.models import Schema
from datagate.report import Finding, Severity


class StructureCheck:
    """Ensure every table declared in the contract exists in the database."""

    name = "structure"

    def run(self, contract: Contract, schema: Schema) -> list[Finding]:
        findings: list[Finding] = []
        for table_spec in contract.structure:
            if schema.table(table_spec.name) is None:
                findings.append(
                    Finding(
                        check=self.name,
                        severity=Severity.ERROR,
                        target=f"table:{table_spec.name}",
                        message=(
                            f"Expected table '{table_spec.name}' is missing from "
                            f"schema '{schema.name}'."
                        ),
                    )
                )
        return findings

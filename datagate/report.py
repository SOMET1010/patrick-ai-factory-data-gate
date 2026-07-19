"""Findings, report assembly and JSON serialisation.

A :class:`Finding` is a single discrepancy between the contract and the live
schema. A :class:`Report` aggregates the findings, computes an overall
:class:`Status` and knows how to serialise itself to the JSON artifact consumed
by CI/CD pipelines.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_REPORT_PATH = Path("artifacts/data-gate-result.json")


class Severity(StrEnum):
    """Severity of a single finding."""

    ERROR = "error"
    WARNING = "warning"


class Status(StrEnum):
    """Overall outcome of a verification run, mapped to a process exit code."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"

    @property
    def exit_code(self) -> int:
        return {Status.PASS: 0, Status.FAIL: 1, Status.ERROR: 2}[self]


@dataclass(frozen=True)
class Finding:
    """A single discrepancy discovered by a check."""

    check: str
    severity: Severity
    target: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "check": self.check,
            "severity": self.severity.value,
            "target": self.target,
            "message": self.message,
        }


@dataclass(frozen=True)
class Report:
    """The complete result of a verification run."""

    status: Status
    database: str
    schema: str
    findings: tuple[Finding, ...] = ()
    generated_at: str | None = None
    error: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.WARNING)

    @property
    def exit_code(self) -> int:
        return self.status.exit_code

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status.value,
            "database": self.database,
            "schema": self.schema,
            "summary": {
                "errors": self.error_count,
                "warnings": self.warning_count,
                "total": len(self.findings),
            },
            "findings": [finding.to_dict() for finding in self.findings],
        }
        if self.generated_at is not None:
            payload["generated_at"] = self.generated_at
        if self.error is not None:
            payload["error"] = self.error
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def write(self, path: str | Path = DEFAULT_REPORT_PATH) -> Path:
        """Write the report as JSON, creating parent directories as needed."""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.to_json() + "\n", encoding="utf-8")
        logger.info("Report written to %s", output)
        return output


def build_report(
    *,
    database: str,
    schema: str,
    findings: Sequence[Finding],
    generated_at: str | None = None,
    metadata: dict[str, object] | None = None,
) -> Report:
    """Assemble a report from findings and derive the overall status."""
    status = status_from_findings(findings)
    return Report(
        status=status,
        database=database,
        schema=schema,
        findings=tuple(findings),
        generated_at=generated_at,
        metadata=metadata or {},
    )


def error_report(
    *,
    database: str,
    schema: str,
    message: str,
    generated_at: str | None = None,
) -> Report:
    """Build a report describing a runtime error (exit code 2)."""
    return Report(
        status=Status.ERROR,
        database=database,
        schema=schema,
        findings=(),
        generated_at=generated_at,
        error=message,
    )


def status_from_findings(findings: Iterable[Finding]) -> Status:
    """PASS when there is no error-severity finding, otherwise FAIL."""
    for finding in findings:
        if finding.severity is Severity.ERROR:
            return Status.FAIL
    return Status.PASS


@dataclass(frozen=True)
class AggregateReport:
    """Result of verifying several contracts (e.g. a whole directory)."""

    results: tuple[tuple[str, Report], ...] = ()
    generated_at: str | None = None

    @property
    def status(self) -> Status:
        """Worst status across all contracts (ERROR > FAIL > PASS)."""
        statuses = {report.status for _, report in self.results}
        if Status.ERROR in statuses:
            return Status.ERROR
        if Status.FAIL in statuses:
            return Status.FAIL
        return Status.PASS

    @property
    def exit_code(self) -> int:
        return self.status.exit_code

    @property
    def passed(self) -> int:
        return sum(1 for _, r in self.results if r.status is Status.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for _, r in self.results if r.status is Status.FAIL)

    @property
    def errored(self) -> int:
        return sum(1 for _, r in self.results if r.status is Status.ERROR)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status.value,
            "summary": {
                "contracts": len(self.results),
                "passed": self.passed,
                "failed": self.failed,
                "errored": self.errored,
                "errors": sum(r.error_count for _, r in self.results),
                "warnings": sum(r.warning_count for _, r in self.results),
            },
            "reports": [
                {"contract": contract, **report.to_dict()}
                for contract, report in self.results
            ],
        }
        if self.generated_at is not None:
            payload["generated_at"] = self.generated_at
        return payload

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def write(self, path: str | Path = DEFAULT_REPORT_PATH) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.to_json() + "\n", encoding="utf-8")
        logger.info("Aggregate report written to %s", output)
        return output

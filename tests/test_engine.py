"""Tests for the verification engine."""

from __future__ import annotations

from datagate.contract import Contract
from datagate.engine import run_checks
from datagate.report import Finding, Severity
from tests.helpers import sample_schema


def _contract() -> Contract:
    return Contract.from_mapping(
        {"version": 1, "database": "db", "schema": "public", "structure": [], "audit": []}
    )


class _StubCheck:
    def __init__(self, name, findings=None, boom=False):
        self.name = name
        self._findings = findings or []
        self._boom = boom

    def run(self, contract, schema):
        if self._boom:
            raise RuntimeError("kaboom")
        return self._findings


def test_run_checks_aggregates() -> None:
    f1 = Finding(check="a", severity=Severity.ERROR, target="t1", message="m")
    f2 = Finding(check="b", severity=Severity.WARNING, target="t2", message="m")
    checks = [_StubCheck("a", [f1]), _StubCheck("b", [f2])]
    findings = run_checks(_contract(), sample_schema(), checks)
    assert findings == [f1, f2]


def test_run_checks_isolates_failures() -> None:
    good = Finding(check="ok", severity=Severity.ERROR, target="t", message="m")
    checks = [_StubCheck("boom", boom=True), _StubCheck("ok", [good])]
    # A raising check must not abort the run.
    findings = run_checks(_contract(), sample_schema(), checks)
    assert findings == [good]


def test_run_checks_uses_defaults_on_clean_schema() -> None:
    # Empty contract against a real schema yields no findings.
    assert run_checks(_contract(), sample_schema()) == []

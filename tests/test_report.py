"""Tests for findings, report assembly and serialisation."""

from __future__ import annotations

import json

from datagate.report import (
    Finding,
    Severity,
    Status,
    build_report,
    error_report,
    status_from_findings,
)


def _finding(severity: Severity) -> Finding:
    return Finding(check="c", severity=severity, target="t", message="m")


def test_status_exit_codes() -> None:
    assert Status.PASS.exit_code == 0
    assert Status.FAIL.exit_code == 1
    assert Status.ERROR.exit_code == 2


def test_status_from_findings() -> None:
    assert status_from_findings([]) is Status.PASS
    assert status_from_findings([_finding(Severity.WARNING)]) is Status.PASS
    assert status_from_findings([_finding(Severity.ERROR)]) is Status.FAIL


def test_build_report_counts_and_status() -> None:
    report = build_report(
        database="db",
        schema="public",
        findings=[_finding(Severity.ERROR), _finding(Severity.WARNING)],
    )
    assert report.status is Status.FAIL
    assert report.error_count == 1
    assert report.warning_count == 1
    assert report.exit_code == 1


def test_error_report() -> None:
    report = error_report(database="db", schema="public", message="boom")
    assert report.status is Status.ERROR
    assert report.exit_code == 2
    assert report.error == "boom"


def test_report_to_dict_is_json_serialisable() -> None:
    report = build_report(
        database="db",
        schema="public",
        findings=[_finding(Severity.ERROR)],
        generated_at="2026-01-01T00:00:00+00:00",
        metadata={"k": "v"},
    )
    payload = json.loads(report.to_json())
    assert payload["status"] == "fail"
    assert payload["summary"] == {"errors": 1, "warnings": 0, "total": 1}
    assert payload["findings"][0]["check"] == "c"
    assert payload["metadata"] == {"k": "v"}


def test_report_write(tmp_path) -> None:
    report = build_report(database="db", schema="public", findings=[])
    output = tmp_path / "nested" / "result.json"
    written = report.write(output)
    assert written == output
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["status"] == "pass"

"""Tests for the CLI adapter."""

from __future__ import annotations

import json

from datagate import cli
from datagate.report import Finding, Severity, build_report, error_report


def test_cli_pass_writes_report_and_returns_zero(tmp_path, monkeypatch, capsys) -> None:
    output = tmp_path / "result.json"
    report = build_report(database="db", schema="public", findings=[])
    monkeypatch.setattr(cli, "run", lambda *a, **k: report)

    code = cli.main(["contract.yaml", "-o", str(output)])

    assert code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["status"] == "pass"
    assert "[PASS]" in capsys.readouterr().out


def test_cli_fail_returns_one(tmp_path, monkeypatch) -> None:
    output = tmp_path / "result.json"
    finding = Finding(
        check="structure", severity=Severity.ERROR, target="table:x", message="missing"
    )
    report = build_report(database="db", schema="public", findings=[finding])
    monkeypatch.setattr(cli, "run", lambda *a, **k: report)

    assert cli.main(["contract.yaml", "-o", str(output)]) == 1


def test_cli_error_returns_two(tmp_path, monkeypatch) -> None:
    output = tmp_path / "result.json"
    report = error_report(database="db", schema="public", message="boom")
    monkeypatch.setattr(cli, "run", lambda *a, **k: report)

    assert cli.main(["contract.yaml", "-o", str(output)]) == 2


def test_cli_forwards_dsn(tmp_path, monkeypatch) -> None:
    output = tmp_path / "result.json"
    captured = {}

    def fake_run(contract_path, *, dsn=None, **kwargs):
        captured["contract"] = contract_path
        captured["dsn"] = dsn
        return build_report(database="db", schema="public", findings=[])

    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["my-contract.yaml", "--dsn", "postgres://x", "-o", str(output)])

    assert captured["contract"] == "my-contract.yaml"
    assert captured["dsn"] == "postgres://x"


def test_cli_contract_only(tmp_path, monkeypatch) -> None:
    output = tmp_path / "result.json"
    captured = {}

    def fake_validate(path):
        captured["path"] = path
        return build_report(database="db", schema="public", findings=[])

    # --contract-only must call validate_contract, never run()
    monkeypatch.setattr(cli, "validate_contract", fake_validate)
    monkeypatch.setattr(
        cli, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("run called"))
    )
    code = cli.main(["c.yaml", "--contract-only", "-o", str(output)])
    assert code == 0
    assert captured["path"] == "c.yaml"

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


def test_cli_generate_writes_contract(tmp_path, monkeypatch) -> None:
    out = tmp_path / "hermes.yaml"
    monkeypatch.setattr(
        cli, "generate_contract", lambda **k: ("hermes", "# draft\nversion: 1\n")
    )
    code = cli.main(["generate", "--dsn", "postgres://x", "-o", str(out)])
    assert code == 0
    assert out.read_text(encoding="utf-8").startswith("# draft")


def test_cli_generate_error_returns_two(monkeypatch, capsys) -> None:
    from datagate.exceptions import DatabaseConnectionError

    def boom(**k):
        raise DatabaseConnectionError("no db")

    monkeypatch.setattr(cli, "generate_contract", boom)
    assert cli.main(["generate", "--dsn", "x"]) == 2


def test_cli_legacy_form_routes_to_verify(tmp_path, monkeypatch) -> None:
    # `datagate <contract>` (no subcommand) must behave like `verify`.
    output = tmp_path / "r.json"
    called = {}

    def fake_run(contract_path, *, dsn=None, **k):
        called["contract"] = contract_path
        return build_report(database="db", schema="public", findings=[])

    monkeypatch.setattr(cli, "run", fake_run)
    assert cli.main(["legacy.yaml", "-o", str(output)]) == 0
    assert called["contract"] == "legacy.yaml"


def test_cli_verify_directory(tmp_path, monkeypatch) -> None:
    from datagate.report import build_report as _build

    output = tmp_path / "agg.json"
    results = [
        ("contracts/a.yaml", _build(database="d", schema="s", findings=[])),
        (
            "contracts/b.yaml",
            _build(
                database="d",
                schema="s",
                findings=[
                    Finding(
                        check="structure",
                        severity=Severity.ERROR,
                        target="table:x",
                        message="missing",
                    )
                ],
            ),
        ),
    ]
    monkeypatch.setattr(cli, "run_directory", lambda *a, **k: results)
    # target must be a real directory so is_dir() is True
    code = cli.main(["verify", str(tmp_path), "-o", str(output)])
    assert code == 1  # one contract failed -> aggregate FAIL
    import json

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["summary"]["contracts"] == 2
    assert data["summary"]["failed"] == 1


def test_cli_verify_empty_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cli, "run_directory", lambda *a, **k: [])
    assert cli.main(["verify", str(tmp_path)]) == 2


def test_cli_diff_files(tmp_path, capsys) -> None:
    src = tmp_path / "v1.yaml"
    dst = tmp_path / "v2.yaml"
    src.write_text(
        "version: 1\ndatabase: d\nschema: public\naudit: []\n"
        "structure:\n  - table: users\n    columns:\n      - name: id\n",
        encoding="utf-8",
    )
    dst.write_text(
        "version: 1\ndatabase: d\nschema: public\naudit: []\n"
        "structure:\n  - table: users\n    columns:\n      - name: id\n"
        "  - table: audit_log\n    columns:\n      - name: id\n",
        encoding="utf-8",
    )
    # audit_log added -> SAFE -> exit 0
    assert cli.main(["diff", str(src), str(dst)]) == 0
    assert "+ audit_log" in capsys.readouterr().out


def test_cli_diff_breaking_exit_one(tmp_path) -> None:
    src = tmp_path / "v1.yaml"
    dst = tmp_path / "v2.yaml"
    src.write_text(
        "version: 1\ndatabase: d\nschema: public\naudit: []\n"
        "structure:\n  - table: users\n    columns:\n      - name: id\n",
        encoding="utf-8",
    )
    # users table removed -> breaking -> exit 1
    dst.write_text(
        "version: 1\ndatabase: d\nschema: public\naudit: []\nstructure: []\n",
        encoding="utf-8",
    )
    assert cli.main(["diff", str(src), str(dst)]) == 1


def test_cli_diff_error_exit_two(tmp_path) -> None:
    src = tmp_path / "v1.yaml"
    src.write_text(
        "version: 1\ndatabase: d\nschema: public\naudit: []\nstructure: []\n",
        encoding="utf-8",
    )
    # target missing file and not a DSN -> resolve tries DSN -> ConfigurationError
    assert cli.main(["diff", str(src), "/tmp/nope-not-a-file.yaml"]) == 2


def test_cli_report_html(tmp_path) -> None:
    import json as _json

    report_json = tmp_path / "result.json"
    report_json.write_text(
        _json.dumps(
            {
                "status": "pass",
                "database": "d",
                "schema": "public",
                "summary": {"errors": 0, "warnings": 0, "total": 0},
                "findings": [],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "report.html"
    assert cli.main(["report", str(report_json), "--format", "html", "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_cli_report_md(tmp_path) -> None:
    import json as _json

    report_json = tmp_path / "result.json"
    report_json.write_text(
        _json.dumps(
            {
                "status": "fail",
                "database": "d",
                "schema": "public",
                "summary": {"errors": 1, "warnings": 0, "total": 1},
                "findings": [
                    {"check": "c", "severity": "error", "target": "t", "message": "m"}
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    assert cli.main(["report", str(report_json), "--format", "md", "-o", str(out)]) == 0
    assert "# Data Gate Report" in out.read_text(encoding="utf-8")


def test_cli_report_missing_input_exit_two(tmp_path) -> None:
    assert cli.main(["report", str(tmp_path / "nope.json")]) == 2

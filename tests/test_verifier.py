"""Integration tests for the verifier orchestration."""

from __future__ import annotations

from contextlib import contextmanager

from datagate import verifier
from datagate.exceptions import DatabaseConnectionError
from datagate.report import Status
from tests.helpers import FakeConnection

PASS_CONTRACT = """
version: 1
database: db
schema: public
structure:
  - table: users
    columns:
      - name: id
        type: integer
        nullable: false
audit:
  - table: users
    required_columns: [id]
"""

FAIL_CONTRACT = """
version: 1
database: db
schema: public
structure:
  - table: ghost
audit: []
"""

FAKE_ROWS = {
    "tables": [("users", "BASE TABLE")],
    "columns": [("users", "id", "integer", "NO", None, 1, None, 32, 0)],
    "primary_keys": [("users", "id")],
    "foreign_keys": [],
    "indexes": [],
}


def _patch_connection(monkeypatch, connection) -> None:
    @contextmanager
    def fake_connect(dsn=None):
        yield connection

    monkeypatch.setattr(verifier, "connect", fake_connect)


def test_verifier_pass(tmp_path, monkeypatch) -> None:
    contract = tmp_path / "c.yaml"
    contract.write_text(PASS_CONTRACT, encoding="utf-8")
    _patch_connection(monkeypatch, FakeConnection(FAKE_ROWS))

    report = verifier.run(contract, dsn="ignored")
    assert report.status is Status.PASS
    assert report.exit_code == 0
    assert report.metadata["tables_checked"] == 1


def test_verifier_fail(tmp_path, monkeypatch) -> None:
    contract = tmp_path / "c.yaml"
    contract.write_text(FAIL_CONTRACT, encoding="utf-8")
    _patch_connection(monkeypatch, FakeConnection(FAKE_ROWS))

    report = verifier.run(contract, dsn="ignored")
    assert report.status is Status.FAIL
    assert report.exit_code == 1
    assert any(f.target == "table:ghost" for f in report.findings)


def test_verifier_contract_error(tmp_path) -> None:
    report = verifier.run(tmp_path / "missing.yaml")
    assert report.status is Status.ERROR
    assert report.exit_code == 2
    assert "not found" in (report.error or "")


def test_verifier_connection_error(tmp_path, monkeypatch) -> None:
    contract = tmp_path / "c.yaml"
    contract.write_text(PASS_CONTRACT, encoding="utf-8")

    @contextmanager
    def boom(dsn=None):
        raise DatabaseConnectionError("cannot connect")
        yield  # pragma: no cover

    monkeypatch.setattr(verifier, "connect", boom)

    report = verifier.run(contract, dsn="ignored")
    assert report.status is Status.ERROR
    assert report.exit_code == 2
    assert "cannot connect" in (report.error or "")


def test_validate_contract_valid(tmp_path) -> None:
    contract = tmp_path / "c.yaml"
    contract.write_text(PASS_CONTRACT, encoding="utf-8")
    report = verifier.validate_contract(contract)
    assert report.status is Status.PASS
    assert report.exit_code == 0
    assert report.metadata["mode"] == "contract-only"


def test_validate_contract_invalid(tmp_path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: 1\n", encoding="utf-8")  # missing required keys
    report = verifier.validate_contract(bad)
    assert report.status is Status.ERROR
    assert report.exit_code == 2

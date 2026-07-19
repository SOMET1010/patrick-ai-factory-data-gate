"""High-level orchestration of a verification run.

This is the application service that ties the layers together: load the contract,
open a read-only connection, introspect the schema, run the checks and assemble a
report. Keeping it here (rather than in the CLI) means the CLI stays a thin
adapter and the whole flow can be driven directly from tests or other tools.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from datagate.checks import Check
from datagate.contract import Contract
from datagate.db import connect
from datagate.engine import run_checks
from datagate.exceptions import ContractError, DataGateError
from datagate.generator import contract_from_schema, dump_contract
from datagate.introspect import Introspector
from datagate.report import Report, build_report, error_report

logger = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def run(
    contract_path: str | Path,
    *,
    dsn: str | None = None,
    checks: Sequence[Check] | None = None,
) -> Report:
    """Execute a full verification and return a :class:`Report`.

    Never raises for expected failures: contract, configuration, connection and
    introspection problems are captured and returned as an ``ERROR`` report
    (exit code 2), so callers always get a serialisable result.
    """
    generated_at = _timestamp()

    try:
        contract = Contract.from_file(contract_path)
    except ContractError as exc:
        logger.error("Contract error: %s", exc)
        return error_report(
            database="unknown",
            schema="unknown",
            message=str(exc),
            generated_at=generated_at,
        )

    try:
        with connect(dsn) as connection:
            schema = Introspector(connection).introspect(contract.schema)
    except DataGateError as exc:
        logger.error("%s", exc)
        return error_report(
            database=contract.database,
            schema=contract.schema,
            message=str(exc),
            generated_at=generated_at,
        )

    findings = run_checks(contract, schema, checks)
    report = build_report(
        database=contract.database,
        schema=contract.schema,
        findings=findings,
        generated_at=generated_at,
        metadata={
            "contract_version": contract.version,
            "tables_checked": len(contract.structure),
            "audit_rules": len(contract.audit),
        },
    )
    logger.info(
        "Verification %s: %d error(s), %d warning(s)",
        report.status.value.upper(),
        report.error_count,
        report.warning_count,
    )
    return report


def find_contracts(directory: str | Path) -> list[Path]:
    """Return the ``*.yaml`` / ``*.yml`` files under ``directory``, sorted.

    Recurses into subdirectories. The order is deterministic so reports are
    stable across runs.
    """
    root = Path(directory)
    files = {p for p in root.rglob("*.yaml")} | {p for p in root.rglob("*.yml")}
    return sorted(f for f in files if f.is_file())


def run_directory(
    directory: str | Path,
    *,
    dsn: str | None = None,
    checks: Sequence[Check] | None = None,
    contract_only: bool = False,
) -> list[tuple[str, Report]]:
    """Verify every contract found under ``directory``.

    Returns a list of ``(contract_path, report)`` in deterministic order. Each
    contract is independent: an ERROR on one does not stop the others.
    """
    results: list[tuple[str, Report]] = []
    for contract_path in find_contracts(directory):
        if contract_only:
            report = validate_contract(contract_path)
        else:
            report = run(contract_path, dsn=dsn, checks=checks)
        results.append((str(contract_path), report))
    return results


def validate_contract(contract_path: str | Path) -> Report:
    """Validate a contract file without touching any database.

    Useful as a fast CI lint (exit ``0`` when the contract is well-formed,
    ``2`` when it is malformed) before a database is available.
    """
    generated_at = _timestamp()
    try:
        contract = Contract.from_file(contract_path)
    except ContractError as exc:
        logger.error("Contract error: %s", exc)
        return error_report(
            database="unknown",
            schema="unknown",
            message=str(exc),
            generated_at=generated_at,
        )

    logger.info("Contract '%s' is valid (contract-only mode)", contract_path)
    return build_report(
        database=contract.database,
        schema=contract.schema,
        findings=[],
        generated_at=generated_at,
        metadata={
            "mode": "contract-only",
            "contract_version": contract.version,
            "tables_declared": len(contract.structure),
            "audit_rules": len(contract.audit),
        },
    )


def generate_contract(
    *,
    dsn: str | None = None,
    schema_name: str = "public",
) -> tuple[str, str]:
    """Introspect a live schema and return ``(database, yaml_contract)``.

    Read-only: the same introspection engine used by ``verify`` is reused here,
    so ``generate`` and ``verify`` can never diverge in how they read the schema.
    Raises :class:`~datagate.exceptions.DataGateError` on any failure.
    """
    with connect(dsn) as connection:
        introspector = Introspector(connection)
        database = introspector.current_database()
        schema = introspector.introspect(schema_name)

    mapping = contract_from_schema(schema, database)
    logger.info(
        "Generated contract for %s/%s: %d table(s)",
        database,
        schema_name,
        len(schema.tables),
    )
    return database, dump_contract(mapping)

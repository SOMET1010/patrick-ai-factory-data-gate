"""Command-line entry point for the Data Gate.

Thin adapter: parse arguments, configure logging, delegate to
:mod:`datagate.verifier`, persist the JSON report and translate the outcome into
a process exit code.

    Exit codes:
        0  PASS   – the schema conforms to the contract
        1  FAIL   – at least one conformance error was found
        2  ERROR  – the run could not be completed (bad contract, no DB, ...)
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from datagate import __version__
from datagate.report import DEFAULT_REPORT_PATH, Report, Status
from datagate.verifier import run, validate_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datagate",
        description="Read-only PostgreSQL schema conformance checker.",
    )
    parser.add_argument(
        "contract",
        help="Path to the YAML contract describing the expected schema.",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL DSN. Defaults to the DATAGATE_DSN environment variable.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_REPORT_PATH),
        help=f"Path to the JSON report (default: {DEFAULT_REPORT_PATH}).",
    )
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="Validate the contract only, without connecting to a database.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _print_summary(report: Report) -> None:
    print(f"[{report.status.value.upper()}] {report.database}/{report.schema}")
    if report.error:
        print(f"  error: {report.error}")
    for finding in report.findings:
        print(f"  [{finding.severity.value}] {finding.target}: {finding.message}")
    if report.findings:
        print(f"  {report.error_count} error(s), {report.warning_count} warning(s)")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.contract_only:
        report = validate_contract(args.contract)
    else:
        report = run(args.contract, dsn=args.dsn)

    try:
        report.write(args.output)
    except OSError as exc:  # pragma: no cover - filesystem edge case
        print(f"ERROR: could not write report to {args.output}: {exc}", file=sys.stderr)
        return Status.ERROR.exit_code

    _print_summary(report)
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

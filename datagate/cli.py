"""Command-line entry point for the Data Gate.

Subcommand CLI (thin adapter — no business logic):

    datagate verify   <contract> [--dsn ...] [-o ...] [--contract-only]
    datagate generate [--dsn ...] [--schema public] [-o path]

For backward compatibility, the legacy form ``datagate <contract> [...]`` (no
subcommand) is treated as ``datagate verify <contract> [...]``.

    Exit codes:
        0  PASS   – schema conforms / contract valid / contract generated
        1  FAIL   – at least one conformance error was found
        2  ERROR  – the run could not be completed
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from datagate import __version__
from datagate.exceptions import DataGateError
from datagate.report import DEFAULT_REPORT_PATH, AggregateReport, Report, Status
from datagate.verifier import generate_contract, run, run_directory, validate_contract

SUBCOMMANDS = ("verify", "generate")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datagate",
        description="Read-only PostgreSQL schema governance tool.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # -- verify -----------------------------------------------------------------
    verify = subparsers.add_parser(
        "verify", help="Verify a live schema against a YAML contract."
    )
    verify.add_argument(
        "contract",
        help="Path to a YAML contract, or a directory of contracts (*.yaml/*.yml).",
    )
    verify.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL DSN. Defaults to the DATAGATE_DSN environment variable.",
    )
    verify.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_REPORT_PATH),
        help=f"Path to the JSON report (default: {DEFAULT_REPORT_PATH}).",
    )
    verify.add_argument(
        "--contract-only",
        action="store_true",
        help="Validate the contract only, without connecting to a database.",
    )
    verify.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging."
    )

    # -- generate ---------------------------------------------------------------
    generate = subparsers.add_parser(
        "generate", help="Generate a draft contract from a live schema."
    )
    generate.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL DSN. Defaults to the DATAGATE_DSN environment variable.",
    )
    generate.add_argument(
        "--schema", default="public", help="Schema to introspect (default: public)."
    )
    generate.add_argument(
        "-o",
        "--output",
        default=None,
        help="Where to write the contract (default: contracts/<database>.yaml).",
    )
    generate.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose (DEBUG) logging."
    )

    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _normalise_argv(argv: Sequence[str] | None) -> list[str]:
    """Insert the implicit ``verify`` subcommand for the legacy invocation."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return args
    first = args[0]
    if first in SUBCOMMANDS or first in ("-h", "--help", "--version"):
        return args
    # Legacy form: `datagate <contract> [...]` -> `datagate verify <contract> [...]`
    return ["verify", *args]


def _print_summary(report: Report) -> None:
    print(f"[{report.status.value.upper()}] {report.database}/{report.schema}")
    if report.error:
        print(f"  error: {report.error}")
    for finding in report.findings:
        print(f"  [{finding.severity.value}] {finding.target}: {finding.message}")
    if report.findings:
        print(f"  {report.error_count} error(s), {report.warning_count} warning(s)")


def _cmd_verify(args: argparse.Namespace) -> int:
    if Path(args.contract).is_dir():
        return _verify_directory(args)

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


def _verify_directory(args: argparse.Namespace) -> int:
    results = run_directory(args.contract, dsn=args.dsn, contract_only=args.contract_only)
    if not results:
        print(f"ERROR: no contracts (*.yaml/*.yml) found in {args.contract}")
        return Status.ERROR.exit_code

    aggregate = AggregateReport(results=tuple(results))
    try:
        aggregate.write(args.output)
    except OSError as exc:  # pragma: no cover - filesystem edge case
        print(f"ERROR: could not write report to {args.output}: {exc}", file=sys.stderr)
        return Status.ERROR.exit_code

    for contract, report in results:
        location = f"{report.database}/{report.schema}"
        print(f"[{report.status.value.upper()}] {contract} ({location})")
        for finding in report.findings:
            print(f"    [{finding.severity.value}] {finding.target}: {finding.message}")
        if report.error:
            print(f"    error: {report.error}")
    print(
        f"== {aggregate.status.value.upper()}: {len(results)} contract(s) — "
        f"{aggregate.passed} passed, {aggregate.failed} failed, "
        f"{aggregate.errored} errored =="
    )
    return aggregate.exit_code


def _cmd_generate(args: argparse.Namespace) -> int:
    try:
        database, yaml_text = generate_contract(dsn=args.dsn, schema_name=args.schema)
    except DataGateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return Status.ERROR.exit_code

    output = Path(args.output) if args.output else Path("contracts") / f"{database}.yaml"
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(yaml_text, encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem edge case
        print(f"ERROR: could not write contract to {output}: {exc}", file=sys.stderr)
        return Status.ERROR.exit_code

    print(f"[OK] contract written to {output}")
    return Status.PASS.exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_normalise_argv(argv))

    if args.command is None:
        parser.print_help()
        return Status.ERROR.exit_code

    _configure_logging(args.verbose)

    if args.command == "generate":
        return _cmd_generate(args)
    return _cmd_verify(args)


if __name__ == "__main__":
    raise SystemExit(main())

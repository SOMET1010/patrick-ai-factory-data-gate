"""Verification engine.

Runs a collection of independent checks against the introspected schema and
returns the aggregated findings. The engine owns no comparison logic itself: it
only orchestrates the checks, which keeps each concern isolated and testable.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from datagate.checks import Check, default_checks
from datagate.contract import Contract
from datagate.models import Schema
from datagate.report import Finding

logger = logging.getLogger(__name__)


def run_checks(
    contract: Contract,
    schema: Schema,
    checks: Sequence[Check] | None = None,
) -> list[Finding]:
    """Run every check and return the concatenated findings.

    ``checks`` defaults to :func:`datagate.checks.default_checks`. Each check is
    isolated: a failure in one check is logged and turned into no findings rather
    than aborting the whole run.
    """
    active_checks = list(checks) if checks is not None else default_checks()
    findings: list[Finding] = []

    for check in active_checks:
        logger.debug("Running check '%s'", check.name)
        try:
            check_findings = check.run(contract, schema)
        except Exception:  # noqa: BLE001 - one bad check must not sink the run
            logger.exception("Check '%s' raised an unexpected error", check.name)
            continue
        logger.debug("Check '%s' produced %d finding(s)", check.name, len(check_findings))
        findings.extend(check_findings)

    return findings

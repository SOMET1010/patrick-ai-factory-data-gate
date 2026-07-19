"""Verification checks package.

Each check is an autonomous unit implementing the :class:`Check` protocol.
:func:`default_checks` returns the ordered list of checks run by the engine.
"""

from __future__ import annotations

from datagate.checks.audit import AuditCheck
from datagate.checks.base import Check
from datagate.checks.columns import ColumnsCheck
from datagate.checks.constraints import ConstraintsCheck
from datagate.checks.drift import DriftCheck
from datagate.checks.indexes import IndexesCheck
from datagate.checks.structure import StructureCheck

__all__ = [
    "Check",
    "StructureCheck",
    "ColumnsCheck",
    "ConstraintsCheck",
    "IndexesCheck",
    "AuditCheck",
    "DriftCheck",
    "default_checks",
]


def default_checks() -> list[Check]:
    """Return a fresh list of the checks executed on every run."""
    return [
        StructureCheck(),
        ColumnsCheck(),
        ConstraintsCheck(),
        IndexesCheck(),
        AuditCheck(),
        DriftCheck(),
    ]

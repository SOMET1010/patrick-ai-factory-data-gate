"""Shared contract for verification checks.

A *check* is an autonomous unit that compares one aspect of the contract against
the introspected schema and yields :class:`~datagate.report.Finding` objects.
Checks are independent and stateless, which keeps the design open for extension
(add a module, register it) and closed for modification (existing checks stay
untouched).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from datagate.contract import Contract
from datagate.models import Schema
from datagate.report import Finding


@runtime_checkable
class Check(Protocol):
    """A single, self-contained verification."""

    #: Stable identifier used in findings and reports.
    name: str

    def run(self, contract: Contract, schema: Schema) -> list[Finding]:
        """Return the findings produced by comparing ``contract`` to ``schema``."""
        ...

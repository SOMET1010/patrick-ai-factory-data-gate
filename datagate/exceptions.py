"""Dedicated exception hierarchy for the Data Gate.

All errors raised by the application inherit from :class:`DataGateError`, which
makes it easy for the CLI to distinguish an expected, well-described failure
(mapped to exit code ``2 ERROR``) from an unexpected crash.
"""

from __future__ import annotations


class DataGateError(Exception):
    """Base class for every error raised by the Data Gate."""


class ConfigurationError(DataGateError):
    """Raised when the runtime configuration is missing or invalid.

    Typical cause: the ``DATAGATE_DSN`` environment variable is not set.
    """


class ContractError(DataGateError):
    """Raised when a contract file cannot be read or is malformed."""


class DatabaseConnectionError(DataGateError):
    """Raised when the read-only connection to PostgreSQL cannot be opened."""


class IntrospectionError(DataGateError):
    """Raised when the live schema cannot be read from the database."""

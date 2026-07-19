"""Read-only PostgreSQL connection management.

This module is the *only* place that talks to psycopg. It guarantees that every
connection opened by the Data Gate is read-only, so the tool can never mutate
the database it inspects.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from datagate.exceptions import ConfigurationError, DatabaseConnectionError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from psycopg import Connection

logger = logging.getLogger(__name__)

DSN_ENV_VAR = "DATAGATE_DSN"


def get_dsn(explicit: str | None = None) -> str:
    """Return the DSN to use.

    Precedence: an explicit value (e.g. a CLI flag) wins, otherwise the
    ``DATAGATE_DSN`` environment variable is used.

    Raises :class:`ConfigurationError` when no DSN is available.
    """
    dsn = explicit or os.environ.get(DSN_ENV_VAR)
    if not dsn:
        raise ConfigurationError(
            f"No database DSN provided. Set the {DSN_ENV_VAR} environment "
            "variable or pass --dsn."
        )
    return dsn


@contextmanager
def connect(dsn: str | None = None) -> Iterator[Connection]:
    """Open a strictly read-only connection to PostgreSQL.

    The connection is configured as read-only *before* any query runs, and is
    always closed when the context manager exits. Any failure to connect is
    surfaced as :class:`DatabaseConnectionError`.
    """
    resolved = get_dsn(dsn)

    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - dependency guaranteed by packaging
        raise DatabaseConnectionError(
            "psycopg is not installed; install the package dependencies first."
        ) from exc

    logger.debug("Opening read-only connection to PostgreSQL")
    try:
        connection = psycopg.connect(resolved)
    except psycopg.Error as exc:
        raise DatabaseConnectionError(f"Unable to connect to PostgreSQL: {exc}") from exc

    try:
        # Enforce read-only at the session level so that no statement issued
        # through this connection can ever write to the database. Defense in
        # depth: the ``read_only`` attribute alone is NOT honoured under
        # autocommit, so we also set ``default_transaction_read_only`` which
        # makes every implicit transaction reject writes (even for superusers).
        connection.autocommit = True
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("SET default_transaction_read_only = on")
        yield connection
    except psycopg.Error as exc:
        raise DatabaseConnectionError(
            f"Failed to configure read-only session: {exc}"
        ) from exc
    finally:
        connection.close()
        logger.debug("Closed PostgreSQL connection")

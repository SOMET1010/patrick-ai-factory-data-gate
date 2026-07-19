"""Tests for DSN resolution (no live database required)."""

from __future__ import annotations

import pytest

from datagate.db import DSN_ENV_VAR, get_dsn
from datagate.exceptions import ConfigurationError


def test_get_dsn_prefers_explicit(monkeypatch) -> None:
    monkeypatch.setenv(DSN_ENV_VAR, "from-env")
    assert get_dsn("explicit") == "explicit"


def test_get_dsn_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv(DSN_ENV_VAR, "from-env")
    assert get_dsn() == "from-env"


def test_get_dsn_missing_raises(monkeypatch) -> None:
    monkeypatch.delenv(DSN_ENV_VAR, raising=False)
    with pytest.raises(ConfigurationError, match="No database DSN"):
        get_dsn()

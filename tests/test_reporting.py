"""Tests for the report renderer."""

from __future__ import annotations

from datagate.reporting import (
    conformance_score,
    render_html,
    render_markdown,
    score_of,
)

SINGLE_PASS = {
    "status": "pass",
    "database": "hermes",
    "schema": "public",
    "summary": {"errors": 0, "warnings": 0, "total": 0},
    "findings": [],
}

SINGLE_FAIL = {
    "status": "fail",
    "database": "hermes",
    "schema": "public",
    "summary": {"errors": 2, "warnings": 1, "total": 3},
    "findings": [
        {
            "check": "structure",
            "severity": "error",
            "target": "table:orders",
            "message": "missing",
        }
    ],
}

AGGREGATE = {
    "status": "fail",
    "summary": {
        "contracts": 2,
        "passed": 1,
        "failed": 1,
        "errored": 0,
        "errors": 2,
        "warnings": 0,
    },
    "reports": [
        {"contract": "a.yaml", **SINGLE_PASS},
        {"contract": "b.yaml", **SINGLE_FAIL},
    ],
}


def test_conformance_score_formula() -> None:
    assert conformance_score("pass", 0, 0) == 100
    assert conformance_score("error", 5, 5) == 0
    assert conformance_score("fail", 2, 1) == 100 - 20 - 2  # 78
    assert conformance_score("fail", 50, 0) == 0  # clamped


def test_score_of_single_and_aggregate() -> None:
    assert score_of(SINGLE_PASS) == 100
    assert score_of(SINGLE_FAIL) == 78
    # aggregate mean of (100, 78) = 89
    assert score_of(AGGREGATE) == 89


def test_render_markdown_single() -> None:
    md = render_markdown(SINGLE_FAIL)
    assert "# Data Gate Report — hermes/public" in md
    assert "**Status:** FAIL" in md
    assert "78%" in md
    assert "table:orders" in md


def test_render_markdown_aggregate() -> None:
    md = render_markdown(AGGREGATE)
    assert "# Data Gate Report" in md
    assert "89%" in md
    assert "a.yaml" in md and "b.yaml" in md


def test_render_html_is_self_contained() -> None:
    html_out = render_html(SINGLE_FAIL)
    assert html_out.startswith("<!doctype html>")
    assert "<style>" in html_out  # inlined CSS, no external deps
    assert "http://" not in html_out and "https://" not in html_out
    assert "FAIL" in html_out and "78%" in html_out


def test_render_html_escapes() -> None:
    report = {
        "status": "fail",
        "database": "d",
        "schema": "s",
        "summary": {"errors": 1, "warnings": 0},
        "findings": [
            {
                "check": "c",
                "severity": "error",
                "target": "t",
                "message": "<script>alert(1)</script>",
            }
        ],
    }
    html_out = render_html(report)
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out

"""Render a Data Gate JSON report as Markdown or HTML.

Works on the JSON produced by ``datagate verify`` — both a single-contract
report and an aggregate (directory) report. A *conformance score* is derived so
the result is easy to scan in a review or an audit.

The score is intentionally simple and explainable:

* ``PASS``  -> 100
* ``ERROR`` -> 0
* ``FAIL``  -> ``max(0, 100 - 10*errors - 2*warnings)``

For an aggregate report the score is the mean of the per-contract scores.
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any


def conformance_score(status: str, errors: int, warnings: int) -> int:
    status = status.lower()
    if status == "pass":
        return 100
    if status == "error":
        return 0
    return max(0, 100 - 10 * errors - 2 * warnings)


def _is_aggregate(report: Mapping[str, Any]) -> bool:
    return "reports" in report


def _single_score(report: Mapping[str, Any]) -> int:
    summary = report.get("summary", {})
    return conformance_score(
        str(report.get("status", "error")),
        int(summary.get("errors", 0)),
        int(summary.get("warnings", 0)),
    )


def score_of(report: Mapping[str, Any]) -> int:
    """Overall conformance score for a single or aggregate report."""
    if not _is_aggregate(report):
        return _single_score(report)
    reports = report.get("reports") or []
    if not reports:
        return 100
    return round(sum(_single_score(r) for r in reports) / len(reports))


# --- Markdown -----------------------------------------------------------------


def _md_findings(findings: list[Mapping[str, Any]]) -> list[str]:
    if not findings:
        return ["_No findings._", ""]
    lines = ["| Severity | Check | Target | Message |", "| --- | --- | --- | --- |"]
    for f in findings:
        lines.append(
            f"| {f.get('severity', '')} | {f.get('check', '')} "
            f"| `{f.get('target', '')}` | {f.get('message', '')} |"
        )
    lines.append("")
    return lines


def render_markdown(report: Mapping[str, Any]) -> str:
    score = score_of(report)
    lines: list[str] = []

    if _is_aggregate(report):
        summary = report.get("summary", {})
        lines.append("# Data Gate Report")
        lines.append("")
        lines.append(f"**Overall status:** {str(report.get('status', '')).upper()}")
        lines.append(f"**Conformance score:** {score}%")
        lines.append(
            f"**Contracts:** {summary.get('contracts', 0)} "
            f"({summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed, "
            f"{summary.get('errored', 0)} errored)"
        )
        lines.append("")
        lines.append("| Contract | Status | Errors | Warnings |")
        lines.append("| --- | --- | --- | --- |")
        for r in report.get("reports") or []:
            s = r.get("summary", {})
            lines.append(
                f"| {r.get('contract', '')} | {str(r.get('status', '')).upper()} "
                f"| {s.get('errors', 0)} | {s.get('warnings', 0)} |"
            )
        lines.append("")
        for r in report.get("reports") or []:
            if r.get("findings"):
                lines.append(f"## {r.get('contract', '')}")
                lines.extend(_md_findings(list(r.get("findings") or [])))
        return "\n".join(lines).rstrip() + "\n"

    summary = report.get("summary", {})
    lines.append(
        f"# Data Gate Report — {report.get('database', '')}/{report.get('schema', '')}"
    )
    lines.append("")
    lines.append(f"**Status:** {str(report.get('status', '')).upper()}")
    lines.append(f"**Conformance score:** {score}%")
    lines.append(
        f"**Findings:** {summary.get('errors', 0)} error(s), "
        f"{summary.get('warnings', 0)} warning(s)"
    )
    if report.get("error"):
        lines.append("")
        lines.append(f"> {report.get('error')}")
    lines.append("")
    lines.append("## Findings")
    lines.extend(_md_findings(list(report.get("findings") or [])))
    return "\n".join(lines).rstrip() + "\n"


# --- HTML ---------------------------------------------------------------------

_CSS = """
:root { color-scheme: light dark; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
       margin: 2rem auto; max-width: 60rem; padding: 0 1rem; line-height: 1.5; }
h1 { margin-bottom: .25rem; }
.badge { display: inline-block; padding: .15rem .6rem; border-radius: .5rem;
         font-weight: 600; color: #fff; }
.pass { background: #197741; } .fail { background: #b3261e; }
.error { background: #8a5a00; }
.score { font-size: 2.4rem; font-weight: 700; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #8884; padding: .4rem .6rem; text-align: left;
         vertical-align: top; font-size: .95rem; }
th { background: #8881; }
code { background: #8882; padding: 0 .3rem; border-radius: .25rem; }
.sev-error { color: #b3261e; font-weight: 600; }
.sev-warning { color: #8a5a00; font-weight: 600; }
""".strip()


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _status_badge(status: str) -> str:
    cls = {"pass": "pass", "fail": "fail", "error": "error"}.get(status.lower(), "error")
    return f'<span class="badge {cls}">{_esc(status.upper())}</span>'


def _html_findings(findings: list[Mapping[str, Any]]) -> str:
    if not findings:
        return "<p><em>No findings.</em></p>"
    rows = [
        "<table><thead><tr><th>Severity</th><th>Check</th>"
        "<th>Target</th><th>Message</th></tr></thead><tbody>"
    ]
    for f in findings:
        sev = str(f.get("severity", ""))
        rows.append(
            f'<tr><td class="sev-{_esc(sev)}">{_esc(sev)}</td>'
            f"<td>{_esc(f.get('check', ''))}</td>"
            f"<td><code>{_esc(f.get('target', ''))}</code></td>"
            f"<td>{_esc(f.get('message', ''))}</td></tr>"
        )
    rows.append("</tbody></table>")
    return "".join(rows)


def render_html(report: Mapping[str, Any]) -> str:
    score = score_of(report)
    status = str(report.get("status", "error"))
    body: list[str] = []

    if _is_aggregate(report):
        summary = report.get("summary", {})
        body.append("<h1>Data Gate Report</h1>")
        body.append(f"<p>{_status_badge(status)}</p>")
        body.append(f'<p class="score">{score}%</p>')
        body.append(
            f"<p>{summary.get('contracts', 0)} contract(s): "
            f"{summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed, "
            f"{summary.get('errored', 0)} errored.</p>"
        )
        body.append(
            "<table><thead><tr><th>Contract</th><th>Status</th>"
            "<th>Errors</th><th>Warnings</th></tr></thead><tbody>"
        )
        for r in report.get("reports") or []:
            s = r.get("summary", {})
            body.append(
                f"<tr><td><code>{_esc(r.get('contract', ''))}</code></td>"
                f"<td>{_esc(str(r.get('status', '')).upper())}</td>"
                f"<td>{_esc(s.get('errors', 0))}</td>"
                f"<td>{_esc(s.get('warnings', 0))}</td></tr>"
            )
        body.append("</tbody></table>")
        for r in report.get("reports") or []:
            if r.get("findings"):
                body.append(f"<h2>{_esc(r.get('contract', ''))}</h2>")
                body.append(_html_findings(list(r.get("findings") or [])))
    else:
        summary = report.get("summary", {})
        title = f"{report.get('database', '')}/{report.get('schema', '')}"
        body.append(f"<h1>Data Gate Report — {_esc(title)}</h1>")
        body.append(f"<p>{_status_badge(status)}</p>")
        body.append(f'<p class="score">{score}%</p>')
        body.append(
            f"<p>{_esc(summary.get('errors', 0))} error(s), "
            f"{_esc(summary.get('warnings', 0))} warning(s).</p>"
        )
        if report.get("error"):
            body.append(f"<p><strong>{_esc(report.get('error'))}</strong></p>")
        body.append("<h2>Findings</h2>")
        body.append(_html_findings(list(report.get("findings") or [])))

    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Data Gate Report</title>"
        f"<style>{_CSS}</style></head><body>\n" + "\n".join(body) + "\n</body></html>\n"
    )

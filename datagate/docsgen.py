"""Generate human-readable schema documentation from a contract mapping.

Produces Markdown (with a Mermaid ER diagram that renders on GitHub/GitLab and
most Markdown viewers) or a self-contained HTML page. Works on any contract
mapping, so the source can be a contract file or a live database (via
``resolve_mapping``).
"""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any


def _tables(mapping: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalise the ``structure`` entries into a stable list of tables."""
    tables: list[dict[str, Any]] = []
    for entry in mapping.get("structure") or []:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("table") or entry.get("name")
        if not name:
            continue
        columns = []
        for column in entry.get("columns") or []:
            if isinstance(column, str):
                columns.append({"name": column})
            elif isinstance(column, Mapping) and column.get("name"):
                columns.append(dict(column))
        tables.append(
            {
                "name": str(name),
                "columns": columns,
                "primary_key": list(entry.get("primary_key") or []),
                "foreign_keys": list(entry.get("foreign_keys") or []),
                "indexes": list(entry.get("indexes") or []),
            }
        )
    return tables


def _keys_for(table: dict[str, Any]) -> dict[str, set[str]]:
    pk = set(table["primary_key"])
    fk: set[str] = set()
    for foreign in table["foreign_keys"]:
        fk.update(foreign.get("columns") or [])
    return {"pk": pk, "fk": fk}


def _type_of(column: Mapping[str, Any]) -> str:
    base = column.get("type") or "?"
    if column.get("max_length") is not None:
        return f"{base}({column['max_length']})"
    if column.get("precision") is not None:
        scale = column.get("scale")
        return (
            f"{base}({column['precision']},{scale})"
            if scale is not None
            else f"{base}({column['precision']})"
        )
    return str(base)


# --- Mermaid ER diagram -------------------------------------------------------


def _mermaid_token(value: str) -> str:
    """Mermaid types/identifiers cannot contain spaces."""
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in value)


def mermaid_er(mapping: Mapping[str, Any]) -> str:
    tables = _tables(mapping)
    lines = ["erDiagram"]
    for table in tables:
        keys = _keys_for(table)
        entity = _mermaid_token(table["name"])
        lines.append(f"    {entity} {{")
        for column in table["columns"]:
            markers = []
            if column["name"] in keys["pk"]:
                markers.append("PK")
            if column["name"] in keys["fk"]:
                markers.append("FK")
            marker = f" {','.join(markers)}" if markers else ""
            ctype = _mermaid_token(_type_of(column))
            lines.append(f"        {ctype} {_mermaid_token(column['name'])}{marker}")
        lines.append("    }")
    for table in tables:
        child = _mermaid_token(table["name"])
        for foreign in table["foreign_keys"]:
            parent = _mermaid_token(str(foreign.get("references_table", "")))
            if not parent:
                continue
            label = ",".join(foreign.get("columns") or []) or "fk"
            lines.append(f'    {parent} ||--o{{ {child} : "{_mermaid_token(label)}"')
    return "\n".join(lines)


# --- Markdown -----------------------------------------------------------------


def render_markdown(mapping: Mapping[str, Any]) -> str:
    database = mapping.get("database", "")
    schema = mapping.get("schema", "")
    tables = _tables(mapping)

    lines = [f"# Schema documentation — {database}/{schema}", ""]
    lines.append(f"{len(tables)} table(s).")
    lines.append("")
    lines.append("## Entity-relationship diagram")
    lines.append("")
    lines.append("```mermaid")
    lines.append(mermaid_er(mapping))
    lines.append("```")
    lines.append("")

    for table in tables:
        keys = _keys_for(table)
        lines.append(f"## {table['name']}")
        lines.append("")
        lines.append("| Column | Type | Nullable | Key |")
        lines.append("| --- | --- | --- | --- |")
        for column in table["columns"]:
            marks = []
            if column["name"] in keys["pk"]:
                marks.append("PK")
            if column["name"] in keys["fk"]:
                marks.append("FK")
            nullable = column.get("nullable")
            nullable_str = "" if nullable is None else ("yes" if nullable else "no")
            lines.append(
                f"| {column['name']} | {_type_of(column)} | {nullable_str} "
                f"| {', '.join(marks)} |"
            )
        lines.append("")
        if table["foreign_keys"]:
            lines.append("**Foreign keys**")
            for foreign in table["foreign_keys"]:
                cols = ", ".join(foreign.get("columns") or [])
                ref_cols = ", ".join(foreign.get("references_columns") or [])
                ref = foreign.get("references_table", "")
                target = f"{ref}({ref_cols})" if ref_cols else ref
                lines.append(f"- ({cols}) → {target}")
            lines.append("")
        if table["indexes"]:
            lines.append("**Indexes**")
            for index in table["indexes"]:
                unique = "unique " if index.get("unique") else ""
                cols = ", ".join(index.get("columns") or [])
                name = index.get("name") or ""
                lines.append(f"- {unique}index {name} ({cols})")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --- HTML ---------------------------------------------------------------------

_CSS = """
:root { color-scheme: light dark; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
       margin: 2rem auto; max-width: 62rem; padding: 0 1rem; line-height: 1.5; }
table { border-collapse: collapse; width: 100%; margin: .5rem 0 1.5rem; }
th, td { border: 1px solid #8884; padding: .35rem .6rem; text-align: left; }
th { background: #8881; }
code, pre { background: #8882; border-radius: .25rem; }
code { padding: 0 .3rem; }
pre { padding: .75rem; overflow-x: auto; }
.key { font-weight: 600; color: #197741; }
""".strip()


def _esc(value: Any) -> str:
    return html.escape(str(value))


def render_html(mapping: Mapping[str, Any]) -> str:
    database = mapping.get("database", "")
    schema = mapping.get("schema", "")
    tables = _tables(mapping)
    body: list[str] = [f"<h1>Schema documentation — {_esc(database)}/{_esc(schema)}</h1>"]
    body.append(f"<p>{len(tables)} table(s).</p>")

    # Mermaid source is provided in a <pre class="mermaid"> block: it renders in
    # Mermaid-aware viewers and stays readable (and copyable) everywhere else.
    body.append("<h2>Entity-relationship diagram</h2>")
    body.append(f'<pre class="mermaid">{_esc(mermaid_er(mapping))}</pre>')

    for table in tables:
        keys = _keys_for(table)
        body.append(f"<h2>{_esc(table['name'])}</h2>")
        body.append(
            "<table><thead><tr><th>Column</th><th>Type</th>"
            "<th>Nullable</th><th>Key</th></tr></thead><tbody>"
        )
        for column in table["columns"]:
            marks = []
            if column["name"] in keys["pk"]:
                marks.append("PK")
            if column["name"] in keys["fk"]:
                marks.append("FK")
            nullable = column.get("nullable")
            nullable_str = "" if nullable is None else ("yes" if nullable else "no")
            body.append(
                f"<tr><td><code>{_esc(column['name'])}</code></td>"
                f"<td>{_esc(_type_of(column))}</td>"
                f"<td>{_esc(nullable_str)}</td>"
                f'<td class="key">{_esc(", ".join(marks))}</td></tr>'
            )
        body.append("</tbody></table>")
        if table["foreign_keys"]:
            items = []
            for foreign in table["foreign_keys"]:
                cols = ", ".join(foreign.get("columns") or [])
                ref_cols = ", ".join(foreign.get("references_columns") or [])
                ref = foreign.get("references_table", "")
                target = f"{ref}({ref_cols})" if ref_cols else ref
                items.append(f"<li>({_esc(cols)}) &rarr; {_esc(target)}</li>")
            body.append(
                "<p><strong>Foreign keys</strong></p><ul>" + "".join(items) + "</ul>"
            )
        if table["indexes"]:
            items = []
            for index in table["indexes"]:
                unique = "unique " if index.get("unique") else ""
                cols = ", ".join(index.get("columns") or [])
                name = index.get("name") or ""
                items.append(f"<li>{_esc(unique)}index {_esc(name)} ({_esc(cols)})</li>")
            body.append("<p><strong>Indexes</strong></p><ul>" + "".join(items) + "</ul>")

    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Schema documentation</title>"
        f"<style>{_CSS}</style></head><body>\n" + "\n".join(body) + "\n</body></html>\n"
    )

"""Tests for the schema documentation generator."""

from __future__ import annotations

from datagate.docsgen import mermaid_er, render_html, render_markdown

MAPPING = {
    "version": 1,
    "database": "hermes",
    "schema": "public",
    "structure": [
        {
            "table": "organizations",
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "name", "type": "text", "nullable": False},
            ],
            "primary_key": ["id"],
        },
        {
            "table": "users",
            "columns": [
                {"name": "id", "type": "integer", "nullable": False},
                {"name": "org_id", "type": "integer", "nullable": False},
                {"name": "email", "type": "character varying", "max_length": 255},
            ],
            "primary_key": ["id"],
            "foreign_keys": [
                {
                    "columns": ["org_id"],
                    "references_table": "organizations",
                    "references_columns": ["id"],
                }
            ],
            "indexes": [
                {"name": "users_email_idx", "columns": ["email"], "unique": True}
            ],
        },
    ],
    "audit": [],
}


def test_mermaid_er_has_entities_and_relationship() -> None:
    er = mermaid_er(MAPPING)
    assert er.startswith("erDiagram")
    assert "users {" in er
    assert "integer id PK" in er
    assert "integer org_id FK" in er
    # spaces in the type must be sanitised for mermaid
    assert "character_varying_255_ email" in er
    # relationship parent ||--o{ child
    assert "organizations ||--o{ users" in er


def test_render_markdown_contains_diagram_and_tables() -> None:
    md = render_markdown(MAPPING)
    assert "# Schema documentation — hermes/public" in md
    assert "```mermaid" in md
    assert "## users" in md
    assert "| org_id | integer | no | FK |" in md
    assert "(org_id) → organizations(id)" in md
    assert "unique index users_email_idx (email)" in md


def test_render_html_self_contained() -> None:
    html_out = render_html(MAPPING)
    assert html_out.startswith("<!doctype html>")
    assert "http://" not in html_out and "https://" not in html_out
    assert '<pre class="mermaid">' in html_out
    assert "users" in html_out


def test_render_html_escapes() -> None:
    mapping = {
        "database": "d",
        "schema": "s",
        "structure": [{"table": "t", "columns": [{"name": "<script>", "type": "text"}]}],
    }
    html_out = render_html(mapping)
    assert "<script>" not in html_out.split("<style>")[1]
    assert "&lt;script&gt;" in html_out

# Patrick AI Factory – Data Gate

**Read-only PostgreSQL schema conformance checker for CI/CD pipelines.**

The Data Gate connects to a PostgreSQL database, reads its live schema, compares
it against a declarative YAML **contract**, writes a machine-readable JSON report
and returns a CI-friendly exit code.

It is **strictly read-only**. It never issues `CREATE`, `ALTER`, `UPDATE`,
`DELETE` or `DROP`. Read-only mode is enforced at the connection level, and the
tool is designed to run with a least-privilege PostgreSQL role.

---

## Table of contents

- [Objective](#objective)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Contract format](#contract-format)
- [Report format](#report-format)
- [Exit codes](#exit-codes)
- [Configuration](#configuration)
- [Development](#development)
- [Operational context](#operational-context)
- [Roadmap](#roadmap)

---

## Objective

Guarantee that a deployed PostgreSQL schema matches the structure the platform
expects, automatically, on every pipeline run. Typical use inside Patrick AI
Factory: validate the databases behind stacks such as **Hermes Review** before a
release proceeds.

## How it works

```
datagate contracts/example-users.yaml
        │
        ▼
 load contract (YAML)  ──►  connect (READ ONLY)  ──►  introspect live schema
        │                                                     │
        ▼                                                     ▼
             compare contract vs. reality (modular checks)
                              │
                              ▼
        artifacts/data-gate-result.json   +   exit code (0 / 1 / 2)
```

## Architecture

The code follows a clean, layered design — each concern is isolated and
independently testable.

| Module | Responsibility |
| --- | --- |
| `datagate/contract.py` | Load & parse the YAML contract into a typed model |
| `datagate/db.py` | Open a **read-only** psycopg 3 connection from `DATAGATE_DSN` |
| `datagate/introspect.py` | Read the live schema (tables, columns, PK, FK, indexes, views) into a domain model |
| `datagate/models.py` | Immutable dataclasses describing the actual schema |
| `datagate/checks/` | Independent, pluggable checks (structure, columns, constraints, indexes, audit) |
| `datagate/engine.py` | Run all checks and aggregate findings |
| `datagate/report.py` | Findings, report assembly, JSON serialisation, exit-code mapping |
| `datagate/verifier.py` | Orchestrates the full run (application service) |
| `datagate/cli.py` | Thin CLI adapter — no business logic |

Adding a new verification is a matter of dropping a module in `datagate/checks/`
and registering it in `default_checks()` — existing checks stay untouched
(open/closed principle).

## Installation

Requires **Python 3.12+**.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
export DATAGATE_DSN="postgresql://datagate_ro:***@localhost:5432/your_db"

datagate contracts/example-users.yaml
# or specify the report location / DSN explicitly:
datagate contracts/example-users.yaml --dsn "$DATAGATE_DSN" -o artifacts/data-gate-result.json
```

Options:

| Flag | Description |
| --- | --- |
| `--dsn` | PostgreSQL DSN (defaults to `DATAGATE_DSN`) |
| `-o`, `--output` | Report path (default `artifacts/data-gate-result.json`) |
| `-v`, `--verbose` | Verbose (DEBUG) logging |
| `--version` | Print version |

## Contract format

The contract declares **expectations**; the database is the source of truth.
`structure` and `audit` are lists, so an empty contract is valid.

```yaml
version: 1
database: your_db
schema: public

structure:
  - table: users
    columns:
      - name: id
        type: integer      # aliases like int / varchar / timestamptz are accepted
        nullable: false
      - name: email        # a bare string checks presence only
    primary_key: [id]
    foreign_keys:
      - columns: [org_id]
        references_table: organizations
        references_columns: [id]
    indexes:
      - name: users_email_idx
        columns: [email]
        unique: true

audit:
  - table: users
    required_columns: [created_at, updated_at]
```

See [`contracts/example-users.yaml`](contracts/example-users.yaml) for a complete example.

## Report format

```json
{
  "status": "fail",
  "database": "your_db",
  "schema": "public",
  "summary": { "errors": 1, "warnings": 0, "total": 1 },
  "findings": [
    {
      "check": "structure",
      "severity": "error",
      "target": "table:orders",
      "message": "Expected table 'orders' is missing from schema 'public'."
    }
  ],
  "generated_at": "2026-07-19T10:19:19+00:00",
  "metadata": { "contract_version": 1, "tables_checked": 2, "audit_rules": 1 }
}
```

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | **PASS** — the schema conforms to the contract |
| `1` | **FAIL** — at least one conformance error was found |
| `2` | **ERROR** — the run could not complete (bad contract, no DB, connection failure) |

## Configuration

Configuration comes exclusively from the environment — **no credentials live in
the code or the repository**.

| Variable | Description |
| --- | --- |
| `DATAGATE_DSN` | PostgreSQL connection string for a **read-only** role |

Provide it via a local `.env` (see [`.env.example`](.env.example)), system
environment variables, or CI secrets (e.g. GitHub Actions Secrets).

## Development

```bash
pip install -e ".[dev]"
ruff check .        # lint
black --check .     # formatting
pytest --cov        # tests + coverage
```

CI (GitHub Actions, [`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs
two jobs on Python 3.12:

1. **quality** — Ruff, Black and pytest with coverage.
2. **integration** — spins up a PostgreSQL service, seeds a schema, creates a
   dedicated read-only role and runs the Data Gate end to end, uploading
   `artifacts/data-gate-result.json`.

## Operational context

The Data Gate is a standalone component of the Patrick AI Factory platform.

- **OS / runtime:** Ubuntu Server 24.04 LTS, Python 3.12.
- **Deployment path:** `/opt/patrick-ai-factory/patrick-ai-factory-data-gate`.
  The tool is independent and must never modify the platform stacks.
- **Database access:** always through a dedicated read-only PostgreSQL role; the
  DSN is injected via `DATAGATE_DSN` (environment / secrets), never committed.
- **CI/CD:** GitHub Actions; the DSN and any deployment specifics are provided as
  repository/organization secrets.

## Roadmap

- [x] **Sprint 1** — Repository audit & packaging hardening
- [x] **Sprint 2** — Read-only PostgreSQL connection
- [x] **Sprint 3** — Schema introspection (tables, columns, PK, FK, indexes, views)
- [x] **Sprint 4** — Contract vs. database comparison engine
- [x] **Sprint 5** — JSON report & exit codes
- [x] **Sprint 6** — GitHub Actions CI (lint, format, tests, integration)
- [x] **Sprint 7** — Documentation
- [ ] Warning-level (non-blocking) findings & severity policy per check
- [ ] Detection of unexpected/extra objects (drift in the other direction)
- [ ] Column type precision (length, precision/scale) and default-value checks
- [ ] Multi-schema contracts

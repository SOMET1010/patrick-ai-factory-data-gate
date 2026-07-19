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

The recommended lifecycle turns the database into a versioned contract, then
guards it:

```
PostgreSQL ──► datagate generate ──► contract.yaml ──► git ──► datagate verify
```

```bash
export DATAGATE_DSN="postgresql://datagate_ro:***@localhost:5432/your_db"

# 1. Generate a draft contract from the live schema (once, then commit & trim it)
datagate generate --schema public -o contracts/your_db.yaml

# 2. Verify the schema against the committed contract (in CI)
datagate verify contracts/your_db.yaml
```

### Commands

| Command | Purpose |
| --- | --- |
| `datagate generate` | Introspect a live schema and write a draft YAML contract |
| `datagate verify <contract>` | Verify a live schema against a contract (writes the JSON report) |
| `datagate verify <directory>` | Verify **every** `*.yaml`/`*.yml` contract under a directory (recursively) and write one aggregate report |

> Backward compatible: `datagate <contract>` (no subcommand) is treated as
> `datagate verify <contract>`.

**Verifying many contracts at once** — point `verify` at a directory:

```bash
datagate verify contracts/ -o artifacts/data-gate-result.json
```

Every contract is checked independently; the aggregate JSON report lists each
result plus a global summary, and the exit code is the worst outcome
(`0` all pass, `1` at least one FAIL, `2` at least one ERROR).

**`verify`** options:

| Flag | Description |
| --- | --- |
| `--dsn` | PostgreSQL DSN (defaults to `DATAGATE_DSN`) |
| `-o`, `--output` | Report path (default `artifacts/data-gate-result.json`) |
| `--contract-only` | Validate the contract only, without connecting to a database |
| `-v`, `--verbose` | Verbose (DEBUG) logging |

**`generate`** options:

| Flag | Description |
| --- | --- |
| `--dsn` | PostgreSQL DSN (defaults to `DATAGATE_DSN`) |
| `--schema` | Schema to introspect (default `public`) |
| `-o`, `--output` | Output path (default `contracts/<database>.yaml`) |

Validate a contract without a database (fast CI lint, exit `0`/`2`):

```bash
datagate verify contracts/hermes-review.yaml --contract-only
```

## Contract format

The contract declares **expectations**; the database is the source of truth.
`structure` and `audit` are lists, so an empty contract is valid.

```yaml
version: 1
database: your_db
schema: public

# Optional governance policy. Controls how *drift* (objects present in the
# database but not declared here) is reported: error | warning | ignore.
# Defaults to "ignore", so partial contracts stay valid.
settings:
  unexpected_tables: warning
  unexpected_columns: ignore

structure:
  - table: users
    columns:
      - name: id
        type: integer      # aliases like int / varchar / timestamptz are accepted
        nullable: false
      - name: email        # a bare string checks presence only
        type: varchar(255) # inline parameters check length…
      - name: amount
        type: numeric(10, 2) # …and precision / scale
      - name: status
        default: active    # best-effort default comparison (casts/quotes ignored)
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

Column parameters can also be written explicitly (`max_length`, `precision`,
`scale`) instead of inline in `type`. See
[`contracts/example-users.yaml`](contracts/example-users.yaml) for a complete example.

### Checks

| Check | Verifies |
| --- | --- |
| `structure` | Declared tables exist |
| `columns` | Column presence, type, nullability, length/precision/scale, default |
| `constraints` | Primary keys and foreign keys |
| `indexes` | Declared indexes exist |
| `audit` | Governance rules (required columns per table) |
| `drift` | Objects present in the DB but not declared (opt-in via `settings`) |

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

## Deployment — using the gate as a component

The Data Gate ships three ready-to-use integration surfaces so it can be dropped
into any Patrick AI Factory stack (e.g. **Hermes Review**) without copying code.

### 1. CLI (pip / pipx)

```bash
pipx install "git+https://github.com/SOMET1010/patrick-ai-factory-data-gate"
DATAGATE_DSN="postgresql://datagate_ro:***@host:5432/db" \
  datagate contracts/your-contract.yaml
```

### 2. Docker

A small, non-root image is defined in [`Dockerfile`](Dockerfile):

```bash
docker build -t patrick-datagate .

# Mount the repo (contracts + artifacts) and pass the DSN via the environment.
docker run --rm \
  -e DATAGATE_DSN="postgresql://datagate_ro:***@db-host:5432/your_db" \
  -v "$PWD:/work" \
  patrick-datagate contracts/your-contract.yaml -o artifacts/data-gate-result.json
```

The container's exit code is the gate's exit code (`0/1/2`), so it works as a
pipeline step as-is. To verify **all** contracts in one run, point it at the
mounted directory:

```bash
docker run --rm \
  -e DATAGATE_DSN="postgresql://datagate_ro:***@db-host:5432/your_db" \
  -v "$PWD:/work" \
  patrick-datagate verify contracts -o artifacts/data-gate-result.json
```

### 3. Reusable GitHub Action

The repository exposes a composite action ([`action.yml`](action.yml)). Any
workflow can gate a deployment on schema conformance in one step:

```yaml
- name: Data Gate
  uses: SOMET1010/patrick-ai-factory-data-gate@main
  with:
    contract: contracts/hermes-review.yaml
    dsn: ${{ secrets.DATAGATE_DSN }}   # a read-only role
```

The step fails the job on `FAIL`/`ERROR`, and the JSON report path is exposed as
the `report` output for later steps (e.g. artifact upload).

### On the server

On the platform host the tool lives at
`/opt/patrick-ai-factory/patrick-ai-factory-data-gate`. Install it once
(`pip install -e .` inside a venv) or run the Docker image; the DSN of the
read-only role is supplied through the environment / secrets, never committed.

**Automated deployment:** a merge to `main` can deploy to the server over SSH via
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) (running
[`scripts/deploy.sh`](scripts/deploy.sh)). See
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the one-time setup — no credentials
ever live in the repository.

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
- [x] Warning-level (non-blocking) findings & severity policy (`settings`)
- [x] Detection of unexpected/extra objects (drift)
- [x] Column type precision (length, precision/scale) and default-value checks
- [x] Deployable component: Docker image + reusable GitHub Action
- [x] `datagate generate` — draft a contract from a live schema
- [x] `datagate verify <directory>` — verify many contracts at once
- [ ] `datagate diff` — compare two schemas or two contracts
- [ ] `datagate docs` — generate schema documentation (Markdown/HTML)
- [ ] `datagate report` — render the JSON report as Markdown/HTML
- [ ] Multi-schema contracts
- [ ] Per-check severity overrides (e.g. treat a missing index as a warning)
- [ ] Publish the Docker image to a registry (GHCR)

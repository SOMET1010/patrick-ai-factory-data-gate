# Architecture & design decisions

This document records the significant decisions behind the Data Gate so future
contributors understand *why* the code looks the way it does.

## Layering (Clean Architecture)

```
cli  ─►  verifier  ─►  { contract, db, introspect } ─►  engine ─► checks ─► report
                                 │                                         │
                                 └──────────── models (domain) ───────────┘
```

- **`cli`** is a thin adapter: argument parsing, logging setup, exit code. It
  contains no business logic.
- **`verifier`** is the application service that orchestrates a full run and is
  the single entry point for tests and other tools.
- **`models`** holds immutable domain dataclasses shared by every layer, so the
  checks depend on a clean abstraction rather than on psycopg rows or YAML.

**Why:** each concern is isolated and independently testable; the CLI can be
replaced (e.g. by a library call) without touching the verification logic.

## Decision: read-only is enforced at the session level

Setting `connection.read_only = True` is **not** honoured under
`autocommit = True` in psycopg 3. We therefore also execute
`SET default_transaction_read_only = on`, which makes every implicit transaction
reject writes — even for superusers. Both are set as defense in depth.

**Why:** the tool's core guarantee is that it can never mutate the inspected
database. This was verified end-to-end: a `CREATE TABLE` through the connection
is rejected with *"cannot execute CREATE TABLE in a read-only transaction"*.

## Decision: introspect via `pg_catalog`, not `information_schema`, for constraints

`information_schema.table_constraints` / `key_column_usage` are **privilege-aware**:
a least-privilege role holding only `SELECT` does **not** see primary/foreign key
constraints through them. Since the Data Gate is meant to run with a read-only
role, primary keys, foreign keys and indexes are read from `pg_catalog`
(`pg_constraint`, `pg_index`, …), which is visible regardless of table
privileges. `LATERAL unnest(... ) WITH ORDINALITY` preserves column ordering and
handles composite keys correctly.

Tables and columns are still read from `information_schema`, which does expose
objects on which the role holds `SELECT`.

**Why:** without this, every primary key would be reported as missing when run
with the intended read-only user — a bug that only surfaces against a real
least-privilege connection.

## Decision: the contract keeps `structure` and `audit` as lists

Earlier versions shipped a contract with `structure: []` and `audit: []`. To stay
backward compatible, the richer, typed contract model keeps both as *lists of
rules*. `load_contract()` (raw dict) is preserved; `Contract.from_file()` adds the
typed parsing layer on top.

**Why:** never break existing contracts or the existing loader API.

## Decision: checks are independent and pluggable

Every check implements a small `Check` protocol (`name` + `run(contract, schema)`)
and returns a list of `Finding`s. The engine runs them and isolates failures — a
raising check is logged and skipped rather than aborting the whole run.

**Why:** adding a verification means adding a module and registering it in
`default_checks()`; existing checks stay untouched (open/closed principle).

## Decision: `generate` and `verify` share one introspection engine

`datagate generate` (draft a contract from a live schema) and `datagate verify`
(check a schema against a contract) both go through the same `Introspector` and
domain `Schema` model. `generate` simply serialises that model to YAML
(`generator.py`); `verify` compares it against the contract. They can therefore
never disagree about how the database is read, and a generated contract verifies
clean against the schema it came from (covered by a round-trip test).

**Why:** one source of truth for schema reading keeps the growing command
surface (`generate`, `verify`, future `diff`/`docs`) consistent.

## Decision: status → exit code mapping lives in the domain

`Status.PASS/FAIL/ERROR` own their exit codes (`0/1/2`). Expected failures
(bad contract, no DSN, connection error) are captured by the verifier and
returned as an `ERROR` report, so the CLI always has a serialisable result to
write and a correct code to return.

**Why:** CI pipelines depend on precise, predictable exit codes.

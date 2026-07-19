-- Seed schema used by the CI integration job.
-- Mirrors contracts/example-users.yaml so the Data Gate run reports PASS.

CREATE TABLE organizations (
    id   integer PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE users (
    id         integer PRIMARY KEY,
    org_id     integer NOT NULL REFERENCES organizations (id),
    email      text NOT NULL,
    created_at timestamp NOT NULL,
    updated_at timestamp
);

CREATE UNIQUE INDEX users_email_idx ON users (email);

-- A dedicated read-only role. The Data Gate must run with a least-privilege
-- account; introspection reads information_schema, which is privilege-aware, so
-- SELECT on the tables is required for them to be visible.
CREATE ROLE datagate_ro LOGIN PASSWORD 'datagate_ro';
GRANT CONNECT ON DATABASE datagate_ci TO datagate_ro;
GRANT USAGE ON SCHEMA public TO datagate_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO datagate_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO datagate_ro;

CREATE SCHEMA audit AUTHORIZATION mcp_audit_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE TABLE audit.operations (
    operation_id text PRIMARY KEY,
    issuer text NOT NULL,
    subject text NOT NULL,
    expires_at text NOT NULL,
    tool text NOT NULL,
    inputs jsonb NOT NULL,
    limits jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE audit.operations IS 'Immutable request intent with verified caller, exact inputs, and configured limits; no tokens or result sets.';
CREATE TABLE audit.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_id text NOT NULL REFERENCES audit.operations(operation_id),
    kind text NOT NULL,
    detail jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
COMMENT ON TABLE audit.events IS 'Append-only approval, execution, commit-intent, and outcome events.';
CREATE INDEX events_operation_id ON audit.events(operation_id, event_id);
GRANT USAGE ON SCHEMA audit TO mcp_audit_runtime;
GRANT INSERT ON audit.operations, audit.events TO mcp_audit_runtime;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA audit TO mcp_audit_runtime;
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA audit FROM mcp_audit_runtime;

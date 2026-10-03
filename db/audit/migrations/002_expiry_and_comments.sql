-- Preserve the original migration checksum while giving token expiry a timestamp type.
ALTER TABLE audit.operations ALTER COLUMN expires_at TYPE timestamptz
    USING to_timestamp(expires_at::double precision);
COMMENT ON TABLE public.mcp_audit_migrations IS 'Applied audit migration versions and immutable source checksums.';
COMMENT ON COLUMN public.mcp_audit_migrations.version IS 'Numbered migration identifier.';
COMMENT ON COLUMN public.mcp_audit_migrations.sha256 IS 'SHA-256 of the applied SQL file; drift fails migration validation.';
COMMENT ON COLUMN audit.operations.operation_id IS 'Server-generated UUID shared by preview, approval, execution and result.';
COMMENT ON COLUMN audit.operations.issuer IS 'Verified token issuer; never an unverified client argument.';
COMMENT ON COLUMN audit.operations.subject IS 'Verified subject within the issuer namespace.';
COMMENT ON COLUMN audit.operations.expires_at IS 'Expiration of the identity used when the request was received.';
COMMENT ON COLUMN audit.operations.tool IS 'Database tool receiving the request.';
COMMENT ON COLUMN audit.operations.inputs IS 'Exact SQL or JSON arguments supplied to the tool; excludes authentication headers.';
COMMENT ON COLUMN audit.operations.limits IS 'Configured execution and approval limits at request time.';
COMMENT ON COLUMN audit.operations.created_at IS 'Database timestamp when the intent was persisted.';
COMMENT ON COLUMN audit.events.event_id IS 'Append order within the audit store; gaps are possible after rollback.';
COMMENT ON COLUMN audit.events.operation_id IS 'Request whose history this event extends.';
COMMENT ON COLUMN audit.events.kind IS 'Approval, execution_intent, commit_intent, outcome, error, or cancellation.';
COMMENT ON COLUMN audit.events.detail IS 'Decision, preview or execution metadata; excludes result sets and tokens.';
COMMENT ON COLUMN audit.events.created_at IS 'Database timestamp when the event was persisted.';

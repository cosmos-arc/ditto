-- Dedicated Agent runtime state. Raw prompts, responses, and objectives are absent.
CREATE TABLE agent_manifests (
    manifest_hash TEXT PRIMARY KEY CHECK(length(manifest_hash) = 64),
    manifest_id TEXT NOT NULL UNIQUE,
    agent_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_hash TEXT NOT NULL CHECK(length(prompt_hash) = 64),
    tool_schema_version TEXT NOT NULL,
    tool_schema_hash TEXT NOT NULL CHECK(length(tool_schema_hash) = 64),
    model_profile TEXT NOT NULL CHECK(model_profile IN ('balanced', 'quality')),
    model_snapshot TEXT NOT NULL
) STRICT;

CREATE TABLE agent_sessions (
    session_id TEXT PRIMARY KEY,
    created_at_us INTEGER NOT NULL CHECK(created_at_us > 0),
    retention_class TEXT NOT NULL
        CHECK(retention_class IN ('ephemeral', 'standard', 'audit'))
) STRICT;

CREATE TABLE agent_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(session_id),
    status TEXT NOT NULL CHECK(status IN (
        'queued', 'running', 'waiting_approval', 'paused',
        'completed', 'failed', 'cancelled'
    )),
    objective_hash TEXT NOT NULL CHECK(length(objective_hash) = 64),
    authority_hash TEXT NOT NULL CHECK(length(authority_hash) = 64),
    max_model_tokens INTEGER NOT NULL CHECK(max_model_tokens > 0),
    max_model_spend_usd TEXT NOT NULL,
    model_profile TEXT NOT NULL CHECK(model_profile IN ('balanced', 'quality')),
    manifest_hash TEXT NOT NULL REFERENCES agent_manifests(manifest_hash),
    created_at_us INTEGER NOT NULL CHECK(created_at_us > 0),
    started_at_us INTEGER CHECK(started_at_us IS NULL OR started_at_us > 0),
    finished_at_us INTEGER CHECK(finished_at_us IS NULL OR finished_at_us > 0),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
    CHECK(started_at_us IS NULL OR started_at_us >= created_at_us),
    CHECK(finished_at_us IS NULL OR (
        started_at_us IS NOT NULL AND finished_at_us >= started_at_us
    ))
) STRICT;

CREATE INDEX agent_runs_session_created
ON agent_runs(session_id, created_at_us, run_id);

CREATE TABLE agent_run_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
    run_sequence INTEGER NOT NULL CHECK(run_sequence > 0),
    event_type TEXT NOT NULL,
    payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
    occurred_at_us INTEGER NOT NULL CHECK(occurred_at_us > 0),
    prev_hash TEXT CHECK(prev_hash IS NULL OR length(prev_hash) = 64),
    event_hash TEXT NOT NULL UNIQUE CHECK(length(event_hash) = 64),
    UNIQUE(run_id, run_sequence)
) STRICT;

CREATE INDEX agent_run_events_run_order
ON agent_run_events(run_id, run_sequence);

CREATE TRIGGER agent_run_events_no_update
BEFORE UPDATE ON agent_run_events
BEGIN
    SELECT RAISE(ABORT, 'agent run events are append-only');
END;

CREATE TRIGGER agent_run_events_no_delete
BEFORE DELETE ON agent_run_events
BEGIN
    SELECT RAISE(ABORT, 'agent run events are append-only');
END;

CREATE TABLE agent_episode_manifests (
    episode_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES agent_runs(run_id),
    manifest_hash TEXT NOT NULL UNIQUE CHECK(length(manifest_hash) = 64),
    replay_identity TEXT NOT NULL UNIQUE CHECK(length(replay_identity) = 64),
    payload_json BLOB NOT NULL CHECK(length(payload_json) > 0),
    sealed_at_us INTEGER NOT NULL CHECK(sealed_at_us > 0)
) STRICT;

CREATE TRIGGER agent_episode_manifests_no_update
BEFORE UPDATE ON agent_episode_manifests
BEGIN
    SELECT RAISE(ABORT, 'agent episode manifests are immutable');
END;

CREATE TRIGGER agent_episode_manifests_no_delete
BEFORE DELETE ON agent_episode_manifests
BEGIN
    SELECT RAISE(ABORT, 'agent episode manifests are immutable');
END;

CREATE TRIGGER agent_run_events_after_episode
BEFORE INSERT ON agent_run_events
WHEN EXISTS (
    SELECT 1 FROM agent_episode_manifests WHERE run_id = NEW.run_id
)
BEGIN
    SELECT RAISE(ABORT, 'sealed agent episodes forbid new run events');
END;

CREATE TABLE agent_approvals (
    request_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
    action_hash TEXT NOT NULL UNIQUE CHECK(length(action_hash) = 64),
    action_payload BLOB NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
    requested_at_us INTEGER NOT NULL CHECK(requested_at_us > 0),
    expires_at_us INTEGER NOT NULL CHECK(expires_at_us > requested_at_us),
    operator_id TEXT,
    reason TEXT,
    decided_at_us INTEGER CHECK(decided_at_us IS NULL OR decided_at_us >= requested_at_us),
    CHECK((status = 'pending') = (decided_at_us IS NULL)),
    CHECK((status = 'pending') = (operator_id IS NULL))
) STRICT;

CREATE INDEX agent_approvals_run_status
ON agent_approvals(run_id, status, requested_at_us);

CREATE TABLE agent_idempotency (
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK(length(request_hash) = 64),
    status TEXT NOT NULL CHECK(status IN ('pending', 'completed')),
    result_identity TEXT,
    created_at_us INTEGER NOT NULL CHECK(created_at_us > 0),
    updated_at_us INTEGER NOT NULL CHECK(updated_at_us >= created_at_us),
    PRIMARY KEY(scope, idempotency_key),
    CHECK((status = 'completed') = (result_identity IS NOT NULL))
) STRICT;

CREATE TABLE agent_leases (
    resource_kind TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    owner_token TEXT NOT NULL,
    fence INTEGER NOT NULL CHECK(fence > 0),
    lease_until_us INTEGER NOT NULL CHECK(lease_until_us > 0),
    revision INTEGER NOT NULL CHECK(revision >= 0),
    PRIMARY KEY(resource_kind, resource_id)
) STRICT;

CREATE TABLE agent_run_continuations (
    run_id TEXT PRIMARY KEY REFERENCES agent_runs(run_id),
    provider TEXT NOT NULL,
    payload_json BLOB NOT NULL,
    payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
    updated_at_us INTEGER NOT NULL CHECK(updated_at_us > 0)
) STRICT;

CREATE TABLE agent_retention (
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    retention_class TEXT NOT NULL
        CHECK(retention_class IN ('ephemeral', 'standard', 'audit')),
    retain_until_us INTEGER CHECK(retain_until_us IS NULL OR retain_until_us > 0),
    legal_hold INTEGER NOT NULL CHECK(legal_hold IN (0, 1)),
    updated_at_us INTEGER NOT NULL CHECK(updated_at_us > 0),
    PRIMARY KEY(target_kind, target_id)
) STRICT;

CREATE TABLE agent_audit_events (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
    occurred_at_us INTEGER NOT NULL CHECK(occurred_at_us > 0),
    prev_hash TEXT CHECK(prev_hash IS NULL OR length(prev_hash) = 64),
    event_hash TEXT NOT NULL UNIQUE CHECK(length(event_hash) = 64)
) STRICT;

CREATE TRIGGER agent_audit_no_update
BEFORE UPDATE ON agent_audit_events
BEGIN
    SELECT RAISE(ABORT, 'agent audit events are append-only');
END;

CREATE TRIGGER agent_audit_no_delete
BEFORE DELETE ON agent_audit_events
BEGIN
    SELECT RAISE(ABORT, 'agent audit events are append-only');
END;

PRAGMA application_id = 1146372423;
PRAGMA user_version = 1;

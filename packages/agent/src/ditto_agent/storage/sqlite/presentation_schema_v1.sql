-- Sanitized, derived Agent read model. This database is never authoritative.
CREATE TABLE agent_run_presentation (
    run_id TEXT PRIMARY KEY,
    projection_version INTEGER NOT NULL CHECK(projection_version > 0),
    updated_at_us INTEGER NOT NULL CHECK(updated_at_us > 0),
    status TEXT NOT NULL CHECK(status IN (
        'queued', 'running', 'waiting_approval', 'paused',
        'completed', 'failed', 'cancelled'
    )),
    payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
    payload_json BLOB NOT NULL CHECK(length(payload_json) > 0)
) STRICT;

CREATE INDEX agent_run_presentation_updated
ON agent_run_presentation(updated_at_us DESC, run_id DESC);

PRAGMA application_id = 1146376274;
PRAGMA user_version = 1;

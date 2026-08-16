-- Dedicated DecisionOpinion shadow state. No core decision or trading table exists.
CREATE TABLE shadow_decision_opinions (
    opinion_id TEXT PRIMARY KEY,
    shadow_outcome_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('completed', 'blocked')),
    v3_artifact_id TEXT NOT NULL,
    v3_evidence_hash TEXT NOT NULL CHECK(length(v3_evidence_hash) = 64),
    v3_readiness TEXT NOT NULL CHECK(v3_readiness IN ('ready', 'review', 'blocked')),
    opinion_hash TEXT NOT NULL UNIQUE CHECK(length(opinion_hash) = 64),
    generated_at_us INTEGER NOT NULL CHECK(generated_at_us > 0),
    payload_json BLOB NOT NULL CHECK(length(payload_json) > 0)
) STRICT;

CREATE TABLE shadow_decision_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    opinion_id TEXT NOT NULL REFERENCES shadow_decision_opinions(opinion_id),
    event_sequence INTEGER NOT NULL CHECK(event_sequence = 1),
    event_type TEXT NOT NULL
        CHECK(event_type = 'shadow_decision_opinion_persisted'),
    payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
    occurred_at_us INTEGER NOT NULL CHECK(occurred_at_us > 0),
    event_hash TEXT NOT NULL UNIQUE CHECK(length(event_hash) = 64),
    UNIQUE(opinion_id, event_sequence)
) STRICT;

CREATE TRIGGER shadow_decision_opinions_no_update
BEFORE UPDATE ON shadow_decision_opinions
BEGIN
    SELECT RAISE(ABORT, 'shadow decision opinions are immutable');
END;

CREATE TRIGGER shadow_decision_opinions_no_delete
BEFORE DELETE ON shadow_decision_opinions
BEGIN
    SELECT RAISE(ABORT, 'shadow decision opinions are immutable');
END;

CREATE TRIGGER shadow_decision_events_no_update
BEFORE UPDATE ON shadow_decision_events
BEGIN
    SELECT RAISE(ABORT, 'shadow decision events are append-only');
END;

CREATE TRIGGER shadow_decision_events_no_delete
BEFORE DELETE ON shadow_decision_events
BEGIN
    SELECT RAISE(ABORT, 'shadow decision events are append-only');
END;

PRAGMA application_id = 1146373976;
PRAGMA user_version = 1;

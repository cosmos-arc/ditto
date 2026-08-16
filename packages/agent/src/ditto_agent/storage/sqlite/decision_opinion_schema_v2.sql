-- Add immutable PIT-bound outcome feedback without altering opinion rows.
CREATE TABLE shadow_outcome_feedback (
    feedback_id TEXT PRIMARY KEY,
    opinion_id TEXT NOT NULL UNIQUE
        REFERENCES shadow_decision_opinions(opinion_id),
    shadow_outcome_id TEXT NOT NULL UNIQUE,
    opinion_hash TEXT NOT NULL CHECK(length(opinion_hash) = 64),
    observation_id TEXT NOT NULL UNIQUE,
    observation_hash TEXT NOT NULL UNIQUE CHECK(length(observation_hash) = 64),
    outcome_known_at_us INTEGER NOT NULL CHECK(outcome_known_at_us > 0),
    linked_at_us INTEGER NOT NULL CHECK(linked_at_us >= outcome_known_at_us),
    source_snapshot_id TEXT NOT NULL,
    adoption TEXT NOT NULL
        CHECK(adoption IN ('not_reviewed', 'reviewed', 'adopted', 'rejected')),
    accuracy_basis_points INTEGER NOT NULL
        CHECK(accuracy_basis_points BETWEEN 0 AND 10000),
    calibration_basis_points INTEGER NOT NULL
        CHECK(calibration_basis_points BETWEEN 0 AND 10000),
    memory_promotion TEXT NOT NULL CHECK(memory_promotion = 'none'),
    feedback_hash TEXT NOT NULL UNIQUE CHECK(length(feedback_hash) = 64),
    payload_json BLOB NOT NULL CHECK(length(payload_json) > 0)
) STRICT;

CREATE TABLE shadow_outcome_feedback_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_id TEXT NOT NULL REFERENCES shadow_outcome_feedback(feedback_id),
    event_sequence INTEGER NOT NULL CHECK(event_sequence = 1),
    event_type TEXT NOT NULL
        CHECK(event_type = 'shadow_outcome_feedback_persisted'),
    payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
    occurred_at_us INTEGER NOT NULL CHECK(occurred_at_us > 0),
    event_hash TEXT NOT NULL UNIQUE CHECK(length(event_hash) = 64),
    UNIQUE(feedback_id, event_sequence)
) STRICT;

CREATE TRIGGER shadow_outcome_feedback_opinion_binding
BEFORE INSERT ON shadow_outcome_feedback
WHEN NOT EXISTS (
    SELECT 1 FROM shadow_decision_opinions
    WHERE opinion_id = NEW.opinion_id
      AND shadow_outcome_id = NEW.shadow_outcome_id
      AND opinion_hash = NEW.opinion_hash
)
BEGIN
    SELECT RAISE(ABORT, 'shadow feedback opinion identity mismatch');
END;

CREATE TRIGGER shadow_outcome_feedback_no_update
BEFORE UPDATE ON shadow_outcome_feedback
BEGIN
    SELECT RAISE(ABORT, 'shadow outcome feedback is immutable');
END;

CREATE TRIGGER shadow_outcome_feedback_no_delete
BEFORE DELETE ON shadow_outcome_feedback
BEGIN
    SELECT RAISE(ABORT, 'shadow outcome feedback is immutable');
END;

CREATE TRIGGER shadow_outcome_feedback_events_no_update
BEFORE UPDATE ON shadow_outcome_feedback_events
BEGIN
    SELECT RAISE(ABORT, 'shadow outcome feedback events are append-only');
END;

CREATE TRIGGER shadow_outcome_feedback_events_no_delete
BEFORE DELETE ON shadow_outcome_feedback_events
BEGIN
    SELECT RAISE(ABORT, 'shadow outcome feedback events are append-only');
END;

PRAGMA application_id = 1146373976;
PRAGMA user_version = 2;

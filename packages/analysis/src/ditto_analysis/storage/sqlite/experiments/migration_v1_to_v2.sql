-- Ditto Research SQLite schema migration v1 -> v2.
-- This resource is executed inside one BEGIN IMMEDIATE transaction after the
-- exact v1 fingerprint has been verified. The version marker must remain last.

CREATE TABLE research_campaign (
    campaign_id TEXT PRIMARY KEY NOT NULL
        CHECK(length(campaign_id) > 0 AND trim(campaign_id) = campaign_id),
    manifest_hash TEXT NOT NULL UNIQUE
        CHECK(length(manifest_hash) = 64 AND manifest_hash NOT GLOB '*[^0-9a-f]*'),
    manifest_schema_version INTEGER NOT NULL CHECK(manifest_schema_version = 1),
    manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
    search_axis TEXT NOT NULL
        CHECK(search_axis IN ('factor_code', 'model_code', 'parameters')),
    lineage_root TEXT NOT NULL
        CHECK(length(lineage_root) = 64 AND lineage_root NOT GLOB '*[^0-9a-f]*'),
    created_at_epoch_us INTEGER NOT NULL CHECK(created_at_epoch_us >= 0)
) STRICT;

CREATE TABLE research_campaign_event (
    event_id TEXT PRIMARY KEY NOT NULL
        CHECK(length(event_id) > 0 AND trim(event_id) = event_id),
    campaign_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    event_type TEXT NOT NULL
        CHECK(length(event_type) > 0 AND trim(event_type) = event_type),
    previous_status TEXT
        CHECK(previous_status IS NULL OR previous_status IN (
            'draft', 'authorized', 'running', 'paused', 'paused_budget',
            'cancel_requested', 'cancelled', 'completed',
            'completed_with_failures', 'failed'
        )),
    status TEXT NOT NULL
        CHECK(status IN (
            'draft', 'authorized', 'running', 'paused', 'paused_budget',
            'cancel_requested', 'cancelled', 'completed',
            'completed_with_failures', 'failed'
        )),
    detail_json TEXT NOT NULL CHECK(json_valid(detail_json)),
    occurred_at_epoch_us INTEGER NOT NULL CHECK(occurred_at_epoch_us >= 0),
    FOREIGN KEY(campaign_id) REFERENCES research_campaign(campaign_id),
    UNIQUE(campaign_id, ordinal)
) STRICT;

CREATE TABLE research_candidate_lineage (
    campaign_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL
        CHECK(length(candidate_id) > 0 AND trim(candidate_id) = candidate_id),
    parent_candidate_id TEXT,
    ordinal INTEGER NOT NULL CHECK(ordinal > 0),
    generation INTEGER NOT NULL CHECK(generation BETWEEN 0 AND 6),
    candidate_hash TEXT NOT NULL
        CHECK(length(candidate_hash) = 64 AND candidate_hash NOT GLOB '*[^0-9a-f]*'),
    parameter_hash TEXT NOT NULL
        CHECK(length(parameter_hash) = 64 AND parameter_hash NOT GLOB '*[^0-9a-f]*'),
    search_axis TEXT NOT NULL
        CHECK(search_axis IN ('factor_code', 'model_code', 'parameters')),
    candidate_schema_version INTEGER NOT NULL CHECK(candidate_schema_version = 1),
    candidate_json TEXT NOT NULL CHECK(json_valid(candidate_json)),
    created_at_epoch_us INTEGER NOT NULL CHECK(created_at_epoch_us >= 0),
    PRIMARY KEY(campaign_id, candidate_id),
    FOREIGN KEY(campaign_id) REFERENCES research_campaign(campaign_id),
    FOREIGN KEY(campaign_id, parent_candidate_id)
        REFERENCES research_candidate_lineage(campaign_id, candidate_id),
    UNIQUE(campaign_id, ordinal),
    UNIQUE(campaign_id, candidate_hash),
    CHECK(parent_candidate_id IS NULL OR parent_candidate_id <> candidate_id)
) STRICT;

CREATE TABLE research_statistical_trial (
    trial_key TEXT PRIMARY KEY NOT NULL
        CHECK(length(trial_key) = 64 AND trial_key NOT GLOB '*[^0-9a-f]*'),
    campaign_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    origin_experiment_id TEXT NOT NULL
        CHECK(length(origin_experiment_id) > 0),
    logical_ordinal INTEGER NOT NULL CHECK(logical_ordinal > 0),
    parameter_hash TEXT NOT NULL
        CHECK(length(parameter_hash) = 64 AND parameter_hash NOT GLOB '*[^0-9a-f]*'),
    trial_kind TEXT NOT NULL CHECK(trial_kind IN ('prior', 'current')),
    candidate_hash TEXT NOT NULL
        CHECK(length(candidate_hash) = 64 AND candidate_hash NOT GLOB '*[^0-9a-f]*'),
    validation_protocol_hash TEXT NOT NULL
        CHECK(length(validation_protocol_hash) = 64 AND validation_protocol_hash NOT GLOB '*[^0-9a-f]*'),
    lineage_root TEXT NOT NULL
        CHECK(length(lineage_root) = 64 AND lineage_root NOT GLOB '*[^0-9a-f]*'),
    family_id TEXT NOT NULL CHECK(length(family_id) > 0),
    created_at_epoch_us INTEGER NOT NULL CHECK(created_at_epoch_us >= 0),
    FOREIGN KEY(campaign_id, candidate_id)
        REFERENCES research_candidate_lineage(campaign_id, candidate_id),
    UNIQUE(campaign_id, candidate_hash, validation_protocol_hash),
    UNIQUE(campaign_id, origin_experiment_id, candidate_id, logical_ordinal, parameter_hash)
) STRICT;

CREATE TABLE research_operational_attempt (
    attempt_id TEXT PRIMARY KEY NOT NULL
        CHECK(length(attempt_id) > 0 AND trim(attempt_id) = attempt_id),
    trial_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal > 0),
    parent_attempt_id TEXT,
    lineage_root TEXT NOT NULL
        CHECK(length(lineage_root) = 64 AND lineage_root NOT GLOB '*[^0-9a-f]*'),
    family_id TEXT NOT NULL CHECK(length(family_id) > 0),
    created_at_epoch_us INTEGER NOT NULL CHECK(created_at_epoch_us >= 0),
    FOREIGN KEY(trial_key) REFERENCES research_statistical_trial(trial_key),
    FOREIGN KEY(trial_key, parent_attempt_id)
        REFERENCES research_operational_attempt(trial_key, attempt_id),
    UNIQUE(trial_key, attempt_id),
    UNIQUE(trial_key, ordinal),
    CHECK(parent_attempt_id IS NULL OR parent_attempt_id <> attempt_id)
) STRICT;

CREATE TABLE research_code_artifact (
    artifact_hash TEXT PRIMARY KEY NOT NULL
        CHECK(length(artifact_hash) = 64 AND artifact_hash NOT GLOB '*[^0-9a-f]*'),
    source_code TEXT NOT NULL CHECK(length(source_code) > 0),
    source_hash TEXT NOT NULL
        CHECK(length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
    canonical_ast_hash TEXT NOT NULL
        CHECK(length(canonical_ast_hash) = 64 AND canonical_ast_hash NOT GLOB '*[^0-9a-f]*'),
    dependency_lock_hash TEXT NOT NULL
        CHECK(length(dependency_lock_hash) = 64 AND dependency_lock_hash NOT GLOB '*[^0-9a-f]*'),
    dependencies_json TEXT NOT NULL CHECK(json_valid(dependencies_json)),
    image_digest TEXT NOT NULL
        CHECK(length(image_digest) = 64 AND image_digest NOT GLOB '*[^0-9a-f]*'),
    input_schema_hash TEXT NOT NULL
        CHECK(length(input_schema_hash) = 64 AND input_schema_hash NOT GLOB '*[^0-9a-f]*'),
    output_schema_hash TEXT NOT NULL
        CHECK(length(output_schema_hash) = 64 AND output_schema_hash NOT GLOB '*[^0-9a-f]*'),
    created_at_epoch_us INTEGER NOT NULL CHECK(created_at_epoch_us >= 0)
) STRICT;

CREATE TABLE sandbox_execution_manifest (
    attestation_hash TEXT PRIMARY KEY NOT NULL
        CHECK(length(attestation_hash) = 64 AND attestation_hash NOT GLOB '*[^0-9a-f]*'),
    campaign_id TEXT NOT NULL,
    attempt_id TEXT,
    code_artifact_hash TEXT NOT NULL,
    runtime_digest TEXT NOT NULL
        CHECK(length(runtime_digest) = 64 AND runtime_digest NOT GLOB '*[^0-9a-f]*'),
    cpu_count INTEGER NOT NULL CHECK(cpu_count > 0),
    memory_bytes INTEGER NOT NULL CHECK(memory_bytes > 0),
    process_limit INTEGER NOT NULL CHECK(process_limit > 0),
    temporary_storage_bytes INTEGER NOT NULL CHECK(temporary_storage_bytes > 0),
    wall_time_seconds INTEGER NOT NULL CHECK(wall_time_seconds > 0),
    output_bytes INTEGER NOT NULL CHECK(output_bytes > 0),
    input_hash TEXT NOT NULL
        CHECK(length(input_hash) = 64 AND input_hash NOT GLOB '*[^0-9a-f]*'),
    output_hash TEXT
        CHECK(output_hash IS NULL OR (length(output_hash) = 64 AND output_hash NOT GLOB '*[^0-9a-f]*')),
    seed INTEGER NOT NULL CHECK(seed >= 0),
    exit_status TEXT NOT NULL
        CHECK(exit_status IN ('succeeded', 'rejected', 'failed', 'timed_out', 'resource_exhausted')),
    exit_code INTEGER,
    created_at_epoch_us INTEGER NOT NULL CHECK(created_at_epoch_us >= 0),
    FOREIGN KEY(campaign_id) REFERENCES research_campaign(campaign_id),
    FOREIGN KEY(attempt_id) REFERENCES research_operational_attempt(attempt_id),
    FOREIGN KEY(code_artifact_hash) REFERENCES research_code_artifact(artifact_hash),
    CHECK(
        (exit_status = 'succeeded' AND output_hash IS NOT NULL AND exit_code = 0)
        OR (exit_status <> 'succeeded' AND (exit_code IS NULL OR exit_code <> 0))
    )
) STRICT;

CREATE TABLE research_feedback (
    feedback_id TEXT PRIMARY KEY NOT NULL
        CHECK(length(feedback_id) > 0 AND trim(feedback_id) = feedback_id),
    campaign_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    evaluation_result_hash TEXT NOT NULL
        CHECK(length(evaluation_result_hash) = 64 AND evaluation_result_hash NOT GLOB '*[^0-9a-f]*'),
    summary TEXT NOT NULL CHECK(length(summary) > 0),
    evidence_refs_json TEXT NOT NULL CHECK(json_valid(evidence_refs_json)),
    outcome_known_at_epoch_us INTEGER NOT NULL CHECK(outcome_known_at_epoch_us >= 0),
    snapshot_id TEXT NOT NULL CHECK(length(snapshot_id) > 0),
    source TEXT NOT NULL
        CHECK(source IN ('host_validation', 'independent_replication', 'human_review')),
    FOREIGN KEY(campaign_id, candidate_id)
        REFERENCES research_candidate_lineage(campaign_id, candidate_id),
    UNIQUE(campaign_id, evaluation_result_hash, candidate_id)
) STRICT;

CREATE TABLE research_knowledge (
    knowledge_id TEXT PRIMARY KEY NOT NULL
        CHECK(length(knowledge_id) > 0 AND trim(knowledge_id) = knowledge_id),
    campaign_id TEXT NOT NULL,
    claim TEXT NOT NULL CHECK(length(claim) > 0),
    scope TEXT NOT NULL
        CHECK(scope IN ('campaign-local', 'strategy-family', 'global')),
    scope_ref TEXT,
    evidence_refs_json TEXT NOT NULL CHECK(json_valid(evidence_refs_json)),
    outcome_known_at_epoch_us INTEGER NOT NULL CHECK(outcome_known_at_epoch_us >= 0),
    snapshot_id TEXT NOT NULL CHECK(length(snapshot_id) > 0),
    source TEXT NOT NULL
        CHECK(source IN ('host_validation', 'independent_replication', 'human_review')),
    source_hash TEXT NOT NULL
        CHECK(length(source_hash) = 64 AND source_hash NOT GLOB '*[^0-9a-f]*'),
    initial_status TEXT NOT NULL
        CHECK(initial_status IN ('active', 'invalidated', 'contradicted', 'revoked')),
    promotion_receipt_hash TEXT
        CHECK(promotion_receipt_hash IS NULL OR (length(promotion_receipt_hash) = 64 AND promotion_receipt_hash NOT GLOB '*[^0-9a-f]*')),
    independent_evidence_hash TEXT
        CHECK(independent_evidence_hash IS NULL OR (length(independent_evidence_hash) = 64 AND independent_evidence_hash NOT GLOB '*[^0-9a-f]*')),
    FOREIGN KEY(campaign_id) REFERENCES research_campaign(campaign_id),
    CHECK(
        (scope = 'campaign-local' AND scope_ref IS NULL
            AND promotion_receipt_hash IS NULL AND independent_evidence_hash IS NULL)
        OR (scope = 'strategy-family' AND length(scope_ref) > 0
            AND promotion_receipt_hash IS NOT NULL AND independent_evidence_hash IS NOT NULL)
        OR (scope = 'global' AND scope_ref IS NULL
            AND promotion_receipt_hash IS NOT NULL AND independent_evidence_hash IS NOT NULL)
    )
) STRICT;

CREATE TABLE research_knowledge_status_event (
    event_id TEXT PRIMARY KEY NOT NULL
        CHECK(length(event_id) > 0 AND trim(event_id) = event_id),
    knowledge_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal > 0),
    previous_status TEXT NOT NULL
        CHECK(previous_status IN ('active', 'invalidated', 'contradicted')),
    status TEXT NOT NULL
        CHECK(status IN ('invalidated', 'contradicted', 'revoked')),
    outcome_known_at_epoch_us INTEGER NOT NULL CHECK(outcome_known_at_epoch_us >= 0),
    evidence_hash TEXT NOT NULL
        CHECK(length(evidence_hash) = 64 AND evidence_hash NOT GLOB '*[^0-9a-f]*'),
    FOREIGN KEY(knowledge_id) REFERENCES research_knowledge(knowledge_id),
    UNIQUE(knowledge_id, ordinal),
    CHECK(
        CASE previous_status
            WHEN 'active' THEN 0
            WHEN 'invalidated' THEN 1
            WHEN 'contradicted' THEN 2
        END
        <
        CASE status
            WHEN 'invalidated' THEN 1
            WHEN 'contradicted' THEN 2
            WHEN 'revoked' THEN 3
        END
    )
) STRICT;

CREATE INDEX ix_research_campaign_event_stream
    ON research_campaign_event(campaign_id, ordinal);
CREATE INDEX ix_research_candidate_parent
    ON research_candidate_lineage(campaign_id, parent_candidate_id);
CREATE INDEX ix_research_statistical_trial_family
    ON research_statistical_trial(campaign_id, family_id, logical_ordinal);
CREATE INDEX ix_research_operational_attempt_trial
    ON research_operational_attempt(trial_key, ordinal);
CREATE INDEX ix_sandbox_execution_campaign
    ON sandbox_execution_manifest(campaign_id, created_at_epoch_us);
CREATE INDEX ix_research_feedback_visible
    ON research_feedback(campaign_id, outcome_known_at_epoch_us);
CREATE INDEX ix_research_knowledge_visible
    ON research_knowledge(campaign_id, outcome_known_at_epoch_us, scope);
CREATE INDEX ix_research_knowledge_event_stream
    ON research_knowledge_status_event(knowledge_id, ordinal);

CREATE TRIGGER trg_research_campaign_no_update
BEFORE UPDATE ON research_campaign BEGIN
    SELECT RAISE(ABORT, 'research_campaign is immutable');
END;
CREATE TRIGGER trg_research_campaign_no_delete
BEFORE DELETE ON research_campaign BEGIN
    SELECT RAISE(ABORT, 'research_campaign is immutable');
END;
CREATE TRIGGER trg_research_campaign_event_no_update
BEFORE UPDATE ON research_campaign_event BEGIN
    SELECT RAISE(ABORT, 'research_campaign_event is append-only');
END;
CREATE TRIGGER trg_research_campaign_event_no_delete
BEFORE DELETE ON research_campaign_event BEGIN
    SELECT RAISE(ABORT, 'research_campaign_event is append-only');
END;
CREATE TRIGGER trg_research_campaign_event_guard
BEFORE INSERT ON research_campaign_event BEGIN
    SELECT CASE WHEN NEW.ordinal <> COALESCE(
        (
            SELECT MAX(ordinal) + 1 FROM research_campaign_event
            WHERE campaign_id = NEW.campaign_id
        ),
        0
    ) THEN RAISE(ABORT, 'campaign event ordinal is not contiguous') END;
    SELECT CASE WHEN NEW.previous_status IS NOT (
        SELECT status FROM research_campaign_event
        WHERE campaign_id = NEW.campaign_id
        ORDER BY ordinal DESC LIMIT 1
    ) THEN RAISE(ABORT, 'campaign event predecessor mismatch') END;
    SELECT CASE WHEN NEW.occurred_at_epoch_us < COALESCE(
        (
            SELECT occurred_at_epoch_us FROM research_campaign_event
            WHERE campaign_id = NEW.campaign_id
            ORDER BY ordinal DESC LIMIT 1
        ),
        (
            SELECT created_at_epoch_us FROM research_campaign
            WHERE campaign_id = NEW.campaign_id
        )
    ) THEN RAISE(ABORT, 'campaign event time is not monotonic') END;
END;
CREATE TRIGGER trg_research_candidate_lineage_no_update
BEFORE UPDATE ON research_candidate_lineage BEGIN
    SELECT RAISE(ABORT, 'research_candidate_lineage is immutable');
END;
CREATE TRIGGER trg_research_candidate_lineage_no_delete
BEFORE DELETE ON research_candidate_lineage BEGIN
    SELECT RAISE(ABORT, 'research_candidate_lineage is immutable');
END;
CREATE TRIGGER trg_research_statistical_trial_no_update
BEFORE UPDATE ON research_statistical_trial BEGIN
    SELECT RAISE(ABORT, 'research_statistical_trial is immutable');
END;
CREATE TRIGGER trg_research_statistical_trial_no_delete
BEFORE DELETE ON research_statistical_trial BEGIN
    SELECT RAISE(ABORT, 'research_statistical_trial is immutable');
END;
CREATE TRIGGER trg_research_operational_attempt_no_update
BEFORE UPDATE ON research_operational_attempt BEGIN
    SELECT RAISE(ABORT, 'research_operational_attempt is immutable');
END;
CREATE TRIGGER trg_research_operational_attempt_no_delete
BEFORE DELETE ON research_operational_attempt BEGIN
    SELECT RAISE(ABORT, 'research_operational_attempt is immutable');
END;
CREATE TRIGGER trg_research_code_artifact_no_update
BEFORE UPDATE ON research_code_artifact BEGIN
    SELECT RAISE(ABORT, 'research_code_artifact is immutable');
END;
CREATE TRIGGER trg_research_code_artifact_no_delete
BEFORE DELETE ON research_code_artifact BEGIN
    SELECT RAISE(ABORT, 'research_code_artifact is immutable');
END;
CREATE TRIGGER trg_sandbox_execution_manifest_no_update
BEFORE UPDATE ON sandbox_execution_manifest BEGIN
    SELECT RAISE(ABORT, 'sandbox_execution_manifest is immutable');
END;
CREATE TRIGGER trg_sandbox_execution_manifest_no_delete
BEFORE DELETE ON sandbox_execution_manifest BEGIN
    SELECT RAISE(ABORT, 'sandbox_execution_manifest is immutable');
END;
CREATE TRIGGER trg_research_feedback_no_update
BEFORE UPDATE ON research_feedback BEGIN
    SELECT RAISE(ABORT, 'research_feedback is immutable');
END;
CREATE TRIGGER trg_research_feedback_no_delete
BEFORE DELETE ON research_feedback BEGIN
    SELECT RAISE(ABORT, 'research_feedback is immutable');
END;
CREATE TRIGGER trg_research_knowledge_no_update
BEFORE UPDATE ON research_knowledge BEGIN
    SELECT RAISE(ABORT, 'research_knowledge is immutable');
END;
CREATE TRIGGER trg_research_knowledge_no_delete
BEFORE DELETE ON research_knowledge BEGIN
    SELECT RAISE(ABORT, 'research_knowledge is immutable');
END;
CREATE TRIGGER trg_research_knowledge_status_event_no_update
BEFORE UPDATE ON research_knowledge_status_event BEGIN
    SELECT RAISE(ABORT, 'research_knowledge_status_event is append-only');
END;
CREATE TRIGGER trg_research_knowledge_status_event_no_delete
BEFORE DELETE ON research_knowledge_status_event BEGIN
    SELECT RAISE(ABORT, 'research_knowledge_status_event is append-only');
END;

CREATE TRIGGER trg_research_knowledge_status_event_guard
BEFORE INSERT ON research_knowledge_status_event BEGIN
    SELECT CASE WHEN NEW.previous_status <> COALESCE(
        (
            SELECT status FROM research_knowledge_status_event
            WHERE knowledge_id = NEW.knowledge_id
            ORDER BY ordinal DESC LIMIT 1
        ),
        (
            SELECT initial_status FROM research_knowledge
            WHERE knowledge_id = NEW.knowledge_id
        )
    ) THEN RAISE(ABORT, 'knowledge status predecessor mismatch') END;
    SELECT CASE WHEN NEW.ordinal <> COALESCE(
        (
            SELECT MAX(ordinal) + 1 FROM research_knowledge_status_event
            WHERE knowledge_id = NEW.knowledge_id
        ),
        1
    ) THEN RAISE(ABORT, 'knowledge status ordinal is not contiguous') END;
    SELECT CASE WHEN NEW.outcome_known_at_epoch_us < (
        SELECT outcome_known_at_epoch_us FROM research_knowledge
        WHERE knowledge_id = NEW.knowledge_id
    ) THEN RAISE(ABORT, 'knowledge status predates knowledge') END;
END;

CREATE TRIGGER trg_research_operational_attempt_guard
BEFORE INSERT ON research_operational_attempt BEGIN
    SELECT CASE WHEN NEW.lineage_root <> (
        SELECT lineage_root FROM research_statistical_trial
        WHERE trial_key = NEW.trial_key
    ) OR NEW.family_id <> (
        SELECT family_id FROM research_statistical_trial
        WHERE trial_key = NEW.trial_key
    ) THEN RAISE(ABORT, 'attempt cannot reset trial lineage or family') END;
    SELECT CASE WHEN NEW.ordinal = 1 AND NEW.parent_attempt_id IS NOT NULL
        THEN RAISE(ABORT, 'first operational attempt cannot have a parent') END;
    SELECT CASE WHEN NEW.ordinal > 1 AND NEW.parent_attempt_id IS NULL
        THEN RAISE(ABORT, 'retry requires a parent attempt') END;
    SELECT CASE WHEN NEW.parent_attempt_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM research_operational_attempt parent
        WHERE parent.trial_key = NEW.trial_key
          AND parent.attempt_id = NEW.parent_attempt_id
          AND parent.ordinal < NEW.ordinal
    ) THEN RAISE(ABORT, 'retry parent must be an earlier attempt of the same trial') END;
END;

CREATE TRIGGER trg_research_candidate_lineage_guard
BEFORE INSERT ON research_candidate_lineage BEGIN
    SELECT CASE WHEN NEW.search_axis <> (
        SELECT search_axis FROM research_campaign
        WHERE campaign_id = NEW.campaign_id
    ) THEN RAISE(ABORT, 'candidate cannot change the campaign search axis') END;
    SELECT CASE WHEN NEW.parent_candidate_id IS NULL AND NEW.generation <> 0
        THEN RAISE(ABORT, 'root candidate must be generation zero') END;
    SELECT CASE WHEN NEW.parent_candidate_id IS NOT NULL AND NEW.generation <> (
        SELECT generation + 1 FROM research_candidate_lineage
        WHERE campaign_id = NEW.campaign_id
          AND candidate_id = NEW.parent_candidate_id
    ) THEN RAISE(ABORT, 'child generation must immediately follow its parent') END;
END;

CREATE TRIGGER trg_research_statistical_trial_guard
BEFORE INSERT ON research_statistical_trial BEGIN
    SELECT CASE WHEN NEW.lineage_root <> (
        SELECT lineage_root FROM research_campaign
        WHERE campaign_id = NEW.campaign_id
    ) THEN RAISE(ABORT, 'trial cannot reset campaign lineage') END;
    SELECT CASE WHEN NEW.candidate_hash <> (
        SELECT candidate_hash FROM research_candidate_lineage
        WHERE campaign_id = NEW.campaign_id
          AND candidate_id = NEW.candidate_id
    ) OR NEW.parameter_hash <> (
        SELECT parameter_hash FROM research_candidate_lineage
        WHERE campaign_id = NEW.campaign_id
          AND candidate_id = NEW.candidate_id
    ) THEN RAISE(ABORT, 'trial hashes must match the persisted candidate') END;
END;

CREATE TRIGGER trg_sandbox_execution_manifest_guard
BEFORE INSERT ON sandbox_execution_manifest
WHEN NEW.attempt_id IS NOT NULL BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1
        FROM research_operational_attempt attempt
        JOIN research_statistical_trial trial USING(trial_key)
        WHERE attempt.attempt_id = NEW.attempt_id
          AND trial.campaign_id = NEW.campaign_id
    ) THEN RAISE(ABORT, 'sandbox attempt must belong to its campaign') END;
END;

CREATE TRIGGER trg_research_knowledge_status_known_at_guard
BEFORE INSERT ON research_knowledge_status_event BEGIN
    SELECT CASE WHEN NEW.outcome_known_at_epoch_us < COALESCE(
        (
            SELECT outcome_known_at_epoch_us
            FROM research_knowledge_status_event
            WHERE knowledge_id = NEW.knowledge_id
            ORDER BY ordinal DESC LIMIT 1
        ),
        (
            SELECT outcome_known_at_epoch_us FROM research_knowledge
            WHERE knowledge_id = NEW.knowledge_id
        )
    ) THEN RAISE(ABORT, 'knowledge status known-at must be monotonic') END;
END;

PRAGMA user_version = 2;

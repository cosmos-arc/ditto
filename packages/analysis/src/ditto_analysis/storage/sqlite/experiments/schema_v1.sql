-- Ditto R3 Task 7 research experiment control-plane schema v1.
--
-- Approval artifact only. This file is not executed directly. The analysis-owned
-- migration coordinator acquires BEGIN IMMEDIATE, re-reads database markers and
-- sqlite_schema while holding the write lock, executes these statements one by
-- one, writes application_id/user_version last, and then commits. It must never
-- call sqlite3.Connection.executescript() inside the migration transaction.

CREATE TABLE experiment (
    experiment_id TEXT PRIMARY KEY
        CHECK (
            experiment_id = trim(experiment_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND experiment_id <> ''
        ),
    research_cycle_id TEXT NOT NULL
        CHECK (
            research_cycle_id = trim(research_cycle_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND research_cycle_id <> ''
        ),
    research_cycle_hash TEXT NOT NULL
        CHECK (
            length(research_cycle_hash) = 64
            AND research_cycle_hash NOT GLOB '*[^0-9a-f]*'
        ),
    strategy_version TEXT NOT NULL
        CHECK (
            strategy_version = trim(strategy_version, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND strategy_version <> ''
        ),
    strategy_spec_hash TEXT NOT NULL
        CHECK (
            length(strategy_spec_hash) = 64
            AND strategy_spec_hash NOT GLOB '*[^0-9a-f]*'
        ),
    snapshot_id TEXT NOT NULL
        CHECK (
            snapshot_id = trim(snapshot_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND snapshot_id <> ''
        ),
    launch_spec_schema_version INTEGER NOT NULL
        CHECK (launch_spec_schema_version > 0),
    launch_spec_json TEXT NOT NULL
        CHECK (
            json_valid(launch_spec_json)
            AND json_type(launch_spec_json) = 'object'
        ),
    launch_spec_hash TEXT NOT NULL
        CHECK (
            length(launch_spec_hash) = 64
            AND launch_spec_hash NOT GLOB '*[^0-9a-f]*'
        ),
    queue_ordinal INTEGER
        CHECK (
            queue_ordinal IS NULL
            OR queue_ordinal > 0
        ),
    status TEXT NOT NULL CHECK (status IN (
        'draft',
        'blocked',
        'queued',
        'running',
        'pause_requested',
        'paused',
        'cancel_requested',
        'cancelled',
        'completed',
        'completed_with_failures',
        'failed'
    )),
    desired_state TEXT NOT NULL
        CHECK (desired_state IN ('run', 'pause', 'cancel')),
    stage TEXT NOT NULL CHECK (stage IN (
        'preflight',
        'exploration',
        'walk_forward',
        'candidate_selection',
        'holdout',
        'evidence'
    )),
    failure_code TEXT CHECK (
        failure_code IS NULL
        OR failure_code IN (
            'snapshot_not_certified',
            'insufficient_history',
            'candidate_failed',
            'input_hash_mismatch',
            'lease_lost',
            'system_error'
        )
    ),
    created_at_epoch_us INTEGER NOT NULL
        CHECK (created_at_epoch_us >= 0),
    updated_at_epoch_us INTEGER NOT NULL
        CHECK (updated_at_epoch_us >= created_at_epoch_us),
    revision INTEGER NOT NULL DEFAULT 0
        CHECK (revision >= 0),
    UNIQUE (
        experiment_id,
        research_cycle_id,
        research_cycle_hash
    ),
    CHECK (
        (
            status IN ('draft', 'blocked')
            AND queue_ordinal IS NULL
        )
        OR (
            status NOT IN ('draft', 'blocked')
            AND queue_ordinal IS NOT NULL
        )
    ),
    CHECK (
        (
            status = 'blocked'
            AND (
                failure_code IS NULL
                OR failure_code IN (
                    'snapshot_not_certified',
                    'insufficient_history'
                )
            )
        )
        OR (
            status = 'completed_with_failures'
            AND failure_code IS NOT NULL
            AND failure_code = 'candidate_failed'
        )
        OR (
            status = 'failed'
            AND failure_code IS NOT NULL
            AND failure_code IN (
                'input_hash_mismatch',
                'lease_lost',
                'system_error'
            )
        )
        OR (
            status NOT IN (
                'blocked',
                'completed_with_failures',
                'failed'
            )
            AND failure_code IS NULL
        )
    )
) STRICT;

CREATE INDEX ix_experiment_research_cycle
ON experiment(research_cycle_hash, experiment_id);

CREATE UNIQUE INDEX ux_experiment_queue_ordinal
ON experiment(queue_ordinal)
WHERE queue_ordinal IS NOT NULL;

CREATE INDEX ix_experiment_dispatch_queue
ON experiment(status, queue_ordinal, experiment_id);

CREATE TABLE experiment_candidate (
    experiment_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL
        CHECK (
            candidate_id = trim(candidate_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND candidate_id <> ''
        ),
    ordinal INTEGER NOT NULL
        CHECK (ordinal > 0),
    is_baseline INTEGER NOT NULL
        CHECK (is_baseline IN (0, 1)),
    parameters_json TEXT NOT NULL
        CHECK (
            json_valid(parameters_json)
            AND json_type(parameters_json) = 'object'
        ),
    parameters_hash TEXT NOT NULL
        CHECK (
            length(parameters_hash) = 64
            AND parameters_hash NOT GLOB '*[^0-9a-f]*'
        ),
    PRIMARY KEY (experiment_id, candidate_id),
    UNIQUE (experiment_id, ordinal),
    UNIQUE (experiment_id, parameters_hash),
    FOREIGN KEY (experiment_id)
        REFERENCES experiment(experiment_id)
        ON DELETE RESTRICT
) STRICT;

CREATE UNIQUE INDEX ux_experiment_candidate_baseline
ON experiment_candidate(experiment_id)
WHERE is_baseline = 1;

CREATE TABLE experiment_fold (
    experiment_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    fold_id TEXT NOT NULL
        CHECK (
            fold_id = trim(fold_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND fold_id <> ''
        ),
    ordinal INTEGER NOT NULL
        CHECK (ordinal > 0),
    fold_role TEXT NOT NULL CHECK (fold_role IN (
        'exploration',
        'walk_forward',
        'holdout'
    )),
    train_start TEXT,
    train_end TEXT,
    test_start TEXT NOT NULL
        CHECK (
            length(test_start) = 10
            AND test_start GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND date(test_start) IS NOT NULL
            AND date(test_start) = test_start
        ),
    test_end TEXT NOT NULL
        CHECK (
            length(test_end) = 10
            AND test_end GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND date(test_end) IS NOT NULL
            AND date(test_end) = test_end
        ),
    purge_sessions INTEGER NOT NULL
        CHECK (purge_sessions >= 0),
    embargo_sessions INTEGER NOT NULL
        CHECK (embargo_sessions >= 0),
    fold_spec_json TEXT NOT NULL
        CHECK (
            json_valid(fold_spec_json)
            AND json_type(fold_spec_json) = 'object'
        ),
    fold_spec_hash TEXT NOT NULL
        CHECK (
            length(fold_spec_hash) = 64
            AND fold_spec_hash NOT GLOB '*[^0-9a-f]*'
        ),
    status TEXT NOT NULL CHECK (status IN (
        'queued',
        'running',
        'cancelled',
        'completed',
        'failed'
    )),
    claim_owner_token TEXT
        CHECK (
            claim_owner_token IS NULL
            OR (
                claim_owner_token = trim(claim_owner_token, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
                AND claim_owner_token <> ''
            )
        ),
    created_at_epoch_us INTEGER NOT NULL
        CHECK (created_at_epoch_us >= 0),
    updated_at_epoch_us INTEGER NOT NULL
        CHECK (updated_at_epoch_us >= created_at_epoch_us),
    revision INTEGER NOT NULL DEFAULT 0
        CHECK (revision >= 0),
    PRIMARY KEY (experiment_id, candidate_id, fold_id),
    UNIQUE (experiment_id, candidate_id, ordinal),
    UNIQUE (
        experiment_id,
        candidate_id,
        fold_id,
        fold_role
    ),
    CHECK (test_start <= test_end),
    CHECK (
        (
            fold_role = 'exploration'
            AND train_start IS NULL
            AND train_end IS NULL
        )
        OR (
            fold_role IN ('walk_forward', 'holdout')
            AND train_start IS NOT NULL
            AND train_end IS NOT NULL
            AND length(train_start) = 10
            AND length(train_end) = 10
            AND train_start GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND train_end GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND date(train_start) IS NOT NULL
            AND date(train_end) IS NOT NULL
            AND date(train_start) = train_start
            AND date(train_end) = train_end
            AND train_start <= train_end
            AND train_end < test_start
        )
    ),
    CHECK (
        (
            status = 'running'
            AND claim_owner_token IS NOT NULL
        )
        OR (
            status <> 'running'
            AND claim_owner_token IS NULL
        )
    ),
    FOREIGN KEY (experiment_id, candidate_id)
        REFERENCES experiment_candidate(experiment_id, candidate_id)
        ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_experiment_fold_dispatch
ON experiment_fold(
    experiment_id,
    fold_role,
    status,
    ordinal,
    candidate_id
);

CREATE TABLE experiment_attempt (
    attempt_id TEXT PRIMARY KEY
        CHECK (
            attempt_id = trim(attempt_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND attempt_id <> ''
        ),
    experiment_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    fold_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL
        CHECK (ordinal > 0),
    parent_attempt_id TEXT
        CHECK (
            parent_attempt_id IS NULL
            OR (
                parent_attempt_id = trim(parent_attempt_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
                AND parent_attempt_id <> ''
            )
        ),
    status TEXT NOT NULL CHECK (status IN (
        'queued',
        'running',
        'cancelled',
        'completed',
        'failed'
    )),
    backtest_run_id TEXT
        CHECK (
            backtest_run_id IS NULL
            OR (
                backtest_run_id = trim(backtest_run_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
                AND backtest_run_id <> ''
            )
        ),
    resume_from_run_id TEXT
        CHECK (
            resume_from_run_id IS NULL
            OR (
                resume_from_run_id = trim(resume_from_run_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
                AND resume_from_run_id <> ''
            )
        ),
    checkpoint_ref TEXT
        CHECK (
            checkpoint_ref IS NULL
            OR (
                checkpoint_ref = trim(checkpoint_ref, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
                AND checkpoint_ref <> ''
            )
        ),
    reproduction_fingerprint TEXT NOT NULL
        CHECK (
            length(reproduction_fingerprint) = 64
            AND reproduction_fingerprint NOT GLOB '*[^0-9a-f]*'
        ),
    failure_code TEXT CHECK (
        failure_code IS NULL
        OR failure_code IN (
            'candidate_failed',
            'input_hash_mismatch',
            'lease_lost',
            'system_error'
        )
    ),
    created_at_epoch_us INTEGER NOT NULL
        CHECK (created_at_epoch_us >= 0),
    updated_at_epoch_us INTEGER NOT NULL
        CHECK (updated_at_epoch_us >= created_at_epoch_us),
    revision INTEGER NOT NULL DEFAULT 0
        CHECK (revision >= 0),
    UNIQUE (fold_id, attempt_id),
    UNIQUE (experiment_id, candidate_id, fold_id, attempt_id),
    UNIQUE (experiment_id, candidate_id, attempt_id),
    UNIQUE (experiment_id, candidate_id, fold_id, ordinal),
    CHECK (
        (ordinal = 1 AND parent_attempt_id IS NULL)
        OR (ordinal > 1 AND parent_attempt_id IS NOT NULL)
    ),
    CHECK (
        parent_attempt_id IS NULL
        OR parent_attempt_id <> attempt_id
    ),
    CHECK (
        (status = 'failed' AND failure_code IS NOT NULL)
        OR (status <> 'failed' AND failure_code IS NULL)
    ),
    CHECK (
        status NOT IN ('running', 'completed')
        OR backtest_run_id IS NOT NULL
    ),
    FOREIGN KEY (experiment_id, candidate_id, fold_id)
        REFERENCES experiment_fold(experiment_id, candidate_id, fold_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (
        experiment_id,
        candidate_id,
        fold_id,
        parent_attempt_id
    ) REFERENCES experiment_attempt(
        experiment_id,
        candidate_id,
        fold_id,
        attempt_id
    ) ON DELETE RESTRICT
) STRICT;

CREATE UNIQUE INDEX ux_experiment_attempt_live_fold
ON experiment_attempt(experiment_id, candidate_id, fold_id)
WHERE status IN ('queued', 'running');

CREATE UNIQUE INDEX ux_experiment_attempt_backtest_run
ON experiment_attempt(backtest_run_id)
WHERE backtest_run_id IS NOT NULL;

CREATE TABLE experiment_status_event (
    event_id TEXT PRIMARY KEY
        CHECK (
            event_id = trim(event_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND event_id <> ''
        ),
    experiment_id TEXT NOT NULL,
    candidate_id TEXT,
    fold_id TEXT,
    attempt_id TEXT,
    subject_type TEXT NOT NULL CHECK (subject_type IN (
        'experiment',
        'fold',
        'attempt'
    )),
    subject_revision INTEGER NOT NULL
        CHECK (subject_revision >= 0),
    previous_status TEXT,
    status TEXT NOT NULL CHECK (status IN (
        'draft',
        'blocked',
        'queued',
        'running',
        'pause_requested',
        'paused',
        'cancel_requested',
        'cancelled',
        'completed',
        'completed_with_failures',
        'failed'
    )),
    desired_state TEXT CHECK (
        desired_state IS NULL
        OR desired_state IN ('run', 'pause', 'cancel')
    ),
    stage TEXT CHECK (
        stage IS NULL
        OR stage IN (
            'preflight',
            'exploration',
            'walk_forward',
            'candidate_selection',
            'holdout',
            'evidence'
        )
    ),
    failure_code TEXT CHECK (
        failure_code IS NULL
        OR failure_code IN (
            'snapshot_not_certified',
            'insufficient_history',
            'candidate_failed',
            'input_hash_mismatch',
            'lease_lost',
            'system_error'
        )
    ),
    reason_code TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}'
        CHECK (
            json_valid(detail_json)
            AND json_type(detail_json) = 'object'
        ),
    detail_hash TEXT NOT NULL
        CHECK (
            length(detail_hash) = 64
            AND detail_hash NOT GLOB '*[^0-9a-f]*'
        ),
    occurred_at_epoch_us INTEGER NOT NULL
        CHECK (occurred_at_epoch_us >= 0),
    CHECK (
        previous_status IS NULL
        OR previous_status IN (
            'draft',
            'blocked',
            'queued',
            'running',
            'pause_requested',
            'paused',
            'cancel_requested',
            'cancelled',
            'completed',
            'completed_with_failures',
            'failed'
        )
    ),
    CHECK (
        (
            subject_revision = 0
            AND previous_status IS NULL
        )
        OR (
            subject_revision > 0
            AND previous_status IS NOT NULL
        )
    ),
    CHECK (
        (
            subject_type = 'experiment'
            AND candidate_id IS NULL
            AND fold_id IS NULL
            AND attempt_id IS NULL
            AND desired_state IS NOT NULL
            AND stage IS NOT NULL
        )
        OR (
            subject_type = 'fold'
            AND candidate_id IS NOT NULL
            AND fold_id IS NOT NULL
            AND attempt_id IS NULL
            AND desired_state IS NULL
            AND stage IS NULL
        )
        OR (
            subject_type = 'attempt'
            AND candidate_id IS NOT NULL
            AND fold_id IS NOT NULL
            AND attempt_id IS NOT NULL
            AND desired_state IS NULL
            AND stage IS NULL
        )
    ),
    CHECK (
        subject_type = 'experiment'
        OR status IN (
            'queued',
            'running',
            'cancelled',
            'completed',
            'failed'
        )
    ),
    CHECK (
        subject_type = 'experiment'
        OR previous_status IS NULL
        OR previous_status IN (
            'queued',
            'running',
            'cancelled',
            'completed',
            'failed'
        )
    ),
    CHECK (
        (
            subject_type IN ('fold', 'attempt')
            AND status = 'failed'
            AND failure_code IS NOT NULL
            AND failure_code IN (
                'candidate_failed',
                'input_hash_mismatch',
                'lease_lost',
                'system_error'
            )
        )
        OR (
            subject_type IN ('fold', 'attempt')
            AND status <> 'failed'
            AND failure_code IS NULL
        )
        OR subject_type = 'experiment'
    ),
    CHECK (
        subject_type <> 'experiment'
        OR (
            status = 'blocked'
            AND (
                failure_code IS NULL
                OR failure_code IN (
                    'snapshot_not_certified',
                    'insufficient_history'
                )
            )
        )
        OR (
            subject_type = 'experiment'
            AND status = 'completed_with_failures'
            AND failure_code IS NOT NULL
            AND failure_code = 'candidate_failed'
        )
        OR (
            subject_type = 'experiment'
            AND status = 'failed'
            AND failure_code IS NOT NULL
            AND failure_code IN (
                'input_hash_mismatch',
                'lease_lost',
                'system_error'
            )
        )
        OR (
            subject_type = 'experiment'
            AND status NOT IN (
                'blocked',
                'completed_with_failures',
                'failed'
            )
            AND failure_code IS NULL
        )
    ),
    FOREIGN KEY (experiment_id)
        REFERENCES experiment(experiment_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, candidate_id, fold_id)
        REFERENCES experiment_fold(experiment_id, candidate_id, fold_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, candidate_id, fold_id, attempt_id)
        REFERENCES experiment_attempt(
            experiment_id,
            candidate_id,
            fold_id,
            attempt_id
        ) ON DELETE RESTRICT
) STRICT;

CREATE UNIQUE INDEX ux_experiment_status_event_experiment_revision
ON experiment_status_event(experiment_id, subject_revision)
WHERE subject_type = 'experiment';

CREATE UNIQUE INDEX ux_experiment_status_event_fold_revision
ON experiment_status_event(
    experiment_id,
    candidate_id,
    fold_id,
    subject_revision
)
WHERE subject_type = 'fold';

CREATE UNIQUE INDEX ux_experiment_status_event_attempt_revision
ON experiment_status_event(
    experiment_id,
    candidate_id,
    fold_id,
    attempt_id,
    subject_revision
)
WHERE subject_type = 'attempt';

CREATE INDEX ix_experiment_status_event_stream
ON experiment_status_event(
    experiment_id,
    occurred_at_epoch_us,
    event_id
);

CREATE TABLE research_artifact (
    artifact_id TEXT PRIMARY KEY
        CHECK (
            artifact_id = trim(artifact_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND artifact_id <> ''
        ),
    experiment_id TEXT NOT NULL,
    candidate_id TEXT,
    fold_id TEXT,
    attempt_id TEXT,
    artifact_kind TEXT NOT NULL
        CHECK (
            artifact_kind = trim(artifact_kind, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND artifact_kind <> ''
        ),
    relative_path TEXT NOT NULL
        CHECK (
            relative_path = trim(relative_path, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND relative_path <> ''
            AND substr(relative_path, 1, 1) <> '/'
            AND relative_path NOT GLOB '[A-Za-z]:*'
            AND instr(relative_path, char(0)) = 0
            AND instr(relative_path, char(92)) = 0
            AND instr(relative_path, '//') = 0
            AND relative_path NOT IN ('.', '..')
            AND relative_path NOT LIKE './%'
            AND relative_path NOT LIKE '../%'
            AND relative_path NOT LIKE '%/./%'
            AND relative_path NOT LIKE '%/../%'
            AND relative_path NOT LIKE '%/.'
            AND relative_path NOT LIKE '%/..'
        ),
    content_hash TEXT NOT NULL
        CHECK (
            length(content_hash) = 64
            AND content_hash NOT GLOB '*[^0-9a-f]*'
        ),
    schema_hash TEXT NOT NULL
        CHECK (
            length(schema_hash) = 64
            AND schema_hash NOT GLOB '*[^0-9a-f]*'
        ),
    row_count INTEGER NOT NULL
        CHECK (row_count >= 0),
    byte_size INTEGER NOT NULL
        CHECK (byte_size >= 0),
    reproduction_fingerprint TEXT NOT NULL
        CHECK (
            length(reproduction_fingerprint) = 64
            AND reproduction_fingerprint NOT GLOB '*[^0-9a-f]*'
        ),
    manifest_json TEXT NOT NULL
        CHECK (
            json_valid(manifest_json)
            AND json_type(manifest_json) = 'object'
        ),
    is_pinned INTEGER NOT NULL DEFAULT 0
        CHECK (is_pinned IN (0, 1)),
    pinned_at_epoch_us INTEGER
        CHECK (
            pinned_at_epoch_us IS NULL
            OR pinned_at_epoch_us >= created_at_epoch_us
        ),
    created_at_epoch_us INTEGER NOT NULL
        CHECK (created_at_epoch_us >= 0),
    revision INTEGER NOT NULL DEFAULT 0
        CHECK (revision >= 0),
    UNIQUE (experiment_id, artifact_id),
    UNIQUE (relative_path),
    CHECK (
        (
            candidate_id IS NULL
            AND fold_id IS NULL
            AND attempt_id IS NULL
        )
        OR (
            candidate_id IS NOT NULL
            AND fold_id IS NULL
            AND attempt_id IS NULL
        )
        OR (
            candidate_id IS NOT NULL
            AND fold_id IS NOT NULL
            AND attempt_id IS NULL
        )
        OR (
            candidate_id IS NOT NULL
            AND fold_id IS NOT NULL
            AND attempt_id IS NOT NULL
        )
    ),
    CHECK (
        (is_pinned = 0 AND pinned_at_epoch_us IS NULL)
        OR (is_pinned = 1 AND pinned_at_epoch_us IS NOT NULL)
    ),
    FOREIGN KEY (experiment_id)
        REFERENCES experiment(experiment_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, candidate_id)
        REFERENCES experiment_candidate(experiment_id, candidate_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, candidate_id, fold_id)
        REFERENCES experiment_fold(experiment_id, candidate_id, fold_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, candidate_id, fold_id, attempt_id)
        REFERENCES experiment_attempt(
            experiment_id,
            candidate_id,
            fold_id,
            attempt_id
        ) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_research_artifact_lineage
ON research_artifact(
    experiment_id,
    candidate_id,
    fold_id,
    attempt_id,
    artifact_kind
);

CREATE TABLE gate_evaluation (
    evaluation_id TEXT PRIMARY KEY
        CHECK (
            evaluation_id = trim(evaluation_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND evaluation_id <> ''
        ),
    experiment_id TEXT NOT NULL,
    candidate_id TEXT,
    fold_id TEXT,
    attempt_id TEXT,
    rule_id TEXT NOT NULL
        CHECK (
            rule_id = trim(rule_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND rule_id <> ''
        ),
    policy_version TEXT NOT NULL
        CHECK (
            policy_version = trim(policy_version, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND policy_version <> ''
        ),
    layer TEXT NOT NULL
        CHECK (layer IN ('hard', 'evidence')),
    outcome TEXT NOT NULL CHECK (outcome IN (
        'pass',
        'fail',
        'warn',
        'not_evaluated'
    )),
    observed_json TEXT NOT NULL
        CHECK (json_valid(observed_json)),
    policy_json TEXT NOT NULL
        CHECK (json_valid(policy_json)),
    artifact_id TEXT,
    payload_hash TEXT NOT NULL
        CHECK (
            length(payload_hash) = 64
            AND payload_hash NOT GLOB '*[^0-9a-f]*'
        ),
    evaluated_at_epoch_us INTEGER NOT NULL
        CHECK (evaluated_at_epoch_us >= 0),
    CHECK (
        (
            candidate_id IS NULL
            AND fold_id IS NULL
            AND attempt_id IS NULL
        )
        OR (
            candidate_id IS NOT NULL
            AND fold_id IS NULL
            AND attempt_id IS NULL
        )
        OR (
            candidate_id IS NOT NULL
            AND fold_id IS NOT NULL
            AND attempt_id IS NULL
        )
        OR (
            candidate_id IS NOT NULL
            AND fold_id IS NOT NULL
            AND attempt_id IS NOT NULL
        )
    ),
    FOREIGN KEY (experiment_id)
        REFERENCES experiment(experiment_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, candidate_id)
        REFERENCES experiment_candidate(experiment_id, candidate_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, candidate_id, fold_id)
        REFERENCES experiment_fold(experiment_id, candidate_id, fold_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, candidate_id, fold_id, attempt_id)
        REFERENCES experiment_attempt(
            experiment_id,
            candidate_id,
            fold_id,
            attempt_id
        ) ON DELETE RESTRICT,
    FOREIGN KEY (experiment_id, artifact_id)
        REFERENCES research_artifact(experiment_id, artifact_id)
        ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_gate_evaluation_review
ON gate_evaluation(
    experiment_id,
    layer,
    rule_id,
    evaluated_at_epoch_us
);

CREATE TABLE holdout_claim (
    claim_id TEXT PRIMARY KEY
        CHECK (
            claim_id = trim(claim_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND claim_id <> ''
        ),
    research_cycle_id TEXT NOT NULL,
    research_cycle_hash TEXT NOT NULL
        CHECK (
            length(research_cycle_hash) = 64
            AND research_cycle_hash NOT GLOB '*[^0-9a-f]*'
        ),
    experiment_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    fold_id TEXT NOT NULL,
    fold_role TEXT NOT NULL DEFAULT 'holdout'
        CHECK (fold_role = 'holdout'),
    resolved_spec_hash TEXT NOT NULL
        CHECK (
            length(resolved_spec_hash) = 64
            AND resolved_spec_hash NOT GLOB '*[^0-9a-f]*'
        ),
    parameters_hash TEXT NOT NULL
        CHECK (
            length(parameters_hash) = 64
            AND parameters_hash NOT GLOB '*[^0-9a-f]*'
        ),
    snapshot_id TEXT NOT NULL
        CHECK (
            snapshot_id = trim(snapshot_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND snapshot_id <> ''
        ),
    window_start TEXT NOT NULL
        CHECK (
            length(window_start) = 10
            AND window_start GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND date(window_start) IS NOT NULL
            AND date(window_start) = window_start
        ),
    window_end TEXT NOT NULL
        CHECK (
            length(window_end) = 10
            AND window_end GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND date(window_end) IS NOT NULL
            AND date(window_end) = window_end
        ),
    reproduction_fingerprint TEXT NOT NULL
        CHECK (
            length(reproduction_fingerprint) = 64
            AND reproduction_fingerprint NOT GLOB '*[^0-9a-f]*'
        ),
    logical_run_id TEXT NOT NULL
        CHECK (
            logical_run_id = trim(logical_run_id, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND logical_run_id <> ''
        ),
    operator_confirmation TEXT NOT NULL
        CHECK (
            operator_confirmation = trim(operator_confirmation, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
            AND operator_confirmation <> ''
        ),
    selection_reason_json TEXT NOT NULL
        CHECK (
            json_valid(selection_reason_json)
            AND json_type(selection_reason_json) = 'object'
        ),
    claim_payload_hash TEXT NOT NULL
        CHECK (
            length(claim_payload_hash) = 64
            AND claim_payload_hash NOT GLOB '*[^0-9a-f]*'
        ),
    claimed_at_epoch_us INTEGER NOT NULL
        CHECK (claimed_at_epoch_us >= 0),
    UNIQUE (research_cycle_id),
    UNIQUE (research_cycle_hash),
    UNIQUE (experiment_id),
    UNIQUE (logical_run_id),
    UNIQUE (experiment_id, candidate_id, fold_id),
    CHECK (window_start <= window_end),
    FOREIGN KEY (
        experiment_id,
        research_cycle_id,
        research_cycle_hash
    ) REFERENCES experiment(
        experiment_id,
        research_cycle_id,
        research_cycle_hash
    ) ON DELETE RESTRICT,
    FOREIGN KEY (
        experiment_id,
        candidate_id,
        fold_id,
        fold_role
    ) REFERENCES experiment_fold(
        experiment_id,
        candidate_id,
        fold_id,
        fold_role
    ) ON DELETE RESTRICT
) STRICT;

CREATE INDEX ix_holdout_claim_candidate
ON holdout_claim(experiment_id, candidate_id, fold_id);

CREATE TABLE experiment_scheduler_slot (
    slot_id TEXT PRIMARY KEY
        CHECK (slot_id = 'global'),
    experiment_id TEXT,
    owner_token TEXT
        CHECK (
            owner_token IS NULL
            OR (
                owner_token = trim(owner_token, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))
                AND owner_token <> ''
            )
        ),
    lease_until_epoch_us INTEGER
        CHECK (
            lease_until_epoch_us IS NULL
            OR lease_until_epoch_us >= 0
        ),
    acquired_at_epoch_us INTEGER
        CHECK (
            acquired_at_epoch_us IS NULL
            OR acquired_at_epoch_us >= 0
        ),
    renewed_at_epoch_us INTEGER
        CHECK (
            renewed_at_epoch_us IS NULL
            OR renewed_at_epoch_us >= 0
        ),
    revision INTEGER NOT NULL DEFAULT 0
        CHECK (revision >= 0),
    CHECK (
        (
            experiment_id IS NULL
            AND owner_token IS NULL
            AND lease_until_epoch_us IS NULL
            AND acquired_at_epoch_us IS NULL
            AND renewed_at_epoch_us IS NULL
        )
        OR (
            experiment_id IS NOT NULL
            AND owner_token IS NOT NULL
            AND lease_until_epoch_us IS NOT NULL
            AND acquired_at_epoch_us IS NOT NULL
            AND renewed_at_epoch_us IS NOT NULL
            AND acquired_at_epoch_us <= renewed_at_epoch_us
            AND renewed_at_epoch_us < lease_until_epoch_us
        )
    ),
    FOREIGN KEY (experiment_id)
        REFERENCES experiment(experiment_id)
        ON DELETE RESTRICT
) STRICT;

INSERT INTO experiment_scheduler_slot(slot_id, revision)
VALUES ('global', 0);

-- Reject every conflicting INSERT before SQLite can apply REPLACE semantics.
-- This keeps evidence immutable even if a caller attempts INSERT OR REPLACE,
-- INSERT OR IGNORE, or an UPSERT against any identity/uniqueness boundary.
CREATE TRIGGER trg_experiment_reject_insert_conflict
BEFORE INSERT ON experiment
WHEN EXISTS (
    SELECT 1
    FROM experiment AS existing
    WHERE existing.experiment_id = NEW.experiment_id
       OR (
           NEW.queue_ordinal IS NOT NULL
           AND existing.queue_ordinal = NEW.queue_ordinal
       )
)
BEGIN
    SELECT RAISE(ABORT, 'experiment insert conflict');
END;

CREATE TRIGGER trg_experiment_candidate_reject_insert_conflict
BEFORE INSERT ON experiment_candidate
WHEN EXISTS (
    SELECT 1
    FROM experiment_candidate AS existing
    WHERE (
        existing.experiment_id = NEW.experiment_id
        AND existing.candidate_id = NEW.candidate_id
    )
       OR (
           existing.experiment_id = NEW.experiment_id
           AND existing.ordinal = NEW.ordinal
       )
       OR (
           existing.experiment_id = NEW.experiment_id
           AND existing.parameters_hash = NEW.parameters_hash
       )
       OR (
           NEW.is_baseline = 1
           AND existing.experiment_id = NEW.experiment_id
           AND existing.is_baseline = 1
       )
)
BEGIN
    SELECT RAISE(ABORT, 'experiment_candidate insert conflict');
END;

CREATE TRIGGER trg_experiment_fold_reject_insert_conflict
BEFORE INSERT ON experiment_fold
WHEN EXISTS (
    SELECT 1
    FROM experiment_fold AS existing
    WHERE (
        existing.experiment_id = NEW.experiment_id
        AND existing.candidate_id = NEW.candidate_id
        AND existing.fold_id = NEW.fold_id
    )
       OR (
           existing.experiment_id = NEW.experiment_id
           AND existing.candidate_id = NEW.candidate_id
           AND existing.ordinal = NEW.ordinal
       )
)
BEGIN
    SELECT RAISE(ABORT, 'experiment_fold insert conflict');
END;

CREATE TRIGGER trg_experiment_attempt_reject_insert_conflict
BEFORE INSERT ON experiment_attempt
WHEN EXISTS (
    SELECT 1
    FROM experiment_attempt AS existing
    WHERE existing.attempt_id = NEW.attempt_id
       OR (
           existing.experiment_id = NEW.experiment_id
           AND existing.candidate_id = NEW.candidate_id
           AND existing.fold_id = NEW.fold_id
           AND existing.ordinal = NEW.ordinal
       )
       OR (
           NEW.status IN ('queued', 'running')
           AND existing.experiment_id = NEW.experiment_id
           AND existing.candidate_id = NEW.candidate_id
           AND existing.fold_id = NEW.fold_id
           AND existing.status IN ('queued', 'running')
       )
       OR (
           NEW.backtest_run_id IS NOT NULL
           AND existing.backtest_run_id = NEW.backtest_run_id
       )
)
BEGIN
    SELECT RAISE(ABORT, 'experiment_attempt insert conflict');
END;

CREATE TRIGGER trg_experiment_status_event_reject_insert_conflict
BEFORE INSERT ON experiment_status_event
WHEN EXISTS (
    SELECT 1
    FROM experiment_status_event AS existing
    WHERE existing.event_id = NEW.event_id
       OR (
           NEW.subject_type = 'experiment'
           AND existing.subject_type = 'experiment'
           AND existing.experiment_id = NEW.experiment_id
           AND existing.subject_revision = NEW.subject_revision
       )
       OR (
           NEW.subject_type = 'fold'
           AND existing.subject_type = 'fold'
           AND existing.experiment_id = NEW.experiment_id
           AND existing.candidate_id = NEW.candidate_id
           AND existing.fold_id = NEW.fold_id
           AND existing.subject_revision = NEW.subject_revision
       )
       OR (
           NEW.subject_type = 'attempt'
           AND existing.subject_type = 'attempt'
           AND existing.experiment_id = NEW.experiment_id
           AND existing.candidate_id = NEW.candidate_id
           AND existing.fold_id = NEW.fold_id
           AND existing.attempt_id = NEW.attempt_id
           AND existing.subject_revision = NEW.subject_revision
       )
)
BEGIN
    SELECT RAISE(ABORT, 'experiment_status_event insert conflict');
END;

CREATE TRIGGER trg_research_artifact_reject_insert_conflict
BEFORE INSERT ON research_artifact
WHEN EXISTS (
    SELECT 1
    FROM research_artifact AS existing
    WHERE existing.artifact_id = NEW.artifact_id
       OR existing.relative_path = NEW.relative_path
)
BEGIN
    SELECT RAISE(ABORT, 'research_artifact insert conflict');
END;

CREATE TRIGGER trg_gate_evaluation_reject_insert_conflict
BEFORE INSERT ON gate_evaluation
WHEN EXISTS (
    SELECT 1
    FROM gate_evaluation AS existing
    WHERE existing.evaluation_id = NEW.evaluation_id
)
BEGIN
    SELECT RAISE(ABORT, 'gate_evaluation insert conflict');
END;

CREATE TRIGGER trg_holdout_claim_reject_insert_conflict
BEFORE INSERT ON holdout_claim
WHEN EXISTS (
    SELECT 1
    FROM holdout_claim AS existing
    WHERE existing.claim_id = NEW.claim_id
       OR existing.research_cycle_id = NEW.research_cycle_id
       OR existing.research_cycle_hash = NEW.research_cycle_hash
       OR existing.experiment_id = NEW.experiment_id
       OR existing.logical_run_id = NEW.logical_run_id
       OR (
           existing.experiment_id = NEW.experiment_id
           AND existing.candidate_id = NEW.candidate_id
           AND existing.fold_id = NEW.fold_id
       )
)
BEGIN
    SELECT RAISE(ABORT, 'holdout_claim insert conflict');
END;

CREATE TRIGGER trg_experiment_scheduler_slot_reject_insert_conflict
BEFORE INSERT ON experiment_scheduler_slot
WHEN EXISTS (
    SELECT 1
    FROM experiment_scheduler_slot AS existing
    WHERE existing.slot_id = NEW.slot_id
)
BEGIN
    SELECT RAISE(ABORT, 'experiment_scheduler_slot insert conflict');
END;

-- Append-only control-plane facts.
CREATE TRIGGER trg_experiment_candidate_no_update
BEFORE UPDATE ON experiment_candidate
BEGIN
    SELECT RAISE(ABORT, 'experiment_candidate is append-only');
END;

CREATE TRIGGER trg_experiment_candidate_no_delete
BEFORE DELETE ON experiment_candidate
BEGIN
    SELECT RAISE(ABORT, 'experiment_candidate is append-only');
END;

CREATE TRIGGER trg_experiment_status_event_no_update
BEFORE UPDATE ON experiment_status_event
BEGIN
    SELECT RAISE(ABORT, 'experiment_status_event is append-only');
END;

CREATE TRIGGER trg_experiment_status_event_no_delete
BEFORE DELETE ON experiment_status_event
BEGIN
    SELECT RAISE(ABORT, 'experiment_status_event is append-only');
END;

CREATE TRIGGER trg_gate_evaluation_no_update
BEFORE UPDATE ON gate_evaluation
BEGIN
    SELECT RAISE(ABORT, 'gate_evaluation is append-only');
END;

CREATE TRIGGER trg_gate_evaluation_no_delete
BEFORE DELETE ON gate_evaluation
BEGIN
    SELECT RAISE(ABORT, 'gate_evaluation is append-only');
END;

CREATE TRIGGER trg_holdout_claim_no_update
BEFORE UPDATE ON holdout_claim
BEGIN
    SELECT RAISE(ABORT, 'holdout_claim is append-only');
END;

CREATE TRIGGER trg_holdout_claim_no_delete
BEFORE DELETE ON holdout_claim
BEGIN
    SELECT RAISE(ABORT, 'holdout_claim is append-only');
END;

-- Mutable projections must preserve immutable payload and advance revision by one.
CREATE TRIGGER trg_experiment_guard_update
BEFORE UPDATE ON experiment
WHEN
    NEW.experiment_id IS NOT OLD.experiment_id
    OR NEW.research_cycle_id IS NOT OLD.research_cycle_id
    OR NEW.research_cycle_hash IS NOT OLD.research_cycle_hash
    OR NEW.strategy_version IS NOT OLD.strategy_version
    OR NEW.strategy_spec_hash IS NOT OLD.strategy_spec_hash
    OR NEW.snapshot_id IS NOT OLD.snapshot_id
    OR NEW.launch_spec_schema_version IS NOT OLD.launch_spec_schema_version
    OR NEW.launch_spec_json IS NOT OLD.launch_spec_json
    OR NEW.launch_spec_hash IS NOT OLD.launch_spec_hash
    OR NEW.created_at_epoch_us IS NOT OLD.created_at_epoch_us
    OR NEW.updated_at_epoch_us < OLD.updated_at_epoch_us
    OR NEW.revision <> OLD.revision + 1
    OR NOT (
        NEW.queue_ordinal IS OLD.queue_ordinal
        OR (
            OLD.queue_ordinal IS NULL
            AND NEW.queue_ordinal IS NOT NULL
        )
    )
BEGIN
    SELECT RAISE(ABORT, 'invalid experiment projection update');
END;

CREATE TRIGGER trg_experiment_no_delete
BEFORE DELETE ON experiment
BEGIN
    SELECT RAISE(ABORT, 'experiment cannot be deleted');
END;

CREATE TRIGGER trg_experiment_fold_guard_update
BEFORE UPDATE ON experiment_fold
WHEN
    NEW.experiment_id IS NOT OLD.experiment_id
    OR NEW.candidate_id IS NOT OLD.candidate_id
    OR NEW.fold_id IS NOT OLD.fold_id
    OR NEW.ordinal IS NOT OLD.ordinal
    OR NEW.fold_role IS NOT OLD.fold_role
    OR NEW.train_start IS NOT OLD.train_start
    OR NEW.train_end IS NOT OLD.train_end
    OR NEW.test_start IS NOT OLD.test_start
    OR NEW.test_end IS NOT OLD.test_end
    OR NEW.purge_sessions IS NOT OLD.purge_sessions
    OR NEW.embargo_sessions IS NOT OLD.embargo_sessions
    OR NEW.fold_spec_json IS NOT OLD.fold_spec_json
    OR NEW.fold_spec_hash IS NOT OLD.fold_spec_hash
    OR NEW.created_at_epoch_us IS NOT OLD.created_at_epoch_us
    OR NEW.updated_at_epoch_us < OLD.updated_at_epoch_us
    OR NEW.revision <> OLD.revision + 1
BEGIN
    SELECT RAISE(ABORT, 'invalid experiment_fold projection update');
END;

CREATE TRIGGER trg_experiment_fold_no_delete
BEFORE DELETE ON experiment_fold
BEGIN
    SELECT RAISE(ABORT, 'experiment_fold cannot be deleted');
END;

CREATE TRIGGER trg_experiment_attempt_guard_update
BEFORE UPDATE ON experiment_attempt
WHEN
    NEW.attempt_id IS NOT OLD.attempt_id
    OR NEW.experiment_id IS NOT OLD.experiment_id
    OR NEW.candidate_id IS NOT OLD.candidate_id
    OR NEW.fold_id IS NOT OLD.fold_id
    OR NEW.ordinal IS NOT OLD.ordinal
    OR NEW.parent_attempt_id IS NOT OLD.parent_attempt_id
    OR NEW.resume_from_run_id IS NOT OLD.resume_from_run_id
    OR NEW.reproduction_fingerprint IS NOT OLD.reproduction_fingerprint
    OR NEW.created_at_epoch_us IS NOT OLD.created_at_epoch_us
    OR NEW.updated_at_epoch_us < OLD.updated_at_epoch_us
    OR NEW.revision <> OLD.revision + 1
    OR NOT (
        NEW.backtest_run_id IS OLD.backtest_run_id
        OR (
            OLD.backtest_run_id IS NULL
            AND NEW.backtest_run_id IS NOT NULL
        )
    )
BEGIN
    SELECT RAISE(ABORT, 'invalid experiment_attempt projection update');
END;

CREATE TRIGGER trg_experiment_attempt_no_delete
BEFORE DELETE ON experiment_attempt
BEGIN
    SELECT RAISE(ABORT, 'experiment_attempt cannot be deleted');
END;

CREATE TRIGGER trg_research_artifact_guard_update
BEFORE UPDATE ON research_artifact
WHEN NOT (
    OLD.is_pinned = 0
    AND OLD.pinned_at_epoch_us IS NULL
    AND NEW.is_pinned = 1
    AND NEW.pinned_at_epoch_us IS NOT NULL
    AND NEW.revision = OLD.revision + 1
    AND NEW.artifact_id IS OLD.artifact_id
    AND NEW.experiment_id IS OLD.experiment_id
    AND NEW.candidate_id IS OLD.candidate_id
    AND NEW.fold_id IS OLD.fold_id
    AND NEW.attempt_id IS OLD.attempt_id
    AND NEW.artifact_kind IS OLD.artifact_kind
    AND NEW.relative_path IS OLD.relative_path
    AND NEW.content_hash IS OLD.content_hash
    AND NEW.schema_hash IS OLD.schema_hash
    AND NEW.row_count IS OLD.row_count
    AND NEW.byte_size IS OLD.byte_size
    AND NEW.reproduction_fingerprint IS OLD.reproduction_fingerprint
    AND NEW.manifest_json IS OLD.manifest_json
    AND NEW.created_at_epoch_us IS OLD.created_at_epoch_us
)
BEGIN
    SELECT RAISE(ABORT, 'research_artifact only supports one-way pinning');
END;

CREATE TRIGGER trg_research_artifact_no_delete
BEFORE DELETE ON research_artifact
BEGIN
    SELECT RAISE(ABORT, 'research_artifact cannot be deleted');
END;

CREATE TRIGGER trg_experiment_scheduler_slot_guard_update
BEFORE UPDATE ON experiment_scheduler_slot
WHEN
    NEW.slot_id IS NOT OLD.slot_id
    OR NEW.revision <> OLD.revision + 1
BEGIN
    SELECT RAISE(ABORT, 'invalid scheduler slot CAS update');
END;

CREATE TRIGGER trg_experiment_scheduler_slot_no_delete
BEFORE DELETE ON experiment_scheduler_slot
BEGIN
    SELECT RAISE(ABORT, 'experiment_scheduler_slot cannot be deleted');
END;

-- Written last by the migration coordinator, still inside its transaction.
PRAGMA application_id = 1146376755;
PRAGMA user_version = 1;

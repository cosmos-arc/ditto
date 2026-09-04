# Experiment Detail implementation feedback

- React route: `/research/experiments/$id`
- Contract verification: 2026-08-29
- Style anchor: the reviewed Strategy Detail Object Hub supplies the compact meta/tabs/main/bottom shell; no experiment BFF or new page framework was added.
- Revision truth: status, stage, revision, strategy version, snapshot, protocol, counts, hashes, and timestamps come from the experiment detail response.
- Resource fan-out: candidates, gates, comparison, artifacts, aggregate selection evidence, and candidate drill-down evidence retain independent typed failure states.
- Selection safety: promotion stays locked until aggregate evidence is published and the comparison revision matches; the baseline is never promotable.
- Holdout safety: the one-time holdout is bound to the returned selection receipt and fails closed after a persisted claim.
- Recovery: pause/resume/cancel/fold retry commands use the latest revision and idempotency keys; unknown outcomes are retried with the same key.
- Missing evidence: unpublished gates, artifacts, selection evidence, and candidate evidence are labeled as missing or unpublished, never represented as zero.

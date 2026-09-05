# Integrated Product Beta operations runbook

> Scope: A-share ETFs, daily cadence, one local operator, paper execution only.
> This runbook does not authorize real orders, a real broker, production data writes,
> destructive restore-overwrite, or Coding Plan use in a deployed application.

## 1. What constitutes a healthy Beta

The UI is the operator surface. It must show readiness, blocked/stale/error reasons,
as-of time, source snapshot, data quality, recovery result, and the next available
action. Normal operation must not require reading a database or terminal. Agent
output is advisory evidence with citations; it is never a trading or publication
authority.

The certified acceptance lane is sufficient for deterministic release evidence, but
it is not a fresh provider lane. Tushare/FRED are considered live only after their
local credential preflight, entitlement evidence, snapshot build, and certification
pass. Never label fixture or restored data as fresh.

## 2. Start and stop

Choose one explicit local data root. It must not be the repository root, a home
directory, or a production/real-data root.

```bash
cd /Users/chevy/Desktop/code/ditto
DITTO_STATE_ROOT=/absolute/path/ditto-beta-state pixi run -e dev dev
```

The root supervisor starts both processes on loopback, writes a validated
`ditto-runtime-config.json`, and waits for readiness. Stop both with `Ctrl-C`; do not
delete the state root as a substitute for shutdown
or rollback. Feature rollback is to disable the five Agent flags listed in
[the R5 runbook](r5-agent-runbook.md#feature-flags-and-rollback) and restart the
backend. Core research and paper trading remain usable without Agent model calls.

## 3. Data update and acceptance

For a deterministic certified-data check that performs no provider call:

```bash
pixi run -e dev python -m ditto_apps.scripts.r2_data_acceptance --mode fixture
```

For a fresh provider update, first follow
[the R2 data-product runbook](r2-data-product-runbook.md). Provider credentials stay
in the local keyring/configuration store and must never appear in a report or shell
history. Missing credential, entitlement, license, publication cutoff, knowledge
date, or source snapshot is blocked—not empty success and not a mock fallback.

Current integrated research acceptance with a certified snapshot:

```bash
pixi run -e dev python -m ditto_apps.scripts.r5_agent_release_preflight \
  --repo-root . \
  --output docs/evidence/r5/release/release-preflight.json

pixi run -e dev python -m ditto_apps.scripts.r3_research_acceptance \
  --fixture \
  --output docs/evidence/product-beta/20260830/r3-certified-research-flow.json \
  --manifest docs/evidence/product-beta/20260830/r3-certified-research-flow.manifest.json
```

The five-day trading soak is simulated paper execution over five consecutive trading
dates. It creates no real order and contacts no broker:

```bash
pixi run -e dev pytest \
  apps/backend/tests/e2e/test_r1_daily_manual_trading.py::test_certified_etf_paper_flow_completes_five_consecutive_trading_days \
  -q --no-cov -n 0
```

## 4. Backup, restore, and interruption recovery

Backups are non-overwriting and restores go to a new explicit target. Stop writers,
retain the source and backup, verify SQLite integrity, row counts, domain identity,
artifact hashes, and query the restored projection before any cutover.

Deterministic operator exercises:

```bash
pixi run -e dev pytest \
  apps/backend/tests/e2e/test_r1_daily_manual_trading.py::test_online_backup_restore_preserves_the_queryable_r1_decision \
  apps/backend/tests/integration/test_agent_database_lifecycle.py::test_agent_bundle_backup_and_restore_preserve_readable_projection \
  apps/backend/tests/integration/research/test_r3_backup_restore.py::test_r3_backup_restore_preserves_governance_holdout_and_pinned_packet \
  -q --no-cov -n 0

pixi run -e dev pytest \
  apps/backend/tests/e2e/test_r1_daily_manual_trading.py::test_rerun_recovers_a_durable_package_after_finalize_interruption \
  apps/backend/tests/integration/test_agent_run_execution.py::test_process_interruption_before_commit_leaves_run_queued_and_retryable \
  apps/backend/tests/integration/test_agent_run_execution.py::test_episode_write_failure_rolls_back_terminal_run_and_events \
  apps/backend/tests/integration/test_agent_run_execution.py::test_projection_write_failure_leaves_run_queued_and_retryable \
  apps/backend/tests/integration/test_agent_run_execution.py::test_concurrent_execute_requests_invoke_model_once_per_run \
  -q --no-cov -n 0
```

An Agent interruption before the atomic execution commit leaves the original queued
run retryable with no partial terminal event or Episode. Episode or presentation
publication failures also keep the run queued and retryable, while concurrent
execute requests in this single-process Beta invoke the model only once per run. A
provider failure seals a failed run and a complete audit Episode; it never falls
back to an ungrounded answer. An EOD rerun reuses or recovers durable identities
rather than duplicating orders or fills.

## 5. Failure response

| Operator-visible state | Response |
|---|---|
| data/provider unavailable | Keep the page blocked/stale, preserve its last certified snapshot identity, fix credentials/entitlement/provider, then recertify. |
| Agent model unavailable | Disable model calls, retain events/Episode, and continue core workflows; never synthesize an answer. |
| frontend disconnected | Keep the last known state visibly stale, reconnect the query/SSE stream, and resume after the last persisted event ID without replaying a side effect. |
| paper EOD interruption | Restart against the same run/package identity; verify recovery before continuing. |
| restore verification fails | Preserve source and failed evidence, select a new restore target, diagnose drift, and do not cut over. |
| any real broker/order prompt | Stop. This Beta has no authorization or route for that action. |

## 6. Release gates

From `ditto`:

```bash
pixi run -e dev pytest -m pit
pixi run -e dev arch-check
pixi run -e dev ci
git diff --check
```

The root `ci` task owns the Web, contract, system, Harness, security, and artifact
gates. Do not run a second repository-level Bun DAG; Bun scripts under `apps/web`
are leaf tasks invoked by Pixi.

Close the release only when the current P0–P5 ledger links the exact evidence files,
isolated roots/modes, visual viewport results, recovery drills, and artifact hashes.
Historical green reports do not override a current failing gate.

# Workstation runtime reset inventory

> Work package: FND-03
> Captured: 2026-08-31T09:16:15+08:00
> State: read-only inventory; no reset is authorized or performed

This inventory freezes the paths that a future fresh-bootstrap reset may inspect.
It is not a deletion list. A reset must generate a new dry-run hash from current
state and obtain explicit user approval for that exact hash before changing data.

## Configured roots

| Environment | Exact absolute root | Observed state |
|---|---|---|
| development | `/Users/chevy/Desktop/code/ditto/data` | present, 680 KiB |
| testing | `/Users/chevy/Desktop/code/ditto/.tmp/ditto` | present, 648 KiB |
| production | `/data/ditto` | absent on this host |

`DITTO_DATA_ROOT`, `SQLITE_PATH`, and `DUCKDB_PATH` may override these values.
An unresolved override is never a valid reset target.

## Runtime path templates

All templates below are relative to one already resolved and validated data root.

| Owner | Relative path | Contents | Reset classification |
|---|---|---|---|
| data/execution/strategy | `metadata/metadata.sqlite` plus SQLite `-wal`/`-shm` | metadata, ingestion/DQ, strategy, execution, Paper and account projections | `NEEDS_EXPLICIT_APPROVAL` |
| data | `db/ditto.duckdb` | local analytical SQL database | `NEEDS_EXPLICIT_APPROVAL` |
| data | `market/index/constituent.db` plus SQLite sidecars | index constituent PIT store | `NEEDS_EXPLICIT_APPROVAL` |
| data | `market/**`, `capital/**`, `fundamental/**`, `macro/**` | Parquet and domain storage payloads | `NEEDS_EXPLICIT_APPROVAL` |
| data | `freezes/**`, `locks/**` | frozen manifests and runtime locks | `NEEDS_EXPLICIT_APPROVAL`; services must be stopped first |
| features | `features/**`, `factors/**` | technical/factor materializations | `NEEDS_EXPLICIT_APPROVAL` |
| features | `derived/artifacts/**`, `derived/publication_safety/**` | immutable derived artifacts and publication evidence | `NEEDS_EXPLICIT_APPROVAL` |
| analysis | `research/research.sqlite` | experiment/holdout/trial ledger | `NEEDS_EXPLICIT_APPROVAL` |
| analysis | `research/artifacts/**` | indexed immutable research artifacts | `BACKUP_FIRST` |
| agent | `agent/agent.sqlite` | Agent runs, events, approvals, audit and episodes | `BACKUP_FIRST` |
| agent | `agent/agent-presentation.sqlite3` | Agent presentation read model | `NEEDS_EXPLICIT_APPROVAL` |
| agent | `agent-shadow/decision-opinion.sqlite` | Agent shadow opinions | `NEEDS_EXPLICIT_APPROVAL` |
| apps/platform | `logs/**`, `backups/**`, `temp/**` | operator logs, backups and temporary runtime data | backups are `DO_NOT_DELETE`; logs/temp need explicit selection |
| harness | `/Users/chevy/Desktop/code/ditto/.cache/ditto-agent-harness` | local harness cache, currently absent | cache-only; outside data reset by default |

The application `DataCache` and PIT query caches are in-memory and disappear with
the process. They have no filesystem reset target.

## Existing development files

| Exact path | Bytes | Last modified |
|---|---:|---|
| `/Users/chevy/Desktop/code/ditto/data/metadata/metadata.sqlite` | 618496 | 2026-08-11T16:34:49+0800 |
| `/Users/chevy/Desktop/code/ditto/data/metadata/metadata.sqlite-shm` | 32768 | 2026-08-30T20:03:05+0800 |
| `/Users/chevy/Desktop/code/ditto/data/metadata/metadata.sqlite-wal` | 0 | 2026-08-30T19:58:14+0800 |
| `/Users/chevy/Desktop/code/ditto/data/market/index/constituent.db` | 12288 | 2026-08-11T16:34:49+0800 |
| `/Users/chevy/Desktop/code/ditto/data/market/index/constituent.db-shm` | 32768 | 2026-08-30T19:58:14+0800 |
| `/Users/chevy/Desktop/code/ditto/data/market/index/constituent.db-wal` | 0 | 2026-08-30T19:58:14+0800 |

The testing root currently contains the same metadata database and one constituent
database. It remains outside any development-data reset unless selected explicitly.

## Permanent exclusions

The following are never inferred as reset targets:

- `/Users/chevy/Desktop/code/ditto`, its `.git` directory, or either repository;
- a home directory, `/`, `/Users`, `/data`, a glob, `~`, or an unresolved variable;
- source strategy/factor definitions, configuration, credentials, attachments, or
  unknown user files;
- `/Users/chevy/Desktop/code/ditto/artifacts/acceptance/**` and
  `/Users/chevy/Desktop/code/ditto/docs/evidence/**` without a separate evidence
  retention decision;
- any `backups/**` subtree.

## Reset precondition

Before a reset, stop API, Jobs, Paper sessions, Agent runs, and SQLite users; resolve
every target strictly beneath one approved root; show type, size, modification time
and recoverability; create/verify backups; and obtain approval for the exact dry-run
manifest hash. No current work package grants that approval.

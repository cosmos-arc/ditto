# R1 · G1 Evidence Package

> 本文件是验收模板，不是通过证明。只有所有必填项都有可复核证据且结果为 PASS，才可将 G1 判定为通过。
>
> Task 6 fresh schema 已于 2026-07-16 获批；“多笔部分成交”和“追加式更正”仍必须由 raw/effective/adjustment 端到端证据证明，不得用单笔成交测试、skip、xfail 或人工覆盖替代。pytest 的 real-data 用例若 skip，也只能记为 `BLOCKED_EXTERNAL / FAIL`。

## 1. Run identity

| Field | Value |
|---|---|
| Evidence timestamp (Asia/Shanghai) | `<YYYY-MM-DD HH:MM:SS>` |
| Backend commit SHA / dirty state | `<sha>` / `<clean|dirty>` |
| Frontend commit SHA / dirty state | `<sha>` / `<clean|dirty>` |
| Operator | `<name>` |
| Signal date (D) | `<YYYY-MM-DD>` |
| Intended trade date (D+1 trading day) | `<YYYY-MM-DD>` |
| Seed strategy / published version | `<strategy_id>` / `<version>` |
| Account / sleeve (redacted) | `<non-sensitive alias>` |
| Provider | `<provider name; never token>` |

## 2. Deterministic E2E

Command:

```bash
pixi run -e dev pytest --no-cov packages/apps/tests/e2e/test_r1_daily_manual_trading.py -q
```

| Scenario | Expected evidence | Artifact / checksum | Result |
|---|---|---|---|
| Idempotent seed bootstrap | Same active published version | `<id/version>` | `<PASS/FAIL>` |
| Account baseline | Account, sleeve, cash, NAV, positions atomically visible | `<baseline_id>` | `<PASS/FAIL>` |
| Trading-day semantics | D data produces D+1 advice | `<D -> D+1>` | `<PASS/FAIL>` |
| Trade day | Persisted package and intents with quantities | `<artifact_id/checksum>` | `<PASS/FAIL>` |
| Zero-rebalance day | Persisted package with `no_rebalance=true` | `<artifact_id/checksum>` | `<PASS/FAIL>` |
| Two partial fills | Two immutable fill IDs for one intent | `<fill ids>` | `<PASS/FAIL>` |
| Append-only correction | Original + adjustment + replacement; effective view excludes original | `<adjustment/replacement ids>` | `<PASS/FAIL>` |
| Review | Effective fills, remaining quantity, deviation and PnL reconcile | `<decision checksum>` | `<PASS/FAIL>` |

Attach sanitized test output: `<path or CI URL>`

Task 6 两行只有在同一 intent 的多笔 immutable raw fills、append-only replace/void、effective read model，以及依赖 effective fills 的状态、偏差、PnL 和恢复演练全部一致时才能记为 PASS。

## 3. Rerun and recovery

| Exercise | Procedure / command | Required proof | Duration | Result |
|---|---|---|---|---|
| Same-input rerun | Repeat identical EOD request | No new intents; same artifact/checksum | `<seconds>` | `<PASS/FAIL>` |
| Different-input rerun | Change a business input | Explicit `RERUN_CONFLICT`; no silent overwrite | `<seconds>` | `<PASS/FAIL>` |
| Interrupted process | Stop after durable intermediate state, rerun | Resumes/no-ops without duplication | `<seconds>` | `<PASS/FAIL>` |
| SQLite backup | `ditto ops backup-sqlite --source ... --destination ...` while writes are quiesced | Atomic backup + `integrity_check=ok` + row counts | `<seconds>` | `<PASS/FAIL>` |
| SQLite restore | `ditto ops restore-sqlite --backup ... --destination ...` into a separate data root | Integrity/counts/checksums/decision match source | `<seconds>` | `<PASS/FAIL>` |

Source and restored database SHA-256 (database contents may not be committed): `<hashes>`

自动化恢复回归使用与第 2 节相同的 deterministic E2E 命令；正式 evidence 仍需记录操作者实际命令、开始/结束时间、独立恢复路径和脱敏输出。

## 4. Explicit real-data acceptance

The run must be explicitly enabled and use one designated date and seed. Provider credentials remain in the operator's secret store/environment and must never be copied here.

Designated exercise: `signal_date=2024-03-29`, `seed_stock_selection_rotation`（由 `strategy bootstrap-seeds` 创建并发布，不允许测试临时 custom spec）。

```bash
DITTO_RUN_REAL_DATA_ACCEPTANCE=1 \
  pixi run -e dev pytest --no-cov \
  packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py \
  -m e2e -q
```

| Evidence | Value | Result |
|---|---|---|
| Command with secret values redacted | `<command>` | `<PASS/FAIL/BLOCKED_EXTERNAL>` |
| Dataset snapshot IDs | `<ids>` | `<PASS/FAIL>` |
| Freshness / DQ facts | `<facts and reason codes>` | `<PASS/FAIL>` |
| Published strategy version | `<id/version>` | `<PASS/FAIL>` |
| Package artifact ID / checksum | `<id/checksum>` | `<PASS/FAIL>` |
| Daily Decision status / reason codes | `<status/codes>` | `<PASS/FAIL>` |
| Sanitized logs/artifacts | `<path outside secrets>` | `<PASS/FAIL>` |

If externally blocked, record provider response, observation time and retry owner. External blocking does **not** turn G1 into PASS.
命令输出中任一 live 用例为 `SKIPPED` 时，本节不得填写 PASS。

## 5. Frontend live acceptance

Runtime: `VITE_USE_MOCK=false`; backend and frontend bind only to loopback.

| Viewport / state | Required proof | Screenshot | Result |
|---|---|---|---|
| Desktop blocked | Reason codes + recovery entry; no executable advice | `<path>` | `<PASS/FAIL>` |
| Desktop review/conflict | Evidence, checksum, warnings/conflict and manual confirmation gate | `<path>` | `<PASS/FAIL>` |
| Desktop ready | Target/current/delta, quantity, reference price, reason and risk | `<path>` | `<PASS/FAIL>` |
| Desktop fill/review | Multiple fills, correction entry, effective fills, remaining quantity, deviation, PnL | `<path>` | `<PASS/FAIL>` |
| Mobile blocked/review/ready | No overlap, clipping or inaccessible horizontal content | `<paths>` | `<PASS/FAIL>` |
| Keyboard/focus | All controls reachable; focus visible; drawer/dialog focus returns | `<test/output>` | `<PASS/FAIL>` |

Commands:

```bash
cd /home/chevy/projects/ditto-app
bun run gen:api
bun run check
bun run visual:audit
```

## 6. Quality and security gates

| Gate | Command / inspection | Result |
|---|---|---|
| Backend full check | `pixi run -e dev check` | `<PASS/FAIL>` |
| Architecture gates | `pixi run -e dev arch-check` | `<PASS/FAIL>` |
| R1 deterministic E2E | command in section 2 | `<PASS/FAIL>` |
| Frontend full check | `bun run check` | `<PASS/FAIL>` |
| Loopback-only | Host entry points/tasks use `127.0.0.1`; any container-internal `0.0.0.0` is reachable only through a `127.0.0.1` published port; runtime host sockets inspected | `<PASS/FAIL>` |
| Secret scan | No provider token, account identifier or sensitive path in repository/log evidence | `<PASS/FAIL>` |

## 7. Final decision

- G1 result: `<PASS/FAIL>`
- Outstanding blockers: `<none or list>`
- Evidence reviewer: `<name>`
- Review timestamp: `<timestamp>`
- Maturity/benchmark update authorized: `<yes only when every row above passes>`

Do not promote `/api/v1/trade` or capability scores while any required row is FAIL, blank, or externally blocked.

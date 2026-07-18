# R2 Evidence Index

> 本目录是 R2 证据规则和索引，不是通过声明。只有机器输出、可追溯 commit、
> 脱敏 artifact 和 reviewer 事实可以作为 evidence；手写 `PASS`、fixture 代替 live、
> skip/xfail 或缺失字段都不能关闭 release Gate。

## 1. Evidence policy

- 不提交 provider token、API key、账户标识、受限 raw payload、SQLite 数据库或恢复副本。
- Fixture 报告只能证明确定性实现，不证明真实 provider entitlement、历史覆盖或 quota 性能。
- Live 报告只归档非敏感字段：检查时间、commit SHA、dataset/source ID、artifact URI、hash、行数、耗时、reason code 和 reviewer。
- `configuration_blocked`、`performance_blocked`、`acceptance_failed`、SKIPPED 和缺少 evidence 均不是 PASS。
- Certification、promotion、revoke 与 license review 必须引用 append-only runtime identity；README 不复制或重写其事实。

## 2. Machine report naming

正式报告存放在受控 artifact 目录或 CI，不要求提交大文件到 Git：

```text
r2/<YYYYMMDDTHHMMSSZ>/
  run-identity.json
  fixture-acceptance.json
  live-acceptance.json
  provider-access/*.json
  benchmarks/{stock_daily,index_daily,adj_factor,fund_adj}.json
  certification/<dataset>.json
  backup-restore.json
  consecutive-runs.json
  frontend-live/
```

Artifact URI 和 SHA-256 记录在 release review 中。若必须在本目录归档小型 JSON，
文件必须由命令直接生成，且在提交前完成 secret scan；禁止人工编辑结果字段。

## 3. Implementation evidence map

| DoD | Deterministic evidence | Required live evidence |
|---:|---|---|
| 1 | `test_r2_contracts_unit.py`，19 hard + 3 deferred contract freeze | commit SHA 与部署 contract snapshot |
| 2 | coverage/certification target tests | P0 raw coverage 从 2015 开始的 19-report artifacts |
| 3 | PIT-safe stock status、certified boundary tests | 2016 起 stock universe/status replay |
| 4 | schedule-aware gaps + exception validation tests | gap/exception report 和 reviewer identity |
| 5 | immutable certification store/command/query tests | 19 个独立 report ID 与 content hash |
| 6 | snapshot identity、ingestion saga compensation tests | provider snapshot、canonical URI、lineage traversal |
| 7 | checkpoint、resume、backup/restore、idempotency tests | 中断恢复和同区间连续两次运行 artifact |
| 8 | certification review/revoke/recertify tests | append-only revoke + recertification 演练 |
| 9 | API/CLI tests，生成 OpenAPI 类型，前端 MSW real-path tests | `VITE_USE_MOCK=false` 工作台与 backend live evidence |
| 10 | `DataReadinessQuery` 和 Daily Decision R2 preflight tests | promoted snapshot 下 ready/review/blocked 回归 |
| 11 | fixed seed factor input/lookback/replay/smoke tests | certified snapshot 上的机器报告 |
| 12 | contract scope、route/UI review，R2 feature tests | release reviewer 确认无 R3/R4 能力泄漏 |
| 13 | fixture preflight、performance、recoverability、idempotency tests | entitlement、四类 benchmark、真实 backup/restore、5 日连续运行 |

## 4. Reproducible commands

```bash
# deterministic report to stdout
pixi run -e dev python -m ditto_apps.scripts.r2_data_acceptance --mode fixture

# live report, explicit non-secret inputs and isolated recovery paths
pixi run -e dev python -m ditto_apps.scripts.r2_data_acceptance \
  --mode live \
  --evidence /absolute/path/r2-live-evidence.json \
  --sqlite-path /absolute/path/runtime.db \
  --payload-root /absolute/path/data-products \
  --backup-root /absolute/path/r2-backup-<timestamp> \
  --restore-root /absolute/path/r2-restore-<timestamp>
```

完整操作顺序、确认短语和故障处理见
[R2 数据产品运维手册](../../operations/r2-data-product-runbook.md)。

## 5. Current release review

本节只在 fresh verification 后更新。代码/fixture 门禁通过不自动关闭 live 门禁。

| Gate | Evidence | Current result |
|---|---|---|
| Backend focused/full quality | 2026-07-18 本地 fresh run：`pixi run -e dev check` 为 9041 passed / 1 xfailed；三包完整集合为 5383 passed / 43 skipped / 10 xfailed / 11 xpassed，coverage 89.79% | **DEVELOPMENT PASS**；skip/xfail 不作为 live evidence |
| Architecture/smell/pre-commit | 37 条 import contracts kept；architecture smell 0 issues；pre-commit 全部通过 | **DEVELOPMENT PASS** |
| Frontend codegen/check/build | OpenAPI codegen 无 diff；Biome/TypeScript 通过；167 files / 1942 tests；生产 build 通过 | **DEVELOPMENT PASS**；尚无 live UI artifact |
| Fixture acceptance | [`fixture-acceptance.json`](20260718T115126Z/fixture-acceptance.json)，SHA-256 `100157e100a37f6423f43d4a762c9b68d7632413820477f6ce436945e5451d3f`；另一次独立运行同样 `ready` | **PASS（仅确定性实现）**：19 contracts，36000s/120s/0.4s，restore 通过，second-run writes=0 |
| Live provider + entitlement + license | [`live-acceptance.json`](20260718T115126Z/live-acceptance.json)，SHA-256 `f9d0b32e0bc03b6f98efc889a680aab22d16e16e98a2c4f2bbd184172ea768d7`，进程退出码 2 | **BLOCKED**：`entitlement_unverified`；未提交真实 provider access/license evidence |
| Historical coverage + 19 reports | 未提供 artifact URI | **BLOCKED**：未执行真实历史 bootstrap/replay，未生成 19 个 live certification reports |
| Real performance + backup/restore + five-day run | 同一 live 报告；未提供 benchmark/recovery/consecutive-run artifact | **BLOCKED**：`performance_evidence_missing`、`recoverability_evidence_missing`、`idempotency_evidence_missing` |

归档 JSON 均由 acceptance runner 直接生成。2026-07-18 已检查敏感字段；报告不含
token、API key、credential value、受限 raw payload 或数据库副本。Fixture 的
license identity 是确定性合成证据，只验证实现，不代表 reviewer 已批准真实许可。

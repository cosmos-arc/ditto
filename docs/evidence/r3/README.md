# R3 Research / Governance Evidence Index

> 本目录只索引机器生成的验收事实，不是发布通过声明。Task 17 fixture
> 通过最多证明 **R3 ENGINEERING COMPLETE / G2 BLOCKED**；只有 Task 18 经单独
> 授权取得真实 provider、certified 数据、96 月覆盖、浏览器与恢复证据后，才可评估
> release acceptance。

## Evidence policy

- 不归档 token、API key、账户标识、受限 raw payload、SQLite 数据库、备份单元或
  restore data root。
- `deterministic_fixture` 必须固定
  `release_status=RELEASE_ACCEPTANCE_BLOCKED`、
  `r2_live_gate=NOT_EVALUATED` 和 `golden_lanes=[stock, etf]`。
- runner 必须实际执行 submit-review 与 publish/promotion 公共写路径；对应 E2E
  wrapper 断言 active pointer、candidate state 与 append-only event history 均未改变。
- 命令退出 `0` 表示本次确定性工程验收通过，不等于 live 或 release 通过。
- `manifest.json` 由 runner 生成；每个 entry 绑定 relative path、SHA-256、mode、
  generated time、source commit 与完整命令。禁止手工改写结果字段。

## Reproducible command

```bash
pixi run -e dev python -m ditto_apps.scripts.r3_research_acceptance \
  --fixture \
  --output artifacts/acceptance/r3-report.json
```

runner 顺序执行 backend check、stock primary golden、ETF proving golden、governance
recovery、hard-gate zero-write、literal 128 scheduler、隔离 backup/restore 与运行时
OpenAPI zero-diff。每项保留截断 stdout/stderr、return code 和 command transcript
SHA-256；OpenAPI 项额外绑定静态 snapshot hash。

前端 deterministic UI contract 由 `ditto-app` 独立生成到
`docs/review/r3-research-acceptance/deterministic/`。它使用 jsdom + MSW 的隔离 HTTP
fixture，不能充当真实浏览器或 live backend 证据。

## 2026-08-01 deterministic DoD reconciliation

这是 Task 19 在 Task 18 授权前可完成的确定性对账，不是最终 G2 matrix。严格按
“缺任一字段不得标 PASS”执行后，当前为 **10 DETERMINISTIC PASS / 11 PARTIAL /
2 LIVE BLOCKED**，总状态保持 **R3 ENGINEERING COMPLETE / G2 BLOCKED**。

### Evidence and command identities

| ID | Evidence file | SHA-256 | Source / evidence commit | Command |
|---|---|---|---|---|
| B | `artifacts/acceptance/r3-report.json` | `f005425c2428e0e9e01f746281ba2bd74b752089e3cdf202577576bf67c35f76` | `39e2b752` / `a135899c` | `pixi run -e dev python -m ditto_apps.scripts.r3_research_acceptance --fixture --output artifacts/acceptance/r3-report.json` |
| BM | `docs/evidence/r3/manifest.json` | `49192a6d2e25ce4186716dc7e3eb376d2d684d1f46eafeb02ac3230580f1ab30` | `a135899c` | 由 B runner 原子生成 |
| F | `ditto-app/docs/review/r3-research-acceptance/deterministic/report.json` | `2aae6a908f5993e11f0125c1ac4732326dc71312293725bed1a99053be7e7f40` | `7f4d277` / `6da94e1` | `bun run acceptance:r3-research` |
| FM | `ditto-app/docs/review/r3-research-acceptance/deterministic/manifest.json` | `2b84beac99f1f30b413021f16c01df42190012a26c5f6ec33f5ab52462a6a8ef` | `6da94e1` | 由 F runner 原子生成 |

表内 `B:*` 使用 B 报告中对应 command 的 transcript SHA；`F:ui` 使用 F 报告的
`03ce168caad4be795c6095f558e570438c6296d8abcd5a1996f3fa0542ece010`。所有 live
栏位均有意留空；不得用 B/F 补齐。

| # | Status | Evidence file | SHA-256 | Command | Backend commit | Frontend commit | Notes |
|---:|---|---|---|---|---|---|---|
| 1 | LIVE BLOCKED | — | — | Task 18 live R2 runner，未获授权 | — | — | `r2_live_gate=NOT_EVALUATED`。 |
| 2 | PARTIAL / LIVE BLOCKED | B、BM；live 缺失 | B、BM | `B:stock-golden`、`B:etf-golden`；Task 18 live runner 待执行 | `39e2b752`、`a135899c` | — | fixture 证明两 lane 结构闭环，不证明 certified/strategy-eligible live 数据。 |
| 3 | PARTIAL / LIVE BLOCKED | B、BM；live 缺失 | B、BM | `B:stock-golden`、`B:etf-golden`；Task 18 live runner 待执行 | `39e2b752`、`a135899c` | — | preflight 规则已测；真实 start/end/完整月数与 promotable verdict 缺失。 |
| 4 | DETERMINISTIC PASS | B、BM | B、BM | `B:backend-check`、`B:stock-golden`、`B:etf-golden` | `39e2b752`、`a135899c` | — | canonical StrategySpec identity 的精确回归与双 lane packet binding 通过。 |
| 5 | DETERMINISTIC PASS | B、BM | B、BM | `B:backend-check`、`B:stock-golden`、`B:etf-golden` | `39e2b752`、`a135899c` | — | typed override 的精确回归及 runtime/manifest/result identity binding 通过。 |
| 6 | DETERMINISTIC PASS | B、BM | B、BM | `B:backend-check`、`B:scheduler-literal-128` | `39e2b752`、`a135899c` | — | literal 128、2/4 worker 与单 active 的注册上限和重启语义通过。 |
| 7 | DETERMINISTIC PASS | B、BM | B、BM | `B:stock-golden`、`B:etf-golden` | `39e2b752`、`a135899c` | — | 相同完整 identity 的 fingerprint/hash 可重放。 |
| 8 | DETERMINISTIC PASS | B、BM | B、BM | `B:backend-check`、`B:stock-golden`、`B:etf-golden` | `39e2b752`、`a135899c` | — | PIT、split、purge/embargo 的精确回归及双 lane hard-gate identity 通过。 |
| 9 | DETERMINISTIC PASS | B、BM | B、BM | `B:stock-golden`、`B:etf-golden` | `39e2b752`、`a135899c` | — | holdout duplicate/restart ledger 语义通过。 |
| 10 | PARTIAL / LIVE BLOCKED | B、BM；live UI/network 缺失 | B、BM | `B:stock-golden`；Task 18 browser/live runner 待执行 | `acbf19af`、`39e2b752`、`a135899c` | — | selection/contribution/exposure fixture 非空；live 终验缺失。 |
| 11 | PARTIAL / LIVE BLOCKED | B、BM；live publish/reactivate 缺失 | B、BM | `B:etf-golden`、`B:governance-recovery`；Task 18 待执行 | `39e2b752`、`a135899c` | `7f4d277` | fixture 下只证明 fail-closed 与恢复，不能证明 live publish/R1/reactivate 成功。 |
| 12 | DETERMINISTIC PASS | B、BM、F、FM | B、BM、F、FM | `B:hard-gate-zero-write`、`F:ui` | `39e2b752`、`a135899c` | `7f4d277`、`6da94e1` | submit-review 与 publish/promotion 公共路径均被调用并证明 zero-write、active pointer 不变。 |
| 13 | PARTIAL / LIVE BLOCKED | F、FM；live screenshot/trace 缺失 | F、FM | `F:ui`；Task 18 browser runner 待执行 | — | `7f4d277`、`6da94e1` | component contract 不把软统计包装成 PASS；真实浏览器证据缺失。 |
| 14 | PARTIAL / LIVE BLOCKED | B、BM；live reactivate 缺失 | B、BM | `B:governance-recovery`；Task 18 待执行 | `39e2b752`、`a135899c` | `7f4d277` | 原子 pointer/recovery 确定性通过；live R1/EOD 锁版与 reactivate 缺失。 |
| 15 | DETERMINISTIC PASS | B、BM | B、BM | `B:scheduler-literal-128`、`B:governance-recovery`、`B:isolated-backup-restore` | `39e2b752`、`a135899c` | — | experiment/checkpoint/decision/holdout 重启恢复闭环。 |
| 16 | PARTIAL / LIVE BLOCKED | B、BM；live restore manifest 缺失 | B、BM | `B:isolated-backup-restore`；Task 18 live drill 待执行 | `39e2b752`、`a135899c` | — | `tmp_path` 三类 identity/hash parity 通过，不证明 production recovery。 |
| 17 | PARTIAL / LIVE BLOCKED | F、FM；live network trace 缺失 | F、FM | `F:ui`；Task 18 browser runner 待执行 | `a6720e8a` | `246fc5f`、`7f4d277`、`6da94e1` | production live boundary 有确定性契约；`VITE_USE_MOCK=false` 真实 backend 流程缺失。 |
| 18 | PARTIAL | B、BM；frontend final transcript 尚未入 manifest | B、BM | `B:openapi-zero-diff`；frontend 双 codegen fresh 运行 | `a6720e8a`、`39e2b752`、`a135899c` | `246fc5f` | runtime/static OpenAPI hash 为 `97119b…4e221`；frontend fresh zero-diff 已运行，但最终 command transcript 尚未内容寻址。 |
| 19 | DETERMINISTIC PASS | B、BM | B、BM | `B:backend-check`；fresh `arch-check/check/pre-commit-run` | `39e2b752`、`a135899c` | — | B 内 transcript 已内容寻址；2026-08-01 fresh 回归为 12019 passed、1 known xfail、37/37 contracts。 |
| 20 | PARTIAL | F、FM；frontend final transcript 尚未入 manifest | F、FM | `F:ui`；fresh `generate-contracts/audit:routes/prototype:gates/check/build` | — | `7f4d277`、`6da94e1` | UI suite 已内容寻址；全量 final gate 结果需在 Task 19 final manifest 中归档后才能 PASS。 |
| 21 | LIVE BLOCKED | — | — | Task 18 real-browser runner，未获授权 | — | — | 无 live screenshots、trace、network/error report。 |
| 22 | DETERMINISTIC PASS | B、BM | B、BM | `B:scheduler-literal-128` | `39e2b752`、`a135899c` | — | literal 128 压力与故障恢复通过。 |
| 23 | PARTIAL / LIVE BLOCKED | B、BM、F、FM；live bundles 缺失 | B、BM、F、FM | B runner、F runner；Task 18 live runner 待执行 | `39e2b752`、`a135899c` | `7f4d277`、`6da94e1` | 两 lane deterministic bundle 完整；两 lane live release bundle 均缺失。 |

`docs/evidence/r3/manifest.json` 仍是 runner 生成的原始确定性 manifest，本次不手工改写。
Task 18 生成 live artifact 后，Task 19 final reconciliation 必须重新生成 manifest，补齐
第 18/20 项 transcript 与所有 live-only 字段，再重新计算 23 项状态。

## Required live closure

以下内容明确不由本目录的 deterministic report 证明：

- provider entitlement 与许可审阅；
- 真实 certified / strategy-eligible 数据；
- 真实 96 月历史覆盖与性能；
- `VITE_USE_MOCK=false` 的真实浏览器 + live backend 验收；
- production data root 的 backup/restore、cutover 与 rollback。

这些证据只能在 Task 18 hard approval checkpoint 后生成。

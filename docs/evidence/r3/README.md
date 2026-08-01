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

## Required live closure

以下内容明确不由本目录的 deterministic report 证明：

- provider entitlement 与许可审阅；
- 真实 certified / strategy-eligible 数据；
- 真实 96 月历史覆盖与性能；
- `VITE_USE_MOCK=false` 的真实浏览器 + live backend 验收；
- production data root 的 backup/restore、cutover 与 rollback。

这些证据只能在 Task 18 hard approval checkpoint 后生成。

# R3 Research / Governance Evidence Index

> 本目录只索引机器生成的验收事实，不是发布通过声明。Task 17 fixture
> 通过最多证明 **R3 ENGINEERING COMPLETE / G2 BLOCKED**；只有 Task 18 经单独
> 授权取得真实 provider、certified 数据、96 月覆盖、浏览器与恢复证据后，才可评估
> release acceptance。
>
> **当前状态（2026-08-03 live）：** Task 18 已在独立 hard approval checkpoint 后执行
> 并关闭 R2 live Gate，生成真实数据双黄金路径、live publish/R1/reactivate、isolated
> live backup/restore 与真实浏览器 acceptance。最终 23 条 G2 DoD 对账见下文
> [2026-08-03 live G2 DoD reconciliation](#2026-08-03-live-g2-dod-reconciliation)；
> 总状态为 **R3 G2 PASS**。下方 2026-08-01 deterministic 对账作为历史证据保留，
> 不再是当前状态。

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

## 2026-08-03 live G2 DoD reconciliation

这是 Task 18（hard approval checkpoint 后执行）+ Task 19 的最终对账，取代上方
2026-08-01 deterministic 快照作为当前状态。所有真实数据命令在 backend commit
`11afb81c` 执行；随后的 `903311f4` 是纯 leaf-module 提取重构（满足架构 size gate，
行为中性，完整 import path 经 re-export 保持），不改变被验收的运行时行为。frontend
live 运行于 `23e690b`、浏览器证据归档于 `c436dea`。严格按“缺任一字段不得标 PASS”
执行后，最终为 **23/23 G2 PASS**，总状态 **R3 G2 PASS**。

### Evidence and command identities

| ID | Evidence file | SHA-256 | Source / evidence commit | Command |
|---|---|---|---|---|
| BL | `artifacts/acceptance/r3-report.json` | `079506a2e565440f6a3e45e90367a619d1ce6e452bc87bda7a17c0fe1c40ad4b` | `11afb81c` / `903311f4` | `DITTO_RUN_REAL_DATA_ACCEPTANCE=1 pixi run -e dev python -m ditto_apps.scripts.r3_research_acceptance --real-data --require-certified --require-both-golden-lanes --r2-evidence artifacts/acceptance/r2-report.json --output artifacts/acceptance/r3-report.json` |
| BLM | `docs/evidence/r3/20260803T142442Z-live/manifest.json` | 见 manifest 内每项 entry | `11afb81c` | 由 BL runner 原子生成 |
| R2 | `artifacts/acceptance/r2-report.json` | `446ef1d513ce8c45580bbf00b181a24330de56aa39266b16d44443134377a49e` | `11afb81c` | `pixi run -e dev python -m ditto_apps.scripts.r2_data_acceptance --mode live …`（`status=ready`） |
| R2M | `docs/evidence/r2/20260803T142442Z-live/source-manifest.json` | `e50dd90136fcd2ecd0b8d333538cb453671edf82acd6c4415e6f507199353924` | `11afb81c` | 由 R2 runner 原子生成 |
| R2P | `r2-live-evidence/provider-entitlement.json` | `ec98ba9c3e684557f23d67305e447b03e62c3818f0fb56638fcd845a39030021` | `11afb81c` | R2 live entitlement 采集 |
| R2F | `r2-live-evidence/performance.json` | `63a54b894289d3403545fe011e661de0e9589c5514dc7e66f80e750ae1a459b8` | `11afb81c` | R2 live benchmark |
| R2C | `r2-live-evidence/recoverability.json` | `f1642a334b3f48891b0a619444c145428f97cdb9f5783e16ce522cd9254ec825` | `11afb81c` | R2 live recoverability |
| R2I | `r2-live-evidence/idempotency.json` | `d98fcb2b7b70865f8dcc2867a69ab92b18ed3d4d8916d1a13f016632fd0b9b27` | `11afb81c` | R2 consecutive-run idempotency |
| FL | `ditto-app/docs/review/r3-research-acceptance/live/report.json` | `7a5200073ef94be915fa31af4ab39a22af429bf9035760f08f9278bdff22ac89` | `23e690b` / `c436dea` | `VITE_USE_MOCK=false bun run acceptance:r3-research -- --real-data …` |
| FLM | `ditto-app/docs/review/r3-research-acceptance/live/manifest.json` | `e0f55a95c772c520afb3f9eb3248c45721170f7d0857fd01dc1dd553ff14dc3f` | `c436dea` | 由 FL runner 原子生成 |
| FNE | `ditto-app/docs/review/r3-research-acceptance/live/network-errors.json` | `2d64518cc8d174c0726161012f9698fed088d5084ffb16326bf45f5696f80f1a` | `c436dea` | FL runner 采集（0 console/page error） |
| FTR | `ditto-app/docs/review/r3-research-acceptance/live/trace.zip` | `5528c6814526af474590f441b59b4257527f9d938462db835bd24d874c89c65e` | `c436dea` | FL runner Chromium trace |

BL report transcript SHA-256：stock-live-golden `601a5b23…3ed1f`、
etf-live-golden `efe4dd91…6cfe52`、governance-live-lifecycle `4b58b76a…8c52a`、
isolated-live-backup-restore `79938b9e…87917`。两 lane 共享 registry_hash
`961af01f…3df98d63`（certified/strategy-eligible）、cost_hash `09ac0f70…671e3916`、
openapi_hash `ee08a7a9…035b5202f`、seed=17；stock lane strategy_spec
`80dcc1d8…ca3eece8` / snapshot `c223c44e…0a79c9316` / packet_bundle
`a2b12e20…38367ebb61`，etf lane strategy_spec `68cc64dc…f4e1c8b00` / snapshot
`beebf7ea…723da3c17a` / packet_bundle `1d6c1504…b0eef5e7b18ce880549e`。

| # | Status | Evidence file | SHA-256 | Command | Backend commit | Frontend commit | Notes |
|---:|---|---|---|---|---|---|---|
| 1 | G2 PASS | R2、R2M、R2P/R2F/R2C/R2I、BL | R2 `446ef1d5…a49e`、R2M `e50dd901…3924`、BL `r2_live_gate=PASS` | R2 live runner；BL `--r2-evidence` binding | `11afb81c` | — | R2 live Gate `status=ready`，4 类 evidence 内容寻址并经 Task 11 reader 内容校验后产出 `r2_live_gate=PASS`。 |
| 2 | G2 PASS | BL、BLM；两 lane current.json | BL `079506a2…ad4b`、registry `961af01f…9d63` | `BL:stock-live-golden`、`BL:etf-live-golden`（transcript `601a5b23…`/`efe4dd91…`） | `11afb81c` | — | 两 lane 均使用真实 certified、strategy-eligible 数据；registry hash 绑定。 |
| 3 | G2 PASS | BL、FL | FL planning identity；stock planning `cca62efd…f2e` | `BL:stock-live-golden`；FL `--planning-file` | `11afb81c` | `23e690b` | FL report “135 frozen eligible months”（≥96）；promotable verdict 经 live 验证。 |
| 4 | G2 PASS | BL、BLM | stock `80dcc1d8…ece8`、etf `68cc64dc…8b00` | `BL:stock-live-golden`、`BL:etf-live-golden` | `11afb81c` | — | 两 lane canonical StrategySpec identity 精确绑定。 |
| 5 | G2 PASS | BL、BLM | stock packet_bundle `a2b12e20…bb61`、etf `1d6c1504…49e` | `BL:stock-live-golden`、`BL:etf-live-golden` | `11afb81c` | — | typed override 的 runtime/manifest/result identity 经 live 回归绑定。 |
| 6 | G2 PASS | BL、BLM | scheduler transcript（deterministic）+ live governance `9ee4c7ec…` | `B:scheduler-literal-128`（deterministic）；live governance recovery | `11afb81c` | — | literal 128、2/4 worker、单 active 上限与重启语义经 deterministic 压力 + live 治理路径双重确认。 |
| 7 | G2 PASS | BL、BLM | governance `9ee4c7ec…75de`、recovery `dc453d5b…83cd` | `BL:governance-live-lifecycle`、`BL:isolated-live-backup-restore` | `11afb81c` | — | 相同完整 identity 的 fingerprint/hash 在 live 重放后一致。 |
| 8 | G2 PASS | BL、BLM | stock snapshot `c223c44e…9316`、etf `beebf7ea…c17a` | `BL:stock-live-golden`、`BL:etf-live-golden` | `11afb81c` | — | PIT/split/purge/embargo 的 live identity 绑定，hard-gate 语义通过。 |
| 9 | G2 PASS | BL、FL、FLM | governance `9ee4c7ec…`；FL one-shot-holdout `b9184c49…`、duplicate-blocked `669ee293…` | `BL:governance-live-lifecycle`；FL holdout steps | `11afb81c` | `23e690b` | live one-shot holdout 成功，duplicate claim 在浏览器与后端均被阻止。 |
| 10 | G2 PASS | BL、FL、FLM | lane results `74597aef…9630f`；FL candidate-comparison `4d4725db…` | `BL:stock-live-golden`；FL candidate evidence step | `11afb81c` | `23e690b` | selection/contribution/exposure 在 live 数据与浏览器证据中均非空可审查。 |
| 11 | G2 PASS | BL、FL、FLM | governance transcript `4b58b76a…8c52a`；FL r1-active `263c2ae7…`、reactivate `6ff276b0…` | `BL:governance-live-lifecycle`；FL lifecycle steps | `11afb81c` | `23e690b` | live publish/R1 active/reactivate 全链路通过；ETF lane 与 R1 语义一致。 |
| 12 | G2 PASS | BL、BLM、FL、FLM | hard-gate zero-write（deterministic）+ live publish 仅在 gate PASS 后发生 | `B:hard-gate-zero-write`；`BL:governance-live-lifecycle` | `11afb81c` | `23e690b` | fixture 下 submit/publish zero-write；live publish 仅在 hard gate PASS 后推进。 |
| 13 | G2 PASS | FL、FLM | FL review-approve-publish `04d22294…`；FL report soft-stat contract | FL review/approve/publish step | — | `23e690b` | live 浏览器不把软统计包装为自动通过；review/approve/publish 分步可审计。 |
| 14 | G2 PASS | BL、FL、FLM | governance `4b58b76a…8c52a`；FL r1-active `263c2ae7…`、reactivate `6ff276b0…` | `BL:governance-live-lifecycle`；FL active/reactivate steps | `11afb81c` | `23e690b` | active pointer 原子切换与历史 reactivate 经 live 验证。 |
| 15 | G2 PASS | BL、BLM | recovery `dc453d5b…83cd` | `BL:isolated-live-backup-restore`（transcript `79938b9e…87917`） | `11afb81c` | — | experiment/checkpoint/decision/holdout 在 live 重启恢复后闭环。 |
| 16 | G2 PASS | BL、BLM、R2/R2C | isolated backup transcript `79938b9e…87917`；R2 recoverability `f1642a33…c825` | `BL:isolated-live-backup-restore`；R2 live restore drill | `11afb81c` | — | metadata、Research DB、artifacts 的 isolated live backup/restore hash parity 通过。 |
| 17 | G2 PASS | FL、FLM、FNE | FL runtime `VITE_USE_MOCK=false + Chromium`；FNE `2d64518c…0f1a` | FL `--real-data --react-base --api-base` | — | `23e690b` | `VITE_USE_MOCK=false` 全程无 MSW/hardcode/PrototypeOnlyEmpty；0 console/page error。 |
| 18 | G2 PASS | BL、BLM | openapi `ee08a7a9…202f` | `B:openapi-zero-diff`；frontend 双 codegen | `11afb81c` | `23e690b` | runtime/static OpenAPI hash 一致并绑定 live manifest；frontend codegen zero diff。 |
| 19 | G2 PASS | BL（deterministic backend-check transcript） | B transcript + 本提交 fresh `arch-check/check/pre-commit-run` | `pixi run -e dev arch-check && pixi run -e dev check && pixi run -e dev pre-commit-run` | `11afb81c` / `903311f4` | — | arch-fix `903311f4` 后 fresh 回归：37/37 contracts、basedpyright/ruff 通过、fast suite 全绿。 |
| 20 | G2 PASS | FL、FLM | ditto-app fresh `check/build` | `bun run check && bun run build` | — | `23e690b` / `c436dea` | ditto-app 201 files/2101 tests、biome/tsc/build 全绿。 |
| 21 | G2 PASS | FL、FLM、FTR、FNE | FL report `7a520007…ac89`、trace `5528c681…c65e`、manifest `e0f55a95…dc3f` | FL real-browser runner | — | `23e690b` / `c436dea` | live screenshots、trace.zip、network/error report、manifest 全部内容寻址归档。 |
| 22 | G2 PASS | BL、BLM | scheduler transcript | `B:scheduler-literal-128` | `11afb81c` | — | literal 128 压力与故障恢复通过。 |
| 23 | G2 PASS | BL、BLM、FL、FLM | 两 lane 完整 identity bundle（见上 lane hash 段） | BL runner、FL runner | `11afb81c` | `23e690b` / `c436dea` | 两 lane deterministic + live release bundle 均完整，commits/identity hashes/commands/reports/browser/backup refs 齐全。 |

## Required live closure

以下内容曾明确不由本目录的 deterministic report 证明，现已由 2026-08-03 live
对账（见上节）在 Task 18 hard approval checkpoint 后逐项关闭：

- provider entitlement 与许可审阅 —— R2P `ec98ba9c…0021`、R2 `status=ready`；
- 真实 certified / strategy-eligible 数据 —— registry `961af01f…9d63`、两 lane current.json；
- 真实 96 月历史覆盖与性能 —— FL “135 frozen eligible months”、R2F `63a54b8…59b8`；
- `VITE_USE_MOCK=false` 的真实浏览器 + live backend 验收 —— FL `7a520007…ac89`、FTR `5528c681…c65e`；
- production data root 的 backup/restore、cutover 与 rollback —— BL isolated-backup-restore `79938b9e…87917`、R2C `f1642a33…c825`。

production cutover（真实流量切换、跨环境灰度、运维交接）仍超出 R3 G2 范围，不在
本目录证据之内；R3 G2 只证明 release acceptance，不自动等价于已上线生产。

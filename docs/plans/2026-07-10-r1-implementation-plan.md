# R1：日频人工交易 MVP 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task.<br>
> **首次创建**：2026-07-10<br>
> **最近复核**：2026-07-15<br>
> **状态**：READY FOR EXECUTION（唯一近期施工图）<br>
> **目标 Gate**：G1 内部本机 Beta

## 1. 目标

在真实 A 股日级数据上，为一个操作者、一个人工账户、一个活动执行 sleeve 建立可重复的工作流：

```text
D 日收盘数据完成
  → 数据就绪检查
  → 选择活动 published 策略版本
  → EOD 策略运行
  → 持久化 signal package（包括零调仓）
  → 基于账户和持仓生成 D+1 建议数量
  → 人工复核并实际交易
  → 录入一笔或多笔成交
  → 重建持仓、偏差、PnL 与决策证据
```

R1 完成后是**本机内部 Beta**，不是公网服务、商业产品或自动交易系统。

## 2. 已确认的代码基线

以下能力必须复用，不得平行重造：

- `CreateStrategyHandler` / `PublishStrategyHandler` 已在 `ditto_application.commands.strategy`。
- strategy create/publish API 已在 `ditto_apps.api.routes.strategy`。
- seed spec 位于 `ditto_strategy.alpha.seeds`，现有三个 seed ID。
- EOD 是 `ditto_apps.jobs.flows.eod` 的 Prefect flow，并在 19:45 部署调度。
- `SignalPackagePublisher` 已生成 checksum、factor、risk 和 selection reason，但只持久化 intents。
- `StrategyArtifactService` 与 SQLite artifact store 已存在，可保存 package metadata。
- `AccountSnapshotRecord`、`PositionRecord`、`FillRecord` 与 SQLite trade storage 已存在。
- `ditto_execution.target_diff` 和 `quantity_rounding` 已有目标数量、T+1、手数和碎股基础。
- `DailyDecisionQueryFacade`、trade API 和前端 trading adapters 已存在，但契约不完整。
- 前端真实 OpenAPI 生成命令是 `bun run gen:api`，完整检查是 `bun run check`。

## 3. R1 产品决策

### 3.1 账户与策略边界

- R1 只支持一个人工账户 `account_id` 和一个活动执行 sleeve。
- sleeve 使用稳定 `manual-{account_id}-{strategy_id}` 标识，不复用随机 strategy run ID。
- 可发布多个策略供研究比较，但同一账户同一时刻只有一个策略被选为执行策略。
- opening account snapshot 与 opening positions 是基线；其后的 fills 是权威事件；账户/持仓快照是可重建 read model。
- R1 不提供多策略共享现金、多账户归因和券商余额同步。

### 3.2 日期语义

- `signal_date`：策略可见的最后市场数据日期 D。
- `decision_date`：D 日 EOD 运行完成日期。
- `intended_trade_date`：由 A 股交易日历得到的下一个开市日 D+1。
- account/position baseline：不晚于 `signal_date` 的最新已确认快照。
- fill `trade_date`：人工实际成交日期，通常是 `intended_trade_date`，偏离时必须提示 review。

不得把 19:45 生成的 D 日信号表示成 D 日可成交建议。

### 3.3 活动策略语义

- 活动版本是某 `strategy_id` 的**最高 published version**，不是最高任意状态 version。
- 较新的 draft 不得遮住已 published 版本。
- R1 的回滚方式是从历史 spec 创建并发布一个新版本；不修改已发布历史。
- 完整审批、废弃、策略市场和多环境 promotion 留到 R3。

### 3.4 EOD 与幂等语义

- 逻辑 batch key：`strategy_id + strategy_version + signal_date`。
- 相同 batch key、相同 checksum 重跑必须 no-op，并返回已存在结果。
- checksum 只覆盖确定性业务 payload，不包含生成时间、随机 run ID 或 intent ID。
- artifact/intent ID 同时包含 batch key 与 checksum revision；相同 batch 的旧 revision 必须保留，不得 `UPSERT` 抹掉证据。
- 相同 batch key、不同 checksum 且没有 fill 时，旧 pending intents 可被 `superseded`，旧 package 归档，新 package 成为 active。
- 已有 fill 时禁止静默覆盖，状态为 `review`，由人决定是否接受新建议。
- 零 intents 仍必须持久化成功 package，标记 `no_rebalance=true`。
- package 缺失表示未运行或失败，绝不能解释成“今日无信号”。

### 3.5 Readiness 判定

优先级固定为 `blocked > review > ready`：

| 条件 | 状态 | reason code |
|---|---|---|
| 无活动 published 策略 | blocked | `NO_ACTIVE_STRATEGY` |
| 必需数据缺失、过期或质量失败 | blocked | `REQUIRED_DATA_NOT_READY` |
| 无合格账户/持仓基线 | blocked | `ACCOUNT_BASELINE_MISSING` |
| EOD 未运行或失败 | blocked | `EOD_RUN_MISSING` / `EOD_RUN_FAILED` |
| run 成功但 package 缺失或校验失败 | blocked | `SIGNAL_PACKAGE_MISSING` / `CHECKSUM_MISMATCH` |
| package 成功且零 intents | review | `NO_REBALANCE_REQUIRED` |
| 风险 warning、日期偏离或重跑冲突 | review | `RISK_WARNING` / `TRADE_DATE_MISMATCH` / `RERUN_CONFLICT` |
| 建议数量无法生成但权重可复核 | review | `QUANTITY_UNAVAILABLE` |
| package、数据、账户、建议数量和风险均通过 | ready | `READY_FOR_REVIEW` |

前端不得从中文 message 猜状态，只消费 reason code。

## 4. 严格非目标

- AI、LLM、情绪因子和 Agent runtime。
- 分钟级、盘中计算、实盘行情流和券商自动下单。
- cvxpy、高级组合优化和连续盘中风控。
- 多账户、多租户、认证/RBAC 和公网部署。
- fx/commodity 全量 promotion。
- 策略市场、完整审批流和自动参数搜索。

## 5. 开发与提交规则

- 每个 task 使用 RED → GREEN → REFACTOR，并在 task 结束形成独立提交。
- 新功能必须有单元测试；API 变更必须有集成测试。
- 默认测试不得访问真实供应商；真实数据只进入带显式凭证的 acceptance。
- 数据库 schema 变更、依赖变更、环境配置和架构边界变更必须先获得人工批准。
- 不修改 `wave1_env.sh` 注入 token；凭证继续走 env > keyring > config provider。

## 6. 实施任务

### Task 1：活动 published 版本与 seed bootstrap

**目标**：消除 draft 遮住 published 的错误语义，并提供可重复、可审计的 seed 初始化入口。

**Files:**

- Modify: `packages/strategy/src/ditto_strategy/storage/sqlite/strategy_spec_store.py`
- Modify: `packages/strategy/src/ditto_strategy/storage/sqlite/services/strategy_catalog_service.py`
- Modify: `packages/application/src/ditto_application/queries/strategy.py`
- Add: `packages/application/src/ditto_application/processes/strategy/seed_bootstrap.py`
- Modify: `packages/apps/src/ditto_apps/cli/commands/strategy.py`
- Test: `packages/data/tests/unit/storage/metadata/test_strategy_spec_store_unit.py`
- Test: `packages/application/tests/unit/query/test_strategy_query_unit.py`
- Add: `packages/application/tests/unit/process/strategy/test_seed_bootstrap_unit.py`
- Test: `packages/apps/tests/unit/cli/commands/test_strategy_unit.py`

**Steps:**

1. 写失败测试：同一策略 v1 published、v2 draft 时，latest published 返回 v1，published 列表包含该策略。
2. 在 store/service 增加 `get_latest_published(strategy_id)` 与 `list_latest_published()`，查询中显式 `WHERE status = 'published'` 后再取最高 version。
3. 修改 EOD/strategy query 的活动策略读取入口，只使用 latest-published 语义；保留 generic latest 供编辑草稿使用。
4. 写 seed bootstrap 失败测试：空库创建并发布三个 seed；再次运行 no-op；已有同 ID 不同 spec 时 fail closed 并输出差异，不静默覆盖。
5. bootstrap 复用 `CreateStrategyHandler` 和 `PublishStrategyHandler`；不直接写 SQLite，不复制生命周期规则。
6. 增加 `ditto strategy bootstrap-seeds`，输出 `created/published/unchanged/conflict` 结构化摘要。
7. 增加 CLI 与 store/query 测试，运行相关测试并提交。

**Verify:**

```bash
pixi run -e dev pytest packages/data/tests/unit/storage/metadata/test_strategy_spec_store_unit.py packages/application/tests/unit/query/test_strategy_query_unit.py packages/application/tests/unit/process/strategy/test_seed_bootstrap_unit.py packages/apps/tests/unit/cli/commands/test_strategy_unit.py -q
```

### Task 2：人工账户基线与单 sleeve 契约

**目标**：把已有 account/position storage 变成 Daily Decision 可依赖的明确事实源。

**Files:**

- Modify: `packages/execution/src/ditto_execution/contracts.py`
- Modify: `packages/execution/src/ditto_execution/audit/models.py`
- Modify: `packages/execution/src/ditto_execution/audit/execution_audit_service.py`
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/service.py`
- Add: `packages/application/src/ditto_application/commands/account.py`
- Add: `packages/application/src/ditto_application/queries/account.py`
- Modify: `packages/application/src/ditto_application/providers_command.py`
- Modify: `packages/application/src/ditto_application/providers_portfolio.py`
- Modify: `packages/apps/src/ditto_apps/models/trade.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/trade_command_routes.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/trade_query_routes.py`
- Test: `packages/execution/tests/unit/test_trade_data_ports_unit.py`
- Modify: `packages/execution/tests/unit/audit/test_execution_audit_service_unit.py`
- Add: `packages/application/tests/unit/commands/test_account_unit.py`
- Add: `packages/application/tests/unit/query/test_account_unit.py`
- Modify: `packages/apps/tests/integration/api/test_trade_api_integration.py`

**Contract:**

- `ImportAccountBaselineCommand` 一次提交 account snapshot 与零到多条 position snapshot。
- 验证 account/position 的 strategy、snapshot date、run/sleeve identity 一致。
- 同一 `account_id + strategy_id + snapshot_date` 的相同内容重放为 no-op；不同内容必须显式 `replace_confirmed=true`，并在现有 `execution_audit` 保存 old/new baseline payload 后再更新 read model。
- account 与全部 positions 必须先完整校验，再在同一事务提交；任一写入失败不得留下半份 baseline。
- 查询返回“不晚于 signal_date 的最新完整基线”，禁止拼接来自不同日期的 account 与 positions。
- API 必须拒绝负现金、负总资产、负持仓、可用数量大于总数量和市值合计明显不一致。

**Steps:**

1. 先为窄 `AccountDataPort`、baseline command 和同日一致性规则写失败测试。
2. 将已有 `TradeService.save/get/list_account_snapshot` 通过窄 port 暴露，不把 SQLite 类型泄漏到 application。
3. 为现有 execution audit 增加 account baseline import/correction typed payload；复用其 TEXT `record_type`，不新增表或列。
4. 实现 baseline command/query 和原子事务，并复用现有 `PositionDataPort`。
5. 增加 account baseline command/query API DTO；响应返回稳定 snapshot ID 和 sleeve ID。
6. 增加 API 集成测试：空持仓、有效持仓、非法余额、日期不一致、半写入回滚、幂等重放和显式替换。
7. 运行相关测试并提交。

**Verify:**

```bash
pixi run -e dev pytest packages/execution/tests/unit/test_trade_data_ports_unit.py packages/execution/tests/unit/audit/test_execution_audit_service_unit.py packages/application/tests/unit/commands/test_account_unit.py packages/application/tests/unit/query/test_account_unit.py packages/apps/tests/integration/api/test_trade_api_integration.py -q
```

### Task 3：建议数量与 A 股交易规则接线

**目标**：使用账户 NAV、当前持仓和参考收盘价，把目标权重转为可解释的人工交易建议数量。

**Files:**

- Modify: `packages/execution/src/ditto_execution/target_diff.py`
- Modify: `packages/execution/src/ditto_execution/quantity_rounding.py`
- Add: `packages/application/src/ditto_application/processes/execution/manual_sizing.py`
- Modify: `packages/application/src/ditto_application/processes/execution/signal_snapshot.py`
- Test: `packages/execution/tests/unit/test_target_diff_unit.py`
- Test: `packages/execution/tests/unit/test_quantity_rounding_unit.py`
- Add: `packages/application/tests/unit/process/execution/test_manual_sizing_unit.py`

**Rule matrix:**

- 买入数量必须是 board lot 的整数倍，且不能超过可用现金与风险上限。
- 卖出优先使用 `available_quantity`，受 T+1 限制；允许按既有规则处理持仓碎股。
- 小于阈值或不足一手的差额不强行生成交易，必须给出原因。
- 停牌、涨跌停或缺参考价时不伪造数量，输出 blocked/review 原因。
- 所有结果包含 `raw_quantity`、`rounded_quantity`、`lot_size`、`reference_price`、`cash_impact` 和 rounding reason。

**Steps:**

1. 扩充现有 quantity/target-diff 矩阵测试，重点覆盖 150 股原始买入、碎股卖出、T+1、现金不足和缺价格。
2. 仅修复规则测试证明的问题，不新建第二套 rounding helper。
3. 新增 application `ManualSizingService`，组合 account baseline、positions、close price 与 execution planner。
4. 将 suggested quantity 写入新生成的 intent；已有历史 intent 不回填。
5. 测试确定性、现金上限和 reason code，运行相关测试并提交。

**Verify:**

```bash
pixi run -e dev pytest packages/execution/tests/unit/test_target_diff_unit.py packages/execution/tests/unit/test_quantity_rounding_unit.py packages/application/tests/unit/process/execution/test_manual_sizing_unit.py -q
```

### Task 4：持久化 Signal Package 与同日重跑幂等

**目标**：让成功、零调仓、失败和重跑冲突成为可查询、可校验的不同事实。

**Files:**

- Modify: `packages/strategy/src/ditto_strategy/models.py`
- Modify: `packages/application/src/ditto_application/processes/execution/signal_package.py`
- Modify: `packages/application/src/ditto_application/processes/execution/strategy_run_process.py`
- Modify: `packages/application/src/ditto_application/commands/trade.py`
- Modify: `packages/execution/src/ditto_execution/contracts.py`
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/intents.py`
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/service.py`
- Modify: `packages/application/src/ditto_application/providers_process.py`
- Modify: `packages/apps/src/ditto_apps/models/trade.py`
- Test: `packages/application/tests/unit/process/execution/test_signal_package_unit.py`
- Test: `packages/data/tests/unit/storage/metadata/test_strategy_artifact_store_unit.py`
- Modify: `packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py`

**Artifact contract:**

- 新增 `ArtifactKind.SIGNAL_PACKAGE`。
- deterministic artifact ID 包含 strategy、version、signal date 和 checksum revision。
- metadata 至少包含 schema version、run/batch key、signal/decision/intended trade dates、dataset snapshots、factor IDs/values、risk flags、selection reasons、完整 intent payload、checksum、`no_rebalance` 和 outcome。
- checksum 不包含生成时间等非确定字段。

**Steps:**

1. 写失败测试：零 intents 仍保存 package；相同输入重跑返回同 artifact/checksum 且不重复 intent。
2. 为 package publisher 注入现有 `StrategyArtifactService`，持久化完整 package，而非只保留内存对象。
3. EOD 显式传入 deterministic batch key；不要继续依赖随机 `_resolve_run_id()` 表达业务身份。
4. 先计算不含 ID/时间的业务 checksum，再用 `batch key + checksum revision` 生成 artifact/intent ID。
5. 为 intent writer 增加“按 stable intent ID 幂等保存”语义：完全相同则 no-op，已成交不得覆盖；状态集合增加 `superseded`，只允许 pending intent 进入该状态。
6. 对 checksum 变化实现 fail-closed 冲突结果；只有无 fill 的 pending intent 才可 supersede，旧 artifact 必须归档保留。
7. 增加 same date retry、changed checksum、zero intent、已有 fill conflict 和 consecutive dates 集成测试。
8. 运行相关测试并提交。

**Verify:**

```bash
pixi run -e dev pytest packages/application/tests/unit/process/execution/test_signal_package_unit.py packages/data/tests/unit/storage/metadata/test_strategy_artifact_store_unit.py packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py -q
```

### Task 5：EOD Outcome、按策略数据就绪与运营入口

**目标**：让 Prefect 调度和人工重跑共用同一业务编排，并输出可操作的结果。

**Files:**

- Modify: `packages/strategy/src/ditto_strategy/alpha/specs.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/seeds.py`
- Modify: `packages/application/src/ditto_application/builders/deserialization.py`
- Add: `packages/application/src/ditto_application/processes/execution/eod_coordinator.py`
- Modify: `packages/apps/src/ditto_apps/jobs/flows/eod.py`
- Modify: `packages/apps/src/ditto_apps/cli/commands/ops.py`
- Add: `packages/application/tests/unit/process/execution/test_eod_coordinator_unit.py`
- Modify: `packages/strategy/tests/unit/alpha/test_specs_unit.py`
- Modify: `packages/apps/tests/unit/jobs/flows/test_eod_flow_unit.py`
- Add: `packages/apps/tests/unit/cli/commands/test_ops_eod_unit.py`
- Add: `docs/runbooks/r1-daily-operations.md`

**Outcome contract:**

每个策略返回 `completed / no_rebalance / blocked / failed / rerun_conflict`，并包含 strategy version、batch key、required dataset states、artifact ID、checksum 和机器可读原因。

**Steps:**

1. 写 coordinator 失败测试：只因某个不相关数据集 ingestion 失败，不应阻塞不依赖该数据集的策略。
2. 为 `StrategySpec` 增加显式 `required_datasets`，同步反序列化与三个 seed；字段缺失的旧 spec 使用模板默认映射并输出迁移 warning。
3. 从 strategy spec 提取 required datasets，对每个策略独立判断 freshness、DQ 和 snapshot；未知 dataset fail closed。
4. 将 EOD 的纯业务顺序放入 coordinator；Prefect flow 只负责调度、重试、日志和依赖注入。
5. 增加 `ditto ops run-eod --signal-date YYYY-MM-DD [--strategy-id ID]`，调用同一 coordinator；该命令在 Task 5 之前不存在。
6. CLI 返回非零退出码处理 blocked/failed，结构化打印每个策略 outcome，日志不得包含 token。
7. 编写日常 runbook：preflight、正常运行、重跑、冲突处理、备份、失败恢复和收盘后核对。
8. 运行相关测试并提交。

**Verify:**

```bash
pixi run -e dev pytest packages/strategy/tests/unit/alpha/test_specs_unit.py packages/application/tests/unit/process/execution/test_eod_coordinator_unit.py packages/apps/tests/unit/jobs/flows/test_eod_flow_unit.py packages/apps/tests/unit/cli/commands/test_ops_eod_unit.py -q
```

### Task 6：多笔部分成交与追加式更正

**目标**：同一 intent 同日可录入多笔成交，重复请求按 fill ID 幂等，错误录入可追溯地撤销或替换。

**Approval checkpoint:**

本 task 计划新增 `execution_fill_adjustments` 表。执行前必须向用户展示 DDL、迁移/回滚方案并取得数据库 schema 变更批准。未批准时停止本 task，不得改用破坏性覆盖规避审批。

**Approval recorded (2026-07-16):** 用户已批准该 schema，并明确系统尚未上线，
无需兼容旧 schema、回填历史 fill 或保留历史迁移/回滚数据。实现以 fresh schema
初始化为准；开发库允许重建。该简化只作用于上线前迁移，上线后的原 fill
append-only、adjustment 可追溯和 effective-fill 计算规则仍是强制不变量。

**Files:**

- Modify: `packages/execution/src/ditto_execution/models.py`
- Modify: `packages/execution/src/ditto_execution/contracts.py`
- Add: `packages/execution/src/ditto_execution/storage/sqlite/trade/fill_adjustments.py`
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/fills.py`
- Modify: `packages/execution/src/ditto_execution/storage/sqlite/trade/service.py`
- Modify: `packages/application/src/ditto_application/commands/trade.py`
- Modify: `packages/application/src/ditto_application/queries/trade.py`
- Modify: `packages/apps/src/ditto_apps/models/trade.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/trade_command_routes.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/trade_query_routes.py`
- Test: `packages/execution/tests/unit/trade/test_trade_service_unit.py`
- Test: `packages/application/tests/unit/commands/test_trade_unit.py`
- Test: `packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py`
- Test: `packages/apps/tests/integration/api/test_trade_api_integration.py`

**Ledger rules:**

- `fill_id` 是请求幂等键；相同 fill ID 和相同 payload 为 no-op，不同 payload 为 conflict。
- `intent_id + trade_date` 不再承担幂等职责，同日允许多笔 fill。
- 原 fill 永不 UPDATE/DELETE；void/replacement 通过 adjustment 事件记录，必须有 reason、时间和关联 fill。
- status、position、deviation 和 PnL 只消费 effective fills。
- 累积有效数量不得静默超过 intent quantity；超过时进入 review。

**Approved fresh schema（2026-07-16）:**

| 列 | 类型/约束 | 语义 |
|---|---|---|
| `adjustment_id` | TEXT PRIMARY KEY | 更正请求幂等键 |
| `fill_id` | TEXT NOT NULL | 被 void/replaced 的原 fill |
| `adjustment_type` | TEXT NOT NULL | `void` 或 `replace` |
| `replacement_fill_id` | TEXT NULL | replace 时指向新 append-only fill |
| `reason` | TEXT NOT NULL | 人工更正理由 |
| `created_at` | TEXT NOT NULL | 审计时间 |

对 `fill_id` 建唯一索引；若 replacement 仍需更正，则对 replacement fill 新增下一条 adjustment。当前为未上线 fresh-schema 阶段，不做旧 fill 回填、兼容 shim 或历史迁移保留；开发环境回滚可直接重建数据库。首次实际使用后，fill 与 adjustment 证据不得原地改写或删除。

**Steps:**

1. 取得 schema 批准后，先写多笔 fill、fill ID conflict、void、replacement 和重建失败测试。
2. 增加 adjustment model/store/port 与 effective-fill query；fresh schema 直接初始化，不提供旧 fill 回填或兼容迁移。
3. 修改 `RecordFillHandler`：先按 fill ID 幂等，再累计同 intent 的 effective fills。
4. 增加 void/replace command 与 API，禁止直接暴露 store `replace()`。
5. 让 ManualTracker、intent status、deviation 和 PnL 使用 effective fills。
6. 增加完整 API 与 E2E 测试，运行相关测试并提交。

**Verify:**

```bash
pixi run -e dev pytest packages/execution/tests/unit/trade/test_trade_service_unit.py packages/application/tests/unit/commands/test_trade_unit.py packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py packages/apps/tests/integration/api/test_trade_api_integration.py -q
```

### Task 7：Daily Decision V2 契约与 API

**目标**：提供一个可由操作者直接判断“今天能否复核/交易、为什么”的稳定 read model。

**Files:**

- Modify: `packages/application/src/ditto_application/queries/daily_decision.py`
- Modify: `packages/application/src/ditto_application/providers_portfolio.py`
- Modify: `packages/apps/src/ditto_apps/models/trade.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/trade_query_routes.py`
- Test: `packages/application/tests/unit/query/test_daily_decision_query_unit.py`
- Modify: `packages/apps/tests/integration/api/test_trade_api_integration.py`

**V2 response sections:**

- identity：strategy ID/version、account/sleeve、signal/decision/intended trade date。
- readiness：status、reason codes、human-readable details。
- data：required datasets、freshness、snapshot IDs、DQ state。
- run/package：run outcome、artifact ID、checksum、no-rebalance、factor/risk evidence。
- account/positions：baseline identity、cash、NAV、持仓与 as-of。
- actions：target/current/delta weight、suggested quantity、参考价、手数、理由、风险和 intent status。
- execution review：effective fills、deviation、PnL、异常和 unresolved conflicts。

**Steps:**

1. 将 3.5 的 readiness truth table 写成 table-driven 失败测试，覆盖优先级。
2. facade 依赖窄 query/reader ports，不在 API route 或前端重复业务判断。
3. 读取 persisted signal package，而不是以 intents 是否为空推断 run 状态。
4. 定义 V2 Pydantic DTO、OpenAPI examples 和 reason code enum；保持旧字段一个 release 的兼容或明确 `/v2` 路径。
5. API 集成测试覆盖 ready、no-rebalance review、data blocked、run failed、account missing、risk warning 和 rerun conflict。
6. 保持 `/api/v1/trade` maturity 为 `experimental`；本 task 只准备 promotion evidence，不提前提级。
7. 运行相关测试并提交。

**Verify:**

```bash
pixi run -e dev pytest packages/application/tests/unit/query/test_daily_decision_query_unit.py packages/apps/tests/integration/api/test_trade_api_integration.py -q
```

### Task 8：ditto-app Trading Live 工作台

**Repository:** `/home/chevy/projects/ditto-app`

**目标**：`VITE_USE_MOCK=false` 时，Trading 域不再依赖 prototype fallback，完整支持复核、成交录入和盘后复盘。

**Files:**

- Modify: `src/types/generated/api.d.ts`（只由生成脚本更新）
- Modify: `src/features/trading/api/daily-decision.ts`
- Modify: `src/features/trading/api/intents.ts`
- Modify: `src/features/trading/api/fills.ts`
- Modify: `src/features/trading/components/trading-page.tsx`
- Modify: `src/features/trading/components/signals-page.tsx`
- Modify: `src/features/trading/components/orders-page.tsx`
- Modify: `src/features/trading/components/portfolio-page.tsx`
- Modify: existing trading component/API tests

**UX states:**

- blocked：显示阻塞原因与对应操作入口，不显示可执行建议。
- review：明确零调仓、风险 warning、日期偏离或冲突，允许查看证据但要求人工确认。
- ready：展示建议操作、目标/当前/差额、建议数量、参考价、理由和风险。
- fill drawer/dialog：允许同一 intent 多次录入，提供历史与追加式更正入口。
- review view：显示 effective fills、剩余数量、偏差、PnL 和 package checksum。

**Steps:**

1. 启动已完成 Task 7 的后端，运行 `bun run gen:api`，不得手写 generated types。
2. 先更新 API mapper/query 测试，覆盖 reason codes、no-rebalance 和 multiple fills。
3. 更新 trading 页面；业务状态来自后端，前端只做展示与交互保护。
4. 删除 Trading live 路径的 prototype fallback；mock 模式仍保留用于原型开发。
5. 增加 loading、empty、error、retry、conflict、keyboard/focus 和窄屏测试。
6. 在 desktop/mobile 视口做 Playwright/visual audit，确认无重叠和长文本溢出。
7. 运行前端完整检查并在 ditto-app 独立提交。

**Verify:**

```bash
bun run gen:api
bun run check
bun run visual:audit
```

### Task 9：G1 端到端验收、恢复与证据包

**目标**：用确定性 fixture 和一次显式真实数据演练证明 R1 工作流，而不是只证明测试绿。

**Files:**

- Add: `packages/apps/tests/e2e/test_r1_daily_manual_trading.py`
- Modify: `docs/runbooks/r1-daily-operations.md`
- Add: `docs/acceptance/r1-g1-evidence-template.md`
- Modify: `docs/plans/2026-07-10-capability-benchmark-design.md`（验收通过后才更新分数）
- Modify: `packages/apps/src/ditto_apps/api/maturity.py`（G1 通过后）
- Modify: `packages/apps/tests/integration/api/test_trade_api_integration.py`

**四层验收:**

| 层 | 必须证明 |
|---|---|
| 确定性 E2E | bootstrap → baseline → EOD → package → decision → two partial fills → correction → review |
| 重跑/恢复 | 同日相同输入 no-op、不同输入 conflict、进程中断后重跑、SQLite 备份恢复 |
| 真实数据 acceptance | 一次指定交易日、指定 seed、真实 provider 的 DQ/freshness/package/decision 证据；凭证不入库 |
| 前端验收 | `VITE_USE_MOCK=false` 的 blocked/review/ready、成交和复盘；desktop/mobile 截图 |

**Steps:**

1. 增加确定性 R1 E2E，测试零调仓日和有交易日。
2. 演练同日重跑、进程中断、数据库备份与恢复，记录恢复时间和校验结果。
3. 在显式 live 标记下运行一次真实数据 acceptance；供应商不可用时记录外部阻塞，不降低默认测试确定性。
4. 验证服务只绑定 `127.0.0.1`，无认证时不得监听外网接口。
5. 运行后端全量 `check`、架构门禁和前端 `check`。
6. 填写 evidence template，逐项给出命令、时间、commit SHA、artifact/checksum 与结果。
7. 所有 G1 条件通过后，才将 `/api/v1/trade` 从 `experimental` 提升到 `initial-focus`，并更新能力评分和 evidence，提交文档。

**Verify:**

```bash
pixi run -e dev check
pixi run -e dev arch-check
pixi run -e dev pytest packages/apps/tests/e2e/test_r1_daily_manual_trading.py -q
```

前端仓库：

```bash
bun run check
```

## 7. 依赖与执行顺序

```text
Task 1 活动策略 ───────────────┐
Task 2 账户基线 ─→ Task 3 数量 ├─→ Task 4 package/幂等
                              └─→ Task 5 EOD/运营入口
Task 4 + Task 2 ─→ Task 6 成交账本（需 schema approval）
Task 1-6 ───────→ Task 7 Daily Decision V2
Task 7 ─────────→ Task 8 ditto-app live
Task 1-8 ───────→ Task 9 G1 验收
```

建议严格按 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 执行。Task 8 在独立前端仓库提交，后端 OpenAPI 契约冻结后再生成类型。

## 8. G1 完成定义

R1 只有在以下条件全部满足时完成：

- [ ] seed bootstrap 幂等，活动 published 版本选择正确。
- [ ] 账户与持仓基线完整，单 sleeve 规则 fail closed。
- [ ] D 日数据只产生 D+1 建议，数量、手数、现金和 T+1 可解释。
- [ ] signal package 对有信号和零调仓都持久化并可校验。
- [ ] 同日重跑不重复 intent，checksum 冲突不静默覆盖。
- [ ] 一个 intent 可录入多笔部分成交，错误录入可追加式更正。
- [ ] Daily Decision 的 blocked/review/ready 与 reason code 真值表一致。
- [ ] `ditto-app` live 模式不使用 Trading prototype fallback。
- [ ] Prefect 调度和 CLI 人工重跑共用同一 coordinator。
- [ ] SQLite 备份/恢复演练通过，runbook 可由操作者独立执行。
- [ ] 后端与前端完整检查、架构门禁、确定性 E2E 全部通过。
- [ ] 至少一份真实数据 evidence 包完成；token、账户敏感信息不进入日志或仓库。
- [ ] 服务保持 loopback-only，未实现认证前不得对外暴露。

任一项未完成，G1 仍为 FAIL，不以“综合分已达某值”替代。

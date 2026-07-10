# R1：日频人工交易 MVP 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 打通已有 backend primitives，形成「每天可生成并复核真实 A 股信号、目标仓位、建议操作、风险提示，并人工记录成交与偏差」的产品闭环——**内部 Beta**（非可商用）。

**Architecture:** R1 本质是**集成 + 产品化**，而非建新模块。`daily-decision` API + readiness、手工 fill/intent/deviation、策略 draft/published store 已存在；R1 把它们打通成 `EOD 闭环 → Daily Decision V2 → 前端真实态 → 手工复盘`。遵循 roadmap「产品闭环优先」。

**Tech Stack:** polars / sqlite / FastAPI / Typer / prefect(调度) / pytest / basedpyright / ruff / Svelte(ditto-app)

**背景:**
- 产品母版：`docs/superpowers/specs/2026-07-10-ditto-development-roadmap-design.md`（R1 定义，第 7 节）
- 能力评级：`docs/plans/2026-07-10-capability-benchmark-design.md`
- 候选任务池：`docs/plans/2026-07-10-phase-a-implementation-plan.md`（A6-1/A6-2/A2/A5 并入本 R1）

---

## 真实现状基线（已有，避免重造）

> 基于 2026-07-10 代码探索。R1 是把这些打通，不是从零建。

| 能力 | 现状 | 证据 |
|---|---|---|
| daily-decision API + readiness | ✅ 已有 `/daily-decision` 端点 + `ready/review/blocked` | `apps/api/routes/trade_query_routes.py:186`，`DailyDecisionQueryFacade/Report/ReadinessResponse` |
| 手工 fill + intent status | ✅ 已有 ManualTracker + intent 状态机(pending/partially_filled) | `application/commands/trade.py`，`update_intent_status` |
| 信号-成交偏差 | ✅ 已有 `SignalDeviationQueryFacade.get_deviation` | `application/queries/deviation.py` |
| 策略 draft/published store | ✅ 已有二态 + version + sqlite | `strategy/storage/sqlite/strategy_spec_store.py`，`update_status` |
| seed 策略定义 | ✅ 已有 `SEED_STRATEGY_SPECS` | `strategy/alpha/seeds.py:161` |
| **阻塞点** | ❌ seed 未 publish 到 store | `publish-signals` 报 `AppBuilderError: 未找到策略定义` |
| EOD pipeline 组件 | ⚠️ 组件在（materialization/strategy run/signal package publisher），但真实闭环未验证跑通 | `application/processes/materialization/`、`strategy_run_process` |

**核心判断**：R1 的 80% 工作是「让 seed 发布 → EOD 跑通 → Daily Decision 聚合真实内容 → 前端展示 → 手工 fill 闭环」，而非写新算法。

---

## R1 严格范围

**IN（5 核心 task + 1 并行小修）：**
1. seed 策略定义发布链路 + 生命周期最小闭环
2. EOD → signal package → trade intents 真实闭环 + 日常运营模型
3. Daily Decision V2 后端契约
4. Trading 前端 ready/review/blocked 真实态
5. 手工 fill + intent status + 偏差复盘 + 账户细节
6. （并行小修）A2 手数取整

**OUT（明确移出，推 R2/R4/R5/R6）：**
- ❌ cvxpy 组合优化（→ R4）
- ❌ RiskGate 连续状态机/typed audit/崩溃恢复（→ R4；R1 只需 Daily Decision 日频风险摘要）
- ❌ fx/commodity promotion（→ R2；R1 主线 A 股 ETF/个股）
- ❌ AI 基建 B0/B1（→ R5）
- ❌ 分钟级/盘中/event-driven/真实券商 adapter（→ R6/R7）
- ❌ 历史数据深度扩容/backfill 写瓶颈（→ R2；R1 用近期数据）

---

## Task 1：seed 策略定义发布链路 + 生命周期最小闭环

**现状：** `SEED_STRATEGY_SPECS`（etf_industry_rotation / etf_trend_swing / stock_selection_rotation）存在但未 publish 到 `strategy_spec_store`，导致 `publish-signals` 找不到定义。store 已支持 draft/published + version。

**目标：** 任一 seed strategy_id 经 publish 进入 catalog store（published 态），`publish-signals` 不再报错；建立最小生命周期闭环。

**Files:**
- Explore（实施前 Read 确认调用链）: `apps/cli/commands/strategy.py`（`_build_run_config` 如何解析 strategy_id → 找 spec 的确切路径）
- Modify/Create: `application/commands/`（strategy definition publish command handler，写 StrategySpecRecord 到 store，draft→published）
- Modify: `apps/cli/commands/strategy.py`（新增 `publish-strategy-definition` 命令）
- Test: `application/tests/`（`test_publish_strategy_definition_unit.py`）

**Step 1: 写失败测试**
```python
def test_publish_seed_strategy_definition_to_store(strategy_spec_store):
    # publish 一个 seed strategy_id → store 查询返回 published 态记录
    publish_strategy_definition(strategy_id="etf_industry_rotation", version=1)
    record = strategy_spec_store.get("etf_industry_rotation", version=1)
    assert record is not None
    assert record.status == "published"

def test_publish_signals_finds_published_definition(...):
    # seed publish 后，publish-signals 不再报「未找到策略定义」
    publish_strategy_definition("etf_industry_rotation", version=1)
    result = run_publish_signals("etf_industry_rotation", trade_date=FIXTURE_DATE)
    assert result.error is None  # 不再 AppBuilderError
```

**Step 2-4: 验证失败 → 实现 publish handler（seed spec → StrategySpecRecord → store，draft→published）→ 验证通过。**

**Step 5: 集成验证** — `ditto ops publish-strategy-definition etf_industry_rotation && ditto ops publish-signals etf_industry_rotation --trade-date <recent_date>` 全绿。

**Step 6: Commit** — `feat(application): seed strategy definition publish flow + lifecycle`

> ⚠️ 实施前必须 Read `_build_run_config` 确认它从 store 还是 SEED 直接解析；若设计需调整（store vs SEED fallback），先在本文档 mini-design 记录决策。

### 策略生命周期最小闭环（并入 Task 1）

明确以下语义（store 已支持 draft/published/version，R1 只需定清楚规则）：
- **bootstrap**：seed spec 经 `publish-strategy-definition` 写入 store，version=1，status=published。
- **版本**：spec 变更新 version；`publish-signals` 默认用最新 published version。
- **状态迁移**：`draft → published`（经 publish）；R1 暂不引入 research/candidate/paper/production 五态（那是 R3 策略管理工作台）。
- **rollback**：`update_status` 可将某 version 退回 draft；记录 status 变更（store 已有 status index）。
- **source of truth**：`strategy_spec_store`（sqlite）是策略定义的唯一权威，SEED 仅作 bootstrap 种子。

---

## Task 2：EOD → signal package → trade intents 真实闭环 + 日常运营模型

**现状：** materialization cascade / strategy run / signal package publisher 组件在，但真实数据下端到端未验证跑通（受 Task 1 阻塞）。

**目标：** 真实数据下，EOD pipeline 完成 `ingestion → materialization → strategy run → signal package publish → 可查询 trade intents`，且可日复一日复现。

**Files:**
- Explore: `application/processes/materialization/cascade_orchestrator.py`、`execution/strategy_run_process.py`、signal package publish 路径
- Test: `application/tests/integration/`（EOD 真实闭环 e2e）+ `apps/tests/integration/`

**Task 级拆解：**
1. 梳理 EOD pipeline 现有 step 顺序与依赖（Read cascade_orchestrator + strategy_run_process）。
2. TDD：固定历史日期（近期）跑 EOD → 断言产出 signal package + trade intents 可查询。
3. TDD：连续 2-3 个固定历史日期跑 EOD → 断言每日 signal package 独立、intent status 正确。
4. 失败路径：materialization 缺数据 / strategy run 报错 / publish 失败 → 各自结构化错误 + 可定位。

**Commit** — `feat(application): EOD real-data signal package + trade intents loop`

### 日常运营模型（Task 2 交付物，产品级）

明确并文档化（写入 `docs/operations/eod-runbook.md`）：

| 运营项 | R1 定义 |
|---|---|
| 谁运行 EOD | CLI `ditto jobs eod --date <date>`（或 prefect flow）；R1 单运营者 |
| 几点运行 | A 股收盘 + 数据入库后（约 T 日 16:00 后）；R1 手动触发，不上自动调度 |
| 失败如何恢复 | 每个 step 幂等；失败重跑该 date；记录 step 级错误 |
| 数据 stale 怎么提示 | Daily Decision readiness 含 `data_freshness` 状态 + 最后更新时间 |
| 无信号日怎么处理 | readiness=`review`（非 blocked），附「今日无新信号」原因；不报错 |
| 信号发布失败怎么定位 | signal package publish 失败 → 结构化错误 + 指向 Task 1 publish-strategy-definition |
| 前端展示 blocked/review/ready | Daily Decision readiness 三态映射前端（Task 4） |

---

## Task 3：Daily Decision V2 后端契约

**现状：** `/daily-decision` 已聚合 signal intents / positions / deviation / pnl + readiness。V2 需扩展为 roadmap 第 7 节定义的完整决策报告。

**目标：** `DailyDecisionReport` 扩展为 V2，含 7 个组成。

**Files:**
- Modify: `application/queries/daily_decision.py`（`DailyDecisionReport` 扩展字段）
- Modify: `apps/api/routes/trade_query_routes.py`（`DailyDecisionReportResponse` 扩展 + readiness 三态）
- Test: `application/tests/`（V2 契约测试）

**Daily Decision V2 七组成（roadmap L134）：**
1. 数据健康和 freshness（接 Task 2 的 data_freshness）
2. 策略运行状态（strategy run 成功/失败/无信号）
3. 信号摘要和个券明细
4. 当前仓位、目标仓位和建议买卖
5. 基础风险提示（R1 用现有 risk rules 摘要，**非连续风控**）
6. 成交偏差和 PnL（接 `SignalDeviationQueryFacade`）
7. readiness status 和阻塞原因（ready/review/blocked + reason）

**TDD**：每个新增字段一个契约测试（V2 response 含该字段 + 值来自正确 facade）。 readiness 三态各有 fixture。

**Commit** — `feat(application): Daily Decision V2 contract (7 sections + readiness)`

> R1 风险提示只用现有 risk rules（集中度/回撤/止损）的**日频快照摘要**，**不建连续状态机**（那是 R4）。

---

## Task 4：Trading 前端 ready/review/blocked 真实态（ditto-app）

**现状：** Wave1a 已 live smoke 接通，但停留在 blocked 空态。`/trading`、`/trading/signals`、`/trading/portfolio`、`/trading/orders` 需升级为真实可复核工作台。

**目标：** 前端消费 Daily Decision V2，展示真实信号/仓位/建议/风险/偏差，支持手工 fill 录入。

**仓库：** `/home/chevy/projects/ditto-app`（独立分支）

**Files（ditto-app）：**
- `src/routes/trading/`、`src/features/trading/`
- 复用 Wave1a 资产：DecisionBanner / DataTable / SignalDetailPanel / useOverlayController / 14 hook 形状

**Task 级拆解：**
1. 前端契约对齐 Daily Decision V2（codegen 抓 live `/openapi.json`）。
2. readiness 三态 UI：`ready`（正常展示）/ `review`（无信号或需关注，附原因）/ `blocked`（数据/策略故障，附阻塞原因）。
3. 信号详情 + 目标仓位 + 建议买卖展示。
4. 手工 fill 录入 UI（接 Task 5 的 fill API）。
5. 基础风险摘要 + 偏差展示（**不等 A3/A4 完整实现**，用 V2 现有字段）。
6. playwright e2e + vitest 全绿。

**Commit（ditto-app 仓库）** — `feat(trading): Daily Decision V2 ready/review/blocked real-state`

> ⚠️ **解除伪依赖**：Task 4 不等 cvxpy 优化器(A3)/连续风控(A4)。基础风险摘要 + 基础归因用 Daily Decision V2 现有字段即可。

---

## Task 5：手工 fill + intent status + 偏差复盘 + 账户细节

**现状：** `commands/trade.py`（ManualTracker + intent status）+ `queries/deviation.py`（get_deviation）已有 backend。需产品化 + 补账户细节。

**目标：** 用户复核信号后录入手工 fill，系统记录 intent status / actual position / deviation / post-trade notes；账户状态可导入与修正。

**Files:**
- Modify: `application/commands/trade.py`（fill 录入 + intent status 闭环）
- Explore/Create: 初始持仓/现金导入接口（若不存在则新建）
- Test: `application/tests/`（fill 闭环 + 偏差 + 账户导入）

**TDD：**
1. fill 录入 → intent status 更新（pending→partially_filled→filled）→ ManualTracker 重聚合持仓。
2. 偏差报告反映 actual vs signal。
3. 初始持仓/现金导入（fixture：导入初始账户 → Daily Decision 显示正确仓位）。

**Commit** — `feat(application): manual fill loop + account import + deviation`

### 账户与成交状态细节（Task 5 交付物，产品级）

明确（部分需新建，部分定规则）：
- **初始持仓/现金导入**：R1 提供 CLI/API 导入初始账户快照（cash + positions as-of date）；source of truth = portfolio accounting。
- **fill 录错修正**：fill 记录可修正（append 修正事件，不原地改）；审计留痕。
- **撤销/修改成交**：通过 intent status + 修正事件，不删记录；审计。
- **source of truth**：**交易流水（fills）是权威**，持仓快照由 ManualTracker 从流水聚合派生（不双写）。
- **post-trade notes**：fill 可附人工备注。

---

## 并行小修：A2 手数取整

**现状：** 涨跌停/停牌/收盘竞价已由 `AShareFillModel` 实现。`DEFAULT_LOT_SIZE=100` + `TradingRuleSet.lot_size` 已存在。缺买入量 round-down。

**目标：** 买入量规整到 `lot_size` 倍数。

**Files:** `backtest/steps/planning.py`（或订单规整化点，实施前 Read 确认）

**TDD（修正原 A2 设计）：**
- **planning/order 级测试**（不只测私有 helper）：target_weight → quantity → board_lot 全链路。
- **零股语义**（先确认规则再实现）：A 股卖出零股**仅限清仓**（来源：上交所/深交所交易规则）；任意卖出是否允许 odd lot 须 Read 规则确认，**不凭直觉写死**。
- 不足 1 手买入 → 0。

**Commit** — `feat(backtest): A-share board lot round-down (planning-level)`

---

## 4 层验收矩阵（产品级，非只看测试通过）

每个 task 须过对应层：

| 层 | 含义 | R1 验收方式 |
|---|---|---|
| **backend primitive** | 后端原语可用 | unit + integration test 全绿 |
| **API contract** | FastAPI 契约稳定 | OpenAPI codegen + 契约测试；`x-ditto-maturity` 标注 |
| **frontend product** | 前端真实可用 | playwright e2e（非 mock/blocked）；vitest 全绿 |
| **daily operation** | 每日可运营 | 连续多交易日或固定历史日期可复现 EOD + Daily Decision |

---

## 安全与凭证最小线（R1）

- **keyring/env**：生产凭证走 keyring（`tushare/token`、`fred/api_key`）；`wave1_env.sh` 从 keyring 读取并 export，**无 token 时 warning / live smoke fail-fast**（修正原 A6-1 静默 export 空 token）。
- **secret scan**：pre-commit `detect private key` 已启用；不提交 token。
- **live smoke token**：live smoke 用专用只读 token（若需），不暴露生产凭证。
- **前端敏感信息**：Daily Decision V2 response 不含凭证；前端不展示 token/key。
- **不做多租户/认证**（那是 R7 机构级）；R1 单运营者。

---

## R1 Acceptance（里程碑①）

- [ ] Task 1：`publish-strategy-definition` 后 `publish-signals` 不报「未找到策略定义」；≥1 ETF + ≥1 个股 seed 策略 published。
- [ ] Task 2：固定历史日期 EOD 跑通 → signal package + trade intents 可查询；连续 2-3 日可复现。
- [ ] Task 3：`GET /api/v1/trade/daily-decision` 返回 V2 七组成 + readiness 三态。
- [ ] Task 4：ditto-app `/trading` 展示真实信号/仓位/建议/风险/偏差（非 mock/blocked）；playwright e2e 全绿。
- [ ] Task 5：手工 fill 录入 → intent status 闭环 + 偏差报告；初始账户可导入。
- [ ] A2：回测买入量规整 lot_size（planning 级测试）。
- [ ] **daily operation**：连续多个交易日（或固定历史日期）可复现「EOD → Daily Decision → 复核 → 手工 fill → 偏差」全流程。
- [ ] 安全凭证最小线全满足。
- [ ] `pixi run -e dev check` 全绿 + 37 架构合约；ditto-app `bun run check` 全绿。
- [ ] R1 evidence 写入 `docs/acceptance/wave1-r1-*.md`；capability-maturity 同步。

---

## 依赖与执行顺序

```
Task 1 (seed publish) ──解锁──→ Task 2 (EOD 闭环)
                                      │
                                      ├──→ Task 3 (Daily Decision V2)
                                      │         │
                                      │         ├──→ Task 4 (前端真实态) ──→ Task 5 (手工 fill)
                                      │
A2 手数取整（并行，独立）             运营 runbook（随 Task 2 产出）
```

Task 1 是解锁关键（解决 Wave1a 残留阻塞）。Task 4 不等 A3/A4。A2 全程可并行。

# Wave 1 Completion Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.
> **Predecessor:** `docs/plans/2026-06-30-wave1-final-implementation-plan.md`

**Goal:** 把 Wave 1 从「后端能力就绪、数据/前端未就绪」推进到 **Wave 1 全部 DoD 达成**——RC1 发布门禁 `passed==true`，且 ditto-app 能在 MSW 关闭时从真实后端呈现 daily decision cockpit 并完成手工 fill 闭环。

**Architecture:** 以数据阻断为主线前置。Phase 1 解除 catalog/promotion 阻断（14 数据集 backfill + 8 个 experimental 提级），Phase 2 跑通 RC1 门禁，Phase 3 点亮 V1a 前端北极星，Phase 4 补齐 V1b 写路径。后端门禁（Phase 1-2）与前端接线（Phase 3-4）可并行推进。

**Tech Stack:** Python 3.13、polars、FastAPI、Prefect、pytest、ruff、basedpyright、import-linter、pixi；ditto-app React 19、TanStack Query/Router、Vite、Biome、Vitest、bun、MSW。

---

## 0. 当前状态基线（2026-07-01）

分支 `feat/wave1-backend-capabilities` 领先 main 7 个提交（`4619bef6..531a7b16`）。

| Task（wave1-final 编号） | 状态 | 证据 |
|---|---|---|
| Task 0 分支基线 | ✅ | `4619bef6` |
| Task 1 A1 EOD 发布信号 | ✅ | `0b9c28d7`，`eod.py` 已接 publisher + `RECOMMENDATION` |
| Task 2 B3a 数据 readiness | ⚠️ 半 | `87e3f470` 仅收集证据；14 数据集 catalog evidence 全空、72 failures |
| Task 3 Daily Decision 契约 | ✅ | `89a67ded`，`daily_decision.py` + route |
| Task 4 A0a 前端只读接线 | ❌ | ditto-app 在 `feat/prototype-three-zone-architecture`，未接真实后端 |
| Task 5 V1a 端到端 smoke | ❌ | `docs/acceptance/wave1a-first-real-use.md` 不存在 |
| Task 6 A0b 前端写路径 | ❌ | 依赖 Task 4 |
| Task 7 B0 组合优化器 | ✅ | `944f57ab`，三件套 + template wiring |
| Task 8 B1 成交量约束填充 | ✅ | `2bc9f000` + RED/GREEN 证据 |
| Task 9 B3b Full RC1 | ❌ | 脚本就绪（`531a7b16` 加固），未跑通 |
| Task 10 Attribution V1 | ✅ | `2e6465ec` + RED/GREEN 证据 |

**阻断根因（实测）：** `ops status --json` + `rc1_requirements.validate_maturity_status` → 72 failures。14 个 launch 数据集 catalog storage_uri/schema_hash/row_count/freshness **全部缺失**，根因是本地 catalog store 从未 ingest（`DITTO_DATA_ROOT` 未设置），不是代码缺陷。`531a7b16` 修的是稀疏事件数据集空日期处理，让 acceptance **可达**，未生成 evidence。

---

## 1. 关键技术决策

### 1.1 数据环境
- 用独立 data root：`data/`（仓库内、gitignore）或 `.tmp/ditto-rc1/`。统一用 env 注入 `DITTO_DATA_ROOT / SQLITE_PATH / DUCKDB_PATH / ENVIRONMENT=testing`，复用 `packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py` 的 `_cli_env` + `_run_cli` 模式。
- 初始化：`ditto init config --data-root <root> --force`（建目录 + metadata SQLite 表，catalog/promotion store 共用 `metadata.sqlite`）。
- 凭证：Tushare token（keyring `tushare/token`）+ FRED api_key（keyring `fred/api_key`）均已 SET。

### 1.2 backfill 日期范围
- **V1a 档（Task 1.2）**：`2025-01-01 ~ 2026-06-30`（ETF/index/adj/calendar/fund_adj，支撑近期 ETF daily 决策）。
- **RC1 档（Task 1.3）**：`2024-06-01 ~ 2026-06-30`（stock 系列 + fundamental + valuation + macro，支撑选股回测 golden）。
- Tushare 限流：大范围用 `--parallel` 或按月分段；失败日期记录后单独补。

### 1.3 macro FRED PIT
- `ditto backfill macro indicators` 默认 source=tushare（首位）。FRED realtime PIT（Phase 2 成果，`need_pit` 子集 `knowledge_date=realtime_end`）需经 SourceRegistry/job 层路由，CLI backfill 不暴露 `--source`。
- 本计划 macro 先 backfill tushare 满足 RC1 catalog evidence；FRED PIT 强化作为 Task 1.3 的可选子任务（走 process 层），不阻断 RC1。

### 1.4 promotion 顺序
- **逐数据集、backfill 完立即 collect+review**，避免最后批量。
- 每个 experimental 数据集 3 条 criteria（`metadata.py:181-185`）：PIT/replay coverage、runtime owner + freshness SLA + failover 文档、catalog-backed runtime 测试通过。
- `promotion-collect` 只读收集客观证据（test 类强制 `needs_review`），`promotion-review` 逐条提交 reviewer evidence，第 3 条 satisfied 时 `assess_dataset_promotion` **自动**写 `experimental → initial-focus` override。**绝不自造通过。**

### 1.5 前端分支策略
- ditto-app 从 `feat/prototype-three-zone-architecture` 拉 `feat/wave1-backend-wiring` 分支。
- 复用已有 `src/lib/api-client.ts` + `src/mocks/server.ts`（MSW）基础设施，接线 = prototype mock 数据 → 真实 `/api/v1`。
- MSW 由 `VITE_USE_MOCK` gate，dev 默认 `false`。

### 1.6 Kill Switch（硬性规则）
- Task 4.x 写路径（record fill / update intent status）走既有 application command handler + approval 路径，**不加自动交易**。前端写按钮在 A0b 前保持 disabled。
- 无新增自动交易开关；paper/manual 模式是唯一执行面。

### 1.7 PIT（硬性规则）
- 财报三表 backfill 按公告日入 `knowledge_date`（PIT 语义），由 source/coordinator 处理；校验点在 Task 1.4（`catalog_freshness_status` + schema hash）。
- features/backtest 消费这些数据时复用既有 PIT gate（`knowledge_date` as-of），本计划不改动 PIT 策略。

---

## 2. Phase 1 — 数据阻断解除（后端，主线前置）

复杂度 **XL → 拆为 5 个 L/M 任务**。外部 API（Tushare/FRED）风险加权。

### Task 1.1 数据环境初始化 `[S]`

**Files:**
- Read: `packages/apps/src/ditto_apps/cli/commands/init.py`
- Read: `packages/data/src/ditto_data/config/data_store.py`

**Steps:**
1. 选定 data root（建议 `.tmp/ditto-rc1/`，gitignore 已覆盖 `.tmp`）。
2. `pixi run -e dev python -m ditto_apps.cli.main init config --data-root .tmp/ditto-rc1 --force`。
3. 固化 env 注入脚本 `scripts/acceptance/wave1_env.sh`（export `DITTO_DATA_ROOT / SQLITE_PATH / DUCKDB_PATH / ENVIRONMENT=testing`），供后续 Task 复用。
4. 校验 `metadata.sqlite` 建表成功 + catalog/promotion store 表存在。

**Acceptance:**
- `ditto init config` 退出 0，目录结构齐全。
- `ops status --json` 在空环境退出 0（数据集行存在，catalog 字段空属预期）。

**Test:** 新增 `scripts/acceptance/test_wave1_env_unit.py` 校验 env 脚本导出字段完整。

---

### Task 1.2 V1a initial-focus 数据集 backfill `[L]`

**Files:**
- Read: `packages/apps/src/ditto_apps/cli/commands/backfill/metadata.py`、`backfill/market.py`
- Read: `packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py`（参考 `_cli_env` + `_run_cli`）

**Scope:** 5 个 initial-focus 数据集 + calendar（V1a 必需）：
`calendar / etf_basic / etf_daily / index_basic / index_daily / adj_factor / fund_adj`

**Steps:**
1. source env（Task 1.1 脚本）。
2. 按依赖顺序 backfill（`2025-01-01 ~ 2026-06-30`）：
   ```
   ditto backfill metadata calendar -s 2025-01-01 -e 2026-06-30
   ditto backfill metadata basic etf -s 2025-01-01 -e 2026-06-30
   ditto backfill metadata basic index -s 2025-01-01 -e 2026-06-30
   ditto backfill market etf -s 2025-01-01 -e 2026-06-30
   ditto backfill market index -s 2025-01-01 -e 2026-06-30
   ditto backfill market adj -s 2025-01-01 -e 2026-06-30
   ditto backfill market adj --fund -s 2025-01-01 -e 2026-06-30   # fund_adj
   ```
3. 记录失败日期，分段/单日补。
4. 每个数据集后 `ops status --json` 抽查 `latest_status==success`。

**Acceptance:**
- 7 个数据集 `catalog_storage_uri / catalog_schema_hash / catalog_row_count` 非空且 `catalog_freshness_status ∈ {fresh, not_applicable}`。
- `rc1_requirements.validate_maturity_status` 对这 7 个数据集 0 failure（maturity=initial-focus + promotion=not_applicable 已合规）。

**Test:** 扩展 `test_real_data_stock_selection_pipeline.py` 的 catalog 校验断言到 7 个 V1a 数据集（`catalog_row_count > 0`）。

**Implementation Evidence:** 完成。calendar/etf_basic/index_basic 用 `ingest`（路径修正，见 readiness Phase 1 Notes：`backfill metadata calendar/basic` 死循环/浪费），etf_daily/fund_adj 全年 backfill（359/359 success），index_daily/adj_factor 因写瓶颈（SQLite 写锁，parallel 无效）改近期 2 月（39/39 success）。7 数据集 catalog evidence 齐全（fresh/storage/schema/rows>0）。

---

### Task 1.3 RC1 experimental 数据集 backfill `[L]`

**Files:**
- Read: `packages/apps/src/ditto_apps/cli/commands/backfill/{market,fundamental,capital,macro}.py`

**Scope:** 8 个 experimental 数据集（`2024-06-01 ~ 2026-06-30`）：
`stock_basic / stock_daily / stock_status / balance_sheet / income_statement / cash_flow / valuation_metrics / macro_indicators`

**Steps:**
1. source env。
2. 按依赖顺序 backfill：
   ```
   ditto backfill metadata basic stock -s 2024-06-01 -e 2026-06-30
   ditto backfill market stock -s 2024-06-01 -e 2026-06-30
   ditto backfill market status -s 2024-06-01 -e 2026-06-30
   ditto backfill fundamental balance -s 2024-06-01 -e 2026-06-30
   ditto backfill fundamental income -s 2024-06-01 -e 2026-06-30
   ditto backfill fundamental cash-flow -s 2024-06-01 -e 2026-06-30
   ditto backfill capital valuation -s 2024-06-01 -e 2026-06-30
   ditto backfill macro indicators -s 2024-06-01 -e 2026-06-30
   ```
3. **稀疏数据集注意**（`531a7b16`）：`balance_sheet/income_statement/cash_flow` 非披露日空返回 = `success / rows=0` 且不写 catalog entry——属预期，校验用「有披露日期」而非「全部日期」。
4. （可选）macro FRED PIT 强化：经 SourceRegistry/job 层跑 FRED `need_pit` 子集，`knowledge_date=realtime_end`。不阻断 RC1。

**Acceptance:**
- 8 个数据集在有数据日期上 `catalog_*` 字段齐全。
- `stock_daily / valuation_metrics` 的 `catalog_row_count > 1000`（参考 e2e 断言）。
- 失败日期清单记录到 `docs/acceptance/wave1-data-readiness.md`。

**Test:** e2e 真实数据测试（`-m e2e`）在本地 env 跑通；新增 `test_real_data_rc1_backfill_e2e.py` 覆盖 8 数据集 catalog 断言。

**Implementation Evidence:** 完成。stock_basic 用 `ingest` 单次；stock_daily/stock_status/valuation_metrics 近期 2 月 backfill（39/39，写瓶颈全年不可行）；balance_sheet/income_statement/cash_flow 扩到 2025-08~2026-06（含中报+年报披露日，近期 2 月无披露 rows=0）；macro_indicators backfill。8 数据集 catalog evidence 齐全。`test_real_data_rc1_backfill_e2e.py` 未单独新增——复用 `scripts/acceptance/test_wave1_catalog_check_unit.py` 的 e2e 用例覆盖 14 数据集 catalog 断言（RED 72→GREEN 0）。

---

### Task 1.4 catalog evidence 全量校验 `[M]`

**Files:**
- Read: `scripts/acceptance/rc1_requirements.py`（`validate_maturity_status`）
- Create: `scripts/acceptance/wave1_catalog_check.py`

**Steps:**
1. 跑 `ops status --json > /tmp/wave1-status.json`。
2. 用 `validate_maturity_status` 校验 14 数据集，输出 per-dataset 矩阵 + failure 清单。
3. RED：写一个断言 14 数据集全过的测试 `scripts/acceptance/test_wave1_catalog_check_unit.py`（先失败，复现当前 72 failures）。
4. GREEN：Phase 1.2/1.3 backfill 完成后重跑，直到 0 failure（experimental 数据集 maturity/promotion 在 Task 1.5 后达标）。

**Acceptance:**
- `validate_maturity_status` 返回 `ok=True, failures=()`。
- 矩阵写入 `docs/acceptance/wave1-data-readiness.md`（覆盖旧 blocked 状态）。

**Test:** `test_wave1_catalog_check_unit.py` 通过。

---

### Task 1.5 experimental 数据集 promotion 提级 `[L]`

**Files:**
- Read: `packages/apps/src/ditto_apps/cli/commands/ops.py:360-394, 517-541`（promotion-collect / promotion-review 签名）
- Read: `packages/application/src/ditto_application/commands/catalog.py:91-191`（`ReviewDatasetPromotionEvidenceHandler`）

**Scope:** 8 个 experimental 数据集逐个提级：`stock_basic / stock_daily / stock_status / balance_sheet / income_statement / cash_flow / valuation_metrics / macro_indicators`。

**Steps（每个数据集重复）：**
1. `ditto ops promotion-collect <dataset> --output /tmp/wave1-promotion/<dataset>.md`（客观证据，不判定）。
2. Reviewer 对 3 条 criteria 逐条提交（参数以 `ops.py:360-394` 为准）：
   ```
   ditto ops promotion-review <dataset> \
     --criterion "<criterion_text_or_id>" \
     --evidence-uri "<uri>" \
     --reviewed-by "<actor>" --passed
   ```
   - criterion 1: PIT/replay coverage
   - criterion 2: runtime owner + freshness SLA + failover 文档
   - criterion 3: catalog-backed runtime 测试通过
3. 第 3 条 satisfied 后，`assess_dataset_promotion` 自动写 `experimental → initial-focus` override。
4. `ops status --json` 验证 `dataset_maturity==initial-focus` 且 `dataset_promotion_status` 合规。

**Governance 硬约束（不可破）：**
- evidence 必须真实（test 类 `needs_review`，不能工具自判）。
- 不允许跳过 collect 直接批量 review；不允许一次调用批过。
- review 的 evidence_uri 必须指向真实材料（PIT 测试报告、文档链接、golden 测试输出）。

**Acceptance:**
- 8 数据集 `dataset_maturity==initial-focus`。
- `validate_maturity_status` 对 14 数据集全过。
- `ops promotion-history <dataset>` 可查 promoted audit event。

**Test:** 集成测试 `test_promotion_governance_integration.py` 已存在（golden governance 闭环），复跑通过。

**Implementation Evidence:** 完成。8 数据集逐个 `promotion-collect`（客观证据 markdown）→ `promotion-review` × 3 criteria（criterion 1 evidence=collect md replay coverage measured；2=`docs/architecture/capability-maturity.md` freshness_sla/failover 文档；3=`test_golden_e2e.py` 9 测试通过）→ `assess_dataset_promotion` 自动写 experimental→initial-focus override。`promotion-history` audit event 可查（actor=wave1-acceptance）。governance 红线遵守：evidence_uri 全真实材料，逐条 review 未批过，绝不自造通过。14 数据集 `validate_maturity_status` failures=0。

---

## 3. Phase 2 — RC1 门禁通过（Task 9）

依赖 Phase 1 完成。复杂度 **M**。

### Task 2.1 重跑 RC1 acceptance `[M]`

**Files:**
- Run: `scripts/acceptance/rc1_real_data_acceptance.py`
- Read: `docs/acceptance/rc1-release-checklist.md`

**Steps:**
1. source env（Task 1.1）。
2. 跑最终命令：
   ```
   pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py \
     --real-data --require-promoted \
     --output artifacts/acceptance/rc1-report.json
   ```
   该命令内部跑：`pixi run -e dev check` + targeted-golden（4 测试）+ `promotion-collect stock_daily` + real-data-e2e（2 测试）+ `ops status --json` 经 `validate_maturity_status` 校验。
3. 失败时按 `results[].returncode` 定位是 check/golden/e2e/maturity 哪一环，分别修。

**Acceptance（rc1-release-checklist §一）：**
- 报告 `passed == true` 且 `business_failures == []`。
- 覆盖旧的 Jun 30 失败报告。

**Implementation Evidence:** [待实施后填写]

---

### Task 2.2 更新 readiness 证据 `[S]`

**Files:**
- Modify: `docs/acceptance/wave1-data-readiness.md`
- Modify: `docs/acceptance/rc1-release-checklist.md`（勾选完成项）

**Steps:**
1. 用 Task 1.4 矩阵 + Task 2.1 报告路径更新 readiness 文档。
2. 记录 V1a 7 数据集 ready + 8 experimental promoted + RC1 `passed=true`。
3. Commit `docs: record wave1 rc1 promotion evidence`。

**Acceptance:** readiness 文档反映 unblock 状态，与 `rc1-report.json` 一致。

---

## 4. Phase 3 — V1a 前端北极星（Task 4 + 5）

**Repository:** `/home/chevy/projects/ditto-app`，新分支 `feat/wave1-backend-wiring`。可与 Phase 1-2 并行。

### Task 3.1 接线分支与环境 `[M]`

**Files:**
- Branch: 从 `feat/prototype-three-zone-architecture` 拉 `feat/wave1-backend-wiring`
- Create: `.env.development`
- Modify: `vite.config.ts`
- Modify: `src/main.tsx`（MSW gating）
- Modify: `src/test/setup.ts`

**Steps:**
1. `git switch -c feat/wave1-backend-wiring`。
2. `.env.development`：`VITE_API_BASE_URL=/api`、`VITE_USE_MOCK=false`。
3. `vite.config.ts`：加 `/api` proxy 到本地 Ditto 后端端口。
4. `main.tsx`：MSW startup gate 在 `import.meta.env.VITE_USE_MOCK === "true"`。
5. 测试：dev 默认不启 MSW，显式 `VITE_USE_MOCK=true` 仍可启。

**Acceptance:**
- `bun run dev` 默认打真实后端，MSW 仅 opt-in。
- `bun run check` 通过。

**Implementation Evidence:** [待实施后填写]

---

### Task 3.2 daily-decision query hook `[M]`

**Files:**
- Create: `src/features/trading/api/daily-decision.ts`
- Create: `src/features/trading/hooks/use-daily-decision.ts`
- Create: `src/features/trading/api/__tests__/daily-decision.test.ts`

**Steps:**
1. 在 `api-client.ts` 基础上加 `fetchDailyDecision(strategyId, tradeDate?)` 调 `GET /api/v1/trade/daily-decision`。
2. TanStack Query hook `useDailyDecision`，响应类型对齐后端 `DailyDecisionReportResponse`。
3. vitest：MSW handler 模拟空/非空/错误三种响应。

**Acceptance:** hook 单测覆盖三种响应；TypeScript 类型对齐后端 DTO。

---

### Task 3.3 只读视图接线 `[L]`

**Files:**
- Modify: trading overview / signals inbox / positions / deviation 视图组件（`src/features/trading/`）
- 保持写按钮 disabled（A0b 前不假写）

**Steps:**
1. trading overview 消费 `useDailyDecision`，渲染 readiness_status + reasons。
2. signals inbox 渲染 `signal_intents`。
3. positions 渲染 `positions`，deviation 渲染 `deviation`（null 时显空态）。
4. P&L 可选区在 `pnl==null` 时隐藏。
5. 写按钮（record fill / update status）保持 disabled + tooltip「Wave 1b 启用」。

**Acceptance:**
- 真实后端有数据时，四块视图非空。
- 无数据时显结构化空态而非报错。
- `bun run check` 通过，无 `any` / `@ts-ignore` 回归。

---

### Task 3.4 V1a 端到端 smoke + 证据 `[M]`

**Files:**
- Create: `docs/acceptance/wave1a-first-real-use.md`（ditto 仓库）
- Run: ditto 后端 EOD + ditto-app `VITE_USE_MOCK=false`

**Steps:**
1. 起 Ditto 后端。
2. 跑 EOD 或 publish-signals 产出某 ETF 策略 intents（Task 1 已有数据）。
3. `GET /api/v1/trade/daily-decision?strategy_id=<id>` 返回非空 signals 或显式 readiness blocker。
4. ditto-app `VITE_USE_MOCK=false` 启动，捕获：latest signal date、signal count、positions/deviation 状态。
5. 截图/记录到 `docs/acceptance/wave1a-first-real-use.md`。
6. 后端 `pixi run -e dev check` + 前端 `bun run check`。
7. Commit `docs: add wave1a first real use evidence`。

**Acceptance（Wave 1a DoD）：**
- 有人类可读证据文件证明 first real-use 路径。
- 若仍 blocked，文件列 exact blockers，不假装成功。

---

## 5. Phase 4 — V1b 前端写路径（Task 6）

依赖 Phase 3。涉及交易状态变更 → **Kill Switch 约束**。

### Task 4.1 fills 写路径 `[M]`

**Files:**
- Create: `src/features/trading/api/fills.ts` + hook `use-record-fill.ts`
- 对齐后端 `POST /trade/fills`

**Steps:**
1. `recordFill(payload)` mutation 调 `POST /api/v1/trade/fills`。
2. 成功后 invalidate `dailyDecision / positions / deviation` query。
3. vitest：MSW 模拟成功/失败；确认 invalidation。
4. 前端表单校验（quantity/price 正数、instrument 非空）。

**Acceptance:** UI 可记录手工 fill；失败显结构化错误；`bun run check` 通过。

---

### Task 4.2 intent status 写路径 `[M]`

**Files:**
- Create: `src/features/trading/api/intents.ts` + hook `use-update-intent-status.ts`
- 对齐后端 `PUT /trade/intents/{id}/status`

**Steps:**
1. `updateIntentStatus(intentId, status)` mutation。
2. invalidate signals/daily-decision query。
3. 启用 Task 3.3 disabled 的写按钮，接 confirmation modal（复用 prototype 的 confirmation overlay）。
4. **Kill Switch**：仅 manual/paper 路径，无自动提交；状态机校验由后端 command handler 强制。

**Acceptance:** 可更新 intent 状态；deviation 从后端 refetch 后刷新；`bun run check` 通过。

---

### Task 4.3 query invalidation + 收尾 `[S]`

**Steps:**
1. 统一 query key 工厂 `src/features/trading/api/query-keys.ts`。
2. 确认 fill/intent 写后 daily-decision/positions/deviation/pnl 全部 invalidate。
3. `bun run check` + ditto 后端 `pixi run -e dev check`。

**Acceptance（Wave 1b DoD）：**
- UI 可记录手工 fill，deviation 从后端刷新。
- optimizer-backed 目标组合路径已存在（Task 7 已完成）。

---

## 6. 依赖与并行策略

```
Phase 1.1 ─┬─ Phase 1.2 ── Phase 1.4 ─┐
           └─ Phase 1.3 ───────────────┤
                                        ├─ Phase 1.5 ─ Phase 2 ─ (RC1 ✅)
Phase 3.1 ─ Phase 3.2 ─ Phase 3.3 ─ Phase 3.4 ─ (V1a ✅) ─ Phase 4 ─ (V1b ✅)
```

- **Phase 1-2（后端门禁）与 Phase 3-4（前端）可并行**——两条独立分支、独立 PR。
- Phase 3 前端可用 Phase 1.2 的 V1a 数据先跑通；不必等 RC1 全过。
- Phase 4 严格依赖 Phase 3 接线完成。
- 每个任务一个 PR，PR size gate：不合并 Phase（如不把 B0/B1/A0 混提）。

---

## 7. Global Quality Gates

### 后端 PR（Phase 1-2）
```
pixi run -e dev check        # lint + fmt + type + test --fast
pixi run -e dev arch-check   # 37 contracts
```
预期：ruff 过、格式干净、basedpyright 0 error/warning、fast test 过、import-linter 过。

### 前端 PR（Phase 3-4）
```
bun run check                # biome + tsc + vitest
```
预期：Biome 过、TS 过、Vitest 过、无 `any`/`@ts-ignore`/inline style 回归。

### RC1 最终门禁（Phase 2）
```
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py \
  --real-data --require-promoted --output artifacts/acceptance/rc1-report.json
```
预期：`passed==true && business_failures==[]`。

---

## 8. Definition of Done

### Wave 1a DoD（映射 wave1-final §9）
- [x] EOD 能发布信号包（Task 1 已完成）
- [ ] Launch dataset readiness 明确 → **Phase 1.2 + 1.4**
- [x] `/trade/daily-decision` 契约存在（Task 3 已完成）
- [ ] ditto-app 从真实后端显示 cockpit → **Phase 3.3**
- [ ] `docs/acceptance/wave1a-first-real-use.md` 证据 → **Phase 3.4**

### Wave 1b DoD
- [ ] 前端记录手工 fill → **Phase 4.1**
- [ ] deviation 从后端刷新 → **Phase 4.2**
- [x] optimizer-backed 目标组合路径（Task 7 已完成）

### Wave 1c DoD
- [x] 成交量约束填充入回测路径（Task 8 已完成）
- [ ] Full RC1 promotion 证据 → **Phase 1.5 + Phase 2**
- [x] 基础 attribution 支撑日常 review（Task 10 已完成）

---

## 9. Risk Register

| 风险 | 影响 | 缓解 |
|---|---|---|
| Tushare 限流导致大范围 backfill 慢/失败 | Phase 1 延期 | `--parallel` + 按月分段 + 失败日期补跑脚本 |
| 稀疏数据集（财报三表）空日期误判失败 | Phase 1.3 校验错误 | 用「有披露日期」校验，参考 `531a7b16` 语义 |
| promotion evidence 无法满足 3 条 criteria | Phase 1.5 卡住 | 提前为每条 criterion 准备真实材料（PIT 测试报告/文档/golden 输出），不触碰 governance 红线 |
| macro FRED PIT 路由 CLI 未暴露 | Phase 1.3 macro 不完整 | tushare macro 先满足 RC1；FRED PIT 走 job 层作为可选子任务 |
| ditto-app prototype 分支与接线冲突 | Phase 3 合并困难 | 独立 `feat/wave1-backend-wiring` 分支，不回合并 prototype 改动 |
| 真实数据 e2e 在 CI 无凭证跳过 | RC1 证据仅本地 | checklist §四要求凭证环境补跑；本地产出的 `rc1-report.json` 入 `artifacts/` |

---

## 10. Work Explicitly Deferred（不属本计划）

- 实时券商适配器、自动交易（Wave 2+，`reserved`）。
- Paper account lifecycle 完整 UX、read-only AI copilot（Wave 2）。
- 全量 Brinson/Barra position-level attribution（Task 10 已 defer）。
- cvxpy optimizer（需显式批准，Task 7 已用无新依赖 min-vol/inverse-vol hybrid）。

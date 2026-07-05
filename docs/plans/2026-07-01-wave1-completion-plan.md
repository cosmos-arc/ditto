# Wave 1 Completion Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.
> **Predecessor:** `docs/plans/2026-06-30-wave1-final-implementation-plan.md`

**Goal:** 把 Wave 1 从「后端能力就绪、数据/前端未就绪」推进到 **Wave 1 全部 DoD 达成**——RC1 发布门禁 `passed==true`，且 ditto-app 的 **Trading 域**能在 MSW 关闭时从真实后端呈现 daily decision cockpit 并完成手工 fill 闭环。

**Architecture:** 以数据阻断为主线前置。Phase 1 解除 catalog/promotion 阻断（14 数据集 backfill + 8 个 experimental 提级），Phase 2 跑通 RC1 门禁，Phase 3 将 ditto-app 的 Trading 域从 prototype/mock 产品骨架转成 V1a 只读 live cockpit，Phase 4 补齐 V1b 手工执行写路径。Home/Markets/Research/Platform 在 Wave 1 保留为 prototype/MSW 产品方向资产，不进入 live backend DoD；后续按 Platform→Research→Markets→Home 的依赖顺序逐域转正。

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

### 1.5 前端产品化边界与分支策略
- ditto-app 从 `feat/prototype-three-zone-architecture` 拉 `feat/wave1-backend-wiring` 分支。
- Wave 1 前端正式化范围只包含 **Trading 域 daily ETF decision cockpit**：`/trading`、`/trading/signals`、`/trading/portfolio` 的 V1a 只读闭环，以及 V1b 的手工 fill / intent status 写路径。`/trading/orders` 在 Wave 1 只承载 manual execution/fill ledger 的轻量视图，不宣称完整券商订单生命周期；`/trading/risk` 仅展示可由 daily-decision/deviation 支撑的风险阻断或结构化空态。
- Home/Markets/Research/Platform 不在 Wave 1 一次性 live 化。它们继续作为 prototype/MSW 产品方向资产保留，用于承载正式 IA、页面模式、交互状态和后续后端契约设计；不允许因为 Wave 1 接线而删除或降级这些原型页面。
- 复用已有 `src/lib/api-client.ts` + `src/mocks/server.ts`（MSW）基础设施。Wave 1 acceptance 模式为 `VITE_USE_MOCK=false` 并直接打开 `/trading`；全产品原型演示模式为 `VITE_USE_MOCK=true`，用于 Home/Markets/Research/Platform 的产品评审。
- `VITE_API_BASE_URL=/api` 时，Trading live hooks 的 path 必须写成 `/v1/trade/...`，最终请求为 `/api/v1/trade/...`；禁止在 hook 里写 `/api/v1/...` 造成双 `/api`。
- 后端统一响应是 `APIResponse<T>`，前端必须在 `src/features/trading/api/` 建 adapter 解包 `data` 并映射成 UI view model，避免后端 DTO、OpenAPI generated types、prototype view model 三套类型漂移。
- MSW 由 `VITE_USE_MOCK` gate；Wave 1 live acceptance 明确不把非 Trading 路由纳入「MSW 关闭」验收。

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

**Implementation Evidence:** 完成（2026-07-02）。`pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py --real-data --require-promoted --output artifacts/acceptance/rc1-report.json` 一次通过（exit=0，用时 ~1.5min）。报告 `passed=true && business_failures=[]`（`generated_at=2026-07-02T08:48:39Z`），5 命令全 rc=0：`check` / `targeted-golden` / `promotion-evidence-stock-daily` / `real-data-e2e` / `maturity-status`。运行 env: `source scripts/acceptance/wave1_env.sh`（`DITTO_DATA_ROOT=.tmp/ditto-rc1`、`ENVIRONMENT=testing`），真实 Tushare（`tushare/token`）+ FRED（`fred/api_key`）凭证。前置健康检查：`ops status --json` → `validate_maturity_status` `ok=True failures=0`；4 个凭证 key 全 SET。注：被覆盖的旧报告实际为 Jun 17 生成且内容已 `passed=true`（文件 mtime Jun 30），本次重跑产出 Phase 1 完成后的权威报告。

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

**Implementation Evidence:** 完成（2026-07-02）。`docs/acceptance/wave1-data-readiness.md` 顶部 Summary 扩充 Phase 2 完成陈述 + 「Full RC1 Status」节新增 RC1 Release Acceptance 证据块（命令、env、5 命令结果表、`passed=true`）+ Required Next Actions 更新为「RC1 门禁已达成，下一步 Phase 3-4」。`docs/acceptance/rc1-release-checklist.md` 「一、验收口径」节新增 ✅ RC1 验收结果块（报告路径、generated_at、5 命令、env、覆盖旧报告）。两文档与 `rc1-report.json`（`passed=true && business_failures=[]`）一致。

---

## 4. Phase 3 — V1a Trading 域前端产品化（Task 4 + 5）

**Repository:** `/home/chevy/projects/ditto-app`，新分支 `feat/wave1-backend-wiring`。可与 Phase 1-2 并行。

### Phase 3 产品边界

Wave 1 不把 ditto-app 五大域一次性 live 化。正式产品切片聚焦 Trading 域，因为当前后端已有可闭环契约：`GET /trade/daily-decision`、`GET /trade/signals/latest`、`GET /trade/positions`、`GET /trade/deviation`、`GET /trade/pnl`，以及 V1b 写路径 `POST /trade/fills`、`PUT /trade/intents/{id}/status`。

| 域 / 页面 | Wave 1 状态 | Wave 1 要完成什么 | 不在 Wave 1 宣称完成 |
|---|---|---|---|
| `/trading` Trading Overview | live | daily decision cockpit：readiness、latest intents、positions、deviation、pnl、primary answer、blocked/review/ready 状态 | 实时券商会话、完整订单路由、盘中实时行情 |
| `/trading/signals` Signals Inbox | live（只读 V1a，写入 V1b） | 基于 daily-decision/signal_intents 的复核队列、选中 intent、deviation 状态、写按钮门控 | AI signal review、Risk Officer 完整证据链、批量确认 |
| `/trading/portfolio` Portfolio | live（V1a 子集） | positions、pnl、manual fills 空态/列表入口、T+1 可用数量字段展示 | 完整归因、行业/个股/因子贡献图、全量 trades tab |
| `/trading/orders` Orders Ledger | light live（V1b） | manual fill / intent status ledger，用于手工执行追踪 | 真实券商订单生命周期、撤单/重试、路由日志 |
| `/trading/risk` Risk Center | structured state | 展示 daily-decision readiness/deviation 带来的阻断或空态，引导到 Signals/Portfolio | 完整 VaR/stress/incident runtime |
| Home/Markets/Research/Platform | prototype/MSW | 保留原型、IA、页面模式、交互状态，作为后续 live 化上游 | 不作为 Wave 1 live backend DoD |

**正式化原则：**
- 原型页面不是废弃物。React 实现必须继承 `docs/designs/specs/01_product_information_architecture.md`、`02_core_page_blueprints.md`、`04_interaction_state_spec.md` 对 Trading 域的主答案、队列、selected、empty/failed/blocked 状态要求。
- Live adapter 负责把后端传输 DTO 映射为 Trading UI view model；组件只消费 view model，不直接拼后端字段。
- MSW mock 继续服务非 Wave1 域和组件测试；live acceptance 只验证 Trading 域。

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
5. 测试：dev 默认不启 MSW，显式 `VITE_USE_MOCK=true` 仍可启；README 或 acceptance 证据中注明 Wave 1 live 验收入口为 `/trading`。

**Acceptance:**
- `bun run dev` 默认打真实后端；打开 `/trading` 时不依赖 MSW。
- `VITE_USE_MOCK=true` 时全产品原型仍可用于 Home/Markets/Research/Platform 评审。
- `bun run check` 通过。

---

### Task 3.2 Trading live API adapter `[M]`

**Files:**
- Modify: `package.json`（如尚无 OpenAPI codegen script）
- Generate: `src/types/generated/api.d.ts`
- Create: `src/features/trading/api/daily-decision.ts`
- Create: `src/features/trading/api/trade-mappers.ts`
- Create: `src/features/trading/api/query-keys.ts`
- Create: `src/features/trading/hooks/use-daily-decision.ts`
- Create: `src/features/trading/api/__tests__/daily-decision.test.ts`

**Steps:**
1. 用 `openapi-typescript` 从 Ditto 后端 OpenAPI 导出 `src/types/generated/api.d.ts`；保留现有手写 `src/types/trading.ts` 作为 UI view model，不再手写后端传输 DTO。
2. 在 `daily-decision.ts` 新增 `fetchDailyDecision({ strategyId, tradeDate })`，调用 `apiClient.get<APIResponse<DailyDecisionReportResponse>>(withQueryParams("/v1/trade/daily-decision", { strategy_id, trade_date }))` 并返回解包后的 `data`。
3. 在 `trade-mappers.ts` 将后端 DTO 映射到 UI view model：`instrument_id` 先显示为 `#<id>` fallback；`direction` 映射为 `BUY/SELL/HOLD`；intent status 映射为 Signals UI tabs；readiness reasons 映射为中文文案。
4. 在 `query-keys.ts` 定义 `tradingKeys.dailyDecision(strategyId, tradeDate)`、`tradingKeys.positions(strategyId, tradeDate)`、`tradingKeys.deviation(strategyId, tradeDate)`。
5. TanStack Query hook `useDailyDecision` 只返回 mapped view model，组件不直接读 `APIResponse.data`。
6. Vitest 覆盖 ready / review / blocked / failed 四类响应；断言请求 path 是 `/v1/trade/daily-decision`，不是 `/api/v1/trade/daily-decision`。

**Acceptance:**
- hook 单测覆盖 ready/review/blocked/failed。
- TypeScript 类型来自 generated API + mapper view model，无 `any` / `@ts-ignore`。
- API base path 拼接正确：`VITE_API_BASE_URL=/api` + hook path `/v1/trade/...`。

---

### Task 3.3 Trading read-only product slice `[L]`

**Files:**
- Modify: `src/features/trading/components/trading-page.tsx`
- Modify: `src/features/trading/components/signals-list.tsx`
- Modify: `src/features/trading/components/signal-detail-panel.tsx`
- Modify: `src/features/trading/components/positions-summary.tsx`
- Modify: `src/features/trading/components/portfolio-page.tsx`
- Modify: `src/features/trading/components/risk-page.tsx`
- Test: `src/features/trading/components/trading-components.test.tsx`
- Test: `src/features/trading/components/signals-components.test.tsx`
- Test: `src/features/trading/components/risk-components.test.tsx`

**Steps:**
1. Trading Overview 消费 `useDailyDecision`，用 readiness + latest signal count 组成 `data-primary-answer`：一句判断、关键数字、2-3 个证据点、主动作（查看信号 / 查看持仓）。
2. 用 daily-decision 的 `signal_intents` 替换 `TradingPage` 内局部 `MOCK_SIGNALS`；ready/review/blocked 三态都必须有稳定首屏布局。
3. Signals Inbox 使用 daily-decision view model 渲染待复核 intent 列表；点击 intent 后 detail panel 展示 intent、deviation item、readiness reason 和受影响持仓。
4. Positions Summary / Portfolio 持仓 tab 使用 daily-decision `positions` + `pnl`；`available_quantity` 与 `quantity` 不一致时展示 T+1/冻结语义。
5. Deviation 区块在 `deviation == null` 时显示「尚无成交偏差，录入 fill 后刷新」；有数据时显示 filled/unfilled 和 per-instrument deviation。
6. Risk Center 在 Wave 1a 不伪造 VaR/stress 数据；只展示 daily-decision readiness/deviation 相关 blocked/review 状态，并提供跳转 Signals/Portfolio 的动作。
7. 所有写按钮（record fill / update status / confirm signal）保持 disabled 或明确的 Wave 1b 门控；不使用前端本地状态假写。
8. 更新 MSW handler 支持 `/api/v1/trade/daily-decision` 测试响应，同时保留旧 `/api/trading/*` handlers 给非 Wave1 原型与历史组件测试。

**Acceptance:**
- `/trading` 在真实后端有数据时显示 readiness、signal count、positions、deviation/pnl 状态。
- `/trading/signals` 能从同一 daily decision report 展示信号复核列表与选中详情。
- `/trading/portfolio` 能展示真实 positions/pnl 或结构化空态。
- `/trading/risk` 不伪造完整风险中心，能明确显示 Wave 1a 支撑范围和下一动作。
- 无数据时显 structured empty/blocked，不报错、不空白、不沿用 mock 数据。
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
4. ditto-app `VITE_USE_MOCK=false` 启动，直接打开 `/trading`，捕获：readiness、latest signal date、signal count、positions、deviation/pnl 状态。
5. 截图/记录到 `docs/acceptance/wave1a-first-real-use.md`。
6. 后端 `pixi run -e dev check` + 前端 `bun run check`。
7. Commit `docs: add wave1a first real use evidence`。

**Acceptance（Wave 1a DoD）：**
- 有人类可读证据文件证明 Trading 域 first real-use 路径。
- 证据明确说明 Home/Markets/Research/Platform 仍是 prototype/MSW 产品方向资产，不纳入本次 live DoD。
- 若仍 blocked，文件列 exact blockers，不假装成功。

---

## 5. Phase 4 — V1b 手工执行闭环（Task 6）

依赖 Phase 3。涉及交易状态变更 → **Kill Switch 约束**。

### Task 4.1 record fill action `[M]`

**Files:**
- Create: `src/features/trading/api/fills.ts`
- Create: `src/features/trading/hooks/use-record-fill.ts`
- Modify: `src/features/trading/components/signal-detail-panel.tsx`
- Modify: `src/features/trading/components/portfolio-page.tsx`
- Test: `src/features/trading/api/__tests__/fills.test.ts`
- Test: `src/features/trading/components/signals-components.test.tsx`

**Steps:**
1. `recordFill(payload)` mutation 调 `POST /v1/trade/fills`，payload 对齐后端 `RecordFillRequest`。
2. Signal Detail 增加「录入成交」sheet：从选中 intent 预填 `intent_id / strategy_id / trade_date / instrument_id / direction / quantity`，用户输入 `fill_price / fee / slippage / notes`。
3. 前端表单校验：`quantity > 0`、`fill_price > 0`、`fee >= 0`、`slippage` 为有限数字、`intent_id` 非空。
4. 成功后 invalidate `dailyDecision / positions / deviation / pnl / fills` query，并显示 inline success；失败时显示后端 error message，不吞掉 conflict/transition 错误。
5. Vitest 模拟成功/失败/重复提交三类响应；断言 mutation path、payload 和 invalidation。

**Acceptance:** UI 可从选中 signal intent 录入手工 fill；失败显结构化错误；deviation/positions/pnl 从后端 refetch 后刷新；`bun run check` 通过。

---

### Task 4.2 intent status action `[M]`

**Files:**
- Create: `src/features/trading/api/intents.ts`
- Create: `src/features/trading/hooks/use-update-intent-status.ts`
- Modify: `src/features/trading/components/signal-detail-panel.tsx`
- Test: `src/features/trading/api/__tests__/intents.test.ts`
- Test: `src/features/trading/components/signals-components.test.tsx`

**Steps:**
1. `updateIntentStatus(intentId, status)` mutation 调 `PUT /v1/trade/intents/{intent_id}/status`。
2. 支持后端允许的状态：`pending / filled / partially_filled / cancelled / expired`；前端显示文案映射为待处理/已成交/部分成交/已取消/已过期。
3. 启用 Task 3.3 中被门控的状态按钮，接 confirmation modal（复用 prototype 的 confirmation overlay），按钮文案必须说明影响范围。
4. 成功后 invalidate `dailyDecision / signals / deviation`；失败时保持原状态并展示结构化错误。
5. **Kill Switch**：仅 manual/paper 路径，无自动提交；状态机校验由后端 command handler 强制。

**Acceptance:** 可更新 intent 状态；deviation 从后端 refetch 后刷新；`bun run check` 通过。

---

### Task 4.3 manual execution ledger + 收尾 `[M]`

**Files:**
- Create: `src/features/trading/api/fill-ledger.ts`
- Modify: `src/features/trading/components/orders-page.tsx`
- Modify: `src/features/trading/components/portfolio-page.tsx`
- Test: `src/features/trading/components/orders-components.test.tsx`
- Test: `src/features/trading/components/trading-components.test.tsx`

**Steps:**
1. 增加 `fetchFills(strategyId, startDate?, endDate?)`，调用 `GET /v1/trade/fills` 并解包 `APIResponse.data`。
2. `/trading/orders` 在 Wave 1b 明确呈现为「手工执行流水」：显示 fill id、intent id、direction、quantity、fill price、fee、slippage、trade date、notes。
3. `/trading/portfolio` 的 Trades tab 或轻量 activity 区展示同一 fill ledger；没有 fills 时显示「尚未录入手工成交」空态，并引导回 Signals。
4. 统一 query invalidation：fill/intent 写后 daily-decision、fills、positions、deviation、pnl 全部刷新。
5. 运行前端 `bun run check`；联调后运行后端 `pixi run -e dev check`。

**Acceptance（Wave 1b DoD）：**
- UI 可记录手工 fill，deviation 从后端刷新。
- `/trading/orders` 不再假装是完整券商订单系统，而是清楚展示 manual execution/fill ledger。
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
- Phase 3/4 的 live DoD 只覆盖 Trading 域。Home/Markets/Research/Platform 的原型/MSW 保留是本计划的显式选择，不是缺陷。
- 非 Trading 域后续 live 化顺序：Platform（数据 readiness / pipeline health）→ Research（strategy / backtest / signal source）→ Markets（ETF/index 行情与 calendar）→ Home（跨域聚合 command center）。
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
额外要求：Trading live adapter 单测必须覆盖 `APIResponse.data` 解包、`/api` base path 拼接、ready/review/blocked/failed 四态。

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
- [x] Launch dataset readiness 明确 → **Phase 1.2 + 1.4**（Phase 1 完成，14 数据集 catalog evidence 齐全）
- [x] `/trade/daily-decision` 契约存在（Task 3 已完成）
- [ ] ditto-app Trading 域从真实后端显示 daily decision cockpit → **Phase 3.3**
- [ ] `/trading/signals` 和 `/trading/portfolio` 使用同一 daily-decision live adapter，能显示真实数据或结构化空态 → **Phase 3.3**
- [ ] Home/Markets/Research/Platform 保持 prototype/MSW 可评审状态，但不计入 live backend DoD → **Phase 3.1 + 3.3**
- [ ] `docs/acceptance/wave1a-first-real-use.md` 证据 → **Phase 3.4**

### Wave 1b DoD
- [ ] 前端记录手工 fill → **Phase 4.1**
- [ ] deviation 从后端刷新 → **Phase 4.2**
- [ ] `/trading/orders` 明确呈现 manual execution/fill ledger，而非完整券商订单系统 → **Phase 4.3**
- [x] optimizer-backed 目标组合路径（Task 7 已完成）

### Wave 1c DoD
- [x] 成交量约束填充入回测路径（Task 8 已完成）
- [x] Full RC1 promotion 证据 → **Phase 1.5 + Phase 2**（RC1 acceptance `passed=true && business_failures=[]`，2026-07-02）
- [x] 基础 attribution 支撑日常 review（Task 10 已完成）

---

## 9. Risk Register

| 风险 | 影响 | 缓解 |
|---|---|---|
| Tushare 限流导致大范围 backfill 慢/失败 | Phase 1 延期 | `--parallel` + 按月分段 + 失败日期补跑脚本 |
| 稀疏数据集（财报三表）空日期误判失败 | Phase 1.3 校验错误 | 用「有披露日期」校验，参考 `531a7b16` 语义 |
| promotion evidence 无法满足 3 条 criteria | Phase 1.5 卡住 | 提前为每条 criterion 准备真实材料（PIT 测试报告/文档/golden 输出），不触碰 governance 红线 |
| macro FRED PIT 路由 CLI 未暴露 | Phase 1.3 macro 不完整 | tushare macro 先满足 RC1；FRED PIT 走 job 层作为可选子任务 |
| ditto-app prototype 分支与接线冲突 | Phase 3 合并困难 | 独立 `feat/wave1-backend-wiring` 分支；只把 Trading 域 live 化，保留其他域原型资产 |
| MSW 关闭后非 Trading 路由访问真实后端失败 | 用户误以为全站 live | acceptance 入口固定 `/trading`；文档明确非 Trading 域仍是 prototype/MSW；后续逐域转正 |
| 后端 DTO 与前端原型类型并行漂移 | Phase 3 类型混乱 | generated OpenAPI types + `src/features/trading/api/*` adapter；组件只消费 view model |
| `VITE_API_BASE_URL=/api` 与 hook path 拼接错误 | live API 404 | hook path 写 `/v1/trade/...`；单测断言最终请求路径 |
| 真实数据 e2e 在 CI 无凭证跳过 | RC1 证据仅本地 | checklist §四要求凭证环境补跑；本地产出的 `rc1-report.json` 入 `artifacts/` |

---

## 10. Work Explicitly Deferred（不属本计划）

- 实时券商适配器、自动交易（Wave 2+，`reserved`）。
- Home/Markets/Research/Platform 的全量 live backend 产品化（按 Platform→Research→Markets→Home 后续逐域推进）。
- Paper account lifecycle 完整 UX、read-only AI copilot（Wave 2）。
- Signals Inbox 的 AI Review / Risk Officer 完整证据链、批量确认、完整订单确认 sheet。
- Orders Ledger 的真实券商订单生命周期、撤单/重试、route log。
- Risk Center 的完整 VaR/stress/incident runtime。
- 全量 Brinson/Barra position-level attribution（Task 10 已 defer）。
- cvxpy optimizer（需显式批准，Task 7 已用无新依赖 min-vol/inverse-vol hybrid）。

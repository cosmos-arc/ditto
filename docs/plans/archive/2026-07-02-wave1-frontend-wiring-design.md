# Wave 1 前端接线设计（Phase 3-4 校准）

> **日期：** 2026-07-02
> **前置：** [2026-07-01-wave1-completion-plan.md](2026-07-01-wave1-completion-plan.md)（Phase 1+2 已完成，RC1 门禁通过）
> **目标：** 把 ditto-app 的 **Trading 域**从 prototype/MSW 骨架转成 V1a 只读 live cockpit + V1b 手工执行写路径，达成 Wave 1a/1b DoD。
> **双仓库：** 后端 ditto（`feat/wave1-backend-capabilities`，RC1 已绿，本计划不改后端代码）+ 前端 ditto-app（新分支 `feat/wave1-backend-wiring`，从 `feat/prototype-three-zone-architecture` 拉）。
> **下文 `ditto-app/` 前缀的路径均指 ditto-app 仓库内路径**；无前缀的相对路径指 ditto 仓库。

---

## 0. 目标与北极星

**V1a 北极星：** `VITE_USE_MOCK=false` 时打开 `/trading`，从真实后端呈现 daily decision cockpit（readiness / signals / positions / deviation / pnl），不依赖 MSW。

**核心姿态：** 在 ditto-app 已打磨的原型产品方向、IA、交互模式上接线，把 mock 数据源换成 live adapter；组件结构与产品逻辑零改动或最小改动复用；仅在 ditto 后端新能力能明确增强已有原型未实现区时，才落现代化增强。

**Kill Switch（硬性）：** Phase 4 写路径走既有 application command handler + approval 路径，**不加自动交易**。paper/manual 是唯一执行面。

---

## 1. 执行现状基线（2026-07-02）

### 1.1 后端（已完成，trade API 在当前 HEAD）

- `GET /api/v1/trade/daily-decision?strategy_id=<required>&trade_date=<optional>` 是聚合端点，返回 `APIResponse<DailyDecisionReportResponse>`，`data` 含 `readiness + signal_intents + positions + deviation? + pnl?`。即使无信号也返回完整结构（`readiness=blocked, reasons=["no signal intents available"]`），前端不会收到半截数据。
- 其余端点：`intents / fills / positions / pnl / signals/latest / signals/{signal_date}/intents / deviation / comparison`（查询）+ `PUT intents/{id}/status / POST fills`（命令）。
- 全部挂在 `/api/v1`，router prefix `/trade`；`/openapi.json` live 暴露（无 committed schema）；maturity = `experimental`。

### 1.2 前端起点（ditto-app `feat/prototype-three-zone-architecture`）

- `feat/wave1-backend-wiring` 分支**不存在**——前端是一张白纸，但已有 mock-API 骨架。
- **可复用资产（已打磨，勿重写）：** `DecisionBanner`（Primary Answer 三栏参考实现）、`AnalyticalLayout`/`OpsConsoleLayout`（shell SSOT）、`useOverlayController`+`Drawer`（selected→overlay 标准模式，Orders/Risk 已用）、`DataTable`/`Metric`/`StatusBadge`(8 色 LED)/`Sparkline`/`LoadingSkeleton`/`DittoErrorBoundary`、`SignalDetailPanel` 的 AI Review 三件套、14 个 trading hook 的形状与组件消费逻辑、`ContextSection`/`ScopeStrip`。
- **接线缺口：** API 路径双重错配（前端 `/api/trading/*` vs 后端 `/api/v1/trade/*`）、无 OpenAPI codegen、`apiClient` 无 `APIResponse` 解包、MSW DEV 强制全 mock 无 `VITE_USE_MOCK` 开关、无 vite proxy/`.env`、`signals-page.tsx` selected 写死 `sig-001`、`trading-page.tsx`/`portfolio-page.tsx` 部分 mock 硬编码。

---

## 2. 三大认知更新（为何必须校准 plan）

### 2.1 前后端 API 形态是两套设计

前端原型按「细粒度多端点」设计（`/trading/session`、`/trading/equity`、`/trading/risk/var|drawdown|exposure|breaches`、`/trading/signals/queue`、`/trading/orders/summary`），后端实际实现是「聚合 + trade 域」（`daily-decision` 聚合 + `intents/fills/positions/pnl/deviation/comparison`）。**前端原型的 Risk 全系列、Session、Equity 这些端点后端根本没有**——这不是改路径能解决的，是两套 API 设计。

### 2.2 原型资产必须复用，不是重写

`DecisionBanner`/`DataTable`/`SignalDetailPanel` AI Review/14 个 hook 的形状与消费逻辑/`useOverlayController` 都是产品决策的沉淀。接线策略是「换数据源，组件层零改动」，不是「新建 adapter 替换 hooks」。

### 2.3 V1a live 边界由后端能力决定

V1a 能 live 的组件 = `daily-decision`（+ Phase 4 的 `fills/intents`）能喂养的组件。后端无端点的组件（Risk/Session/Equity）在 V1a **保留为 prototype 资产**，显示结构化空态——不删除、不伪造、不报错。

---

## 3. 契约修正清单（vs plan §1.5 / Task 3.2）

| # | plan 假设 | 后端实际 | 修正 |
|---|---|---|---|
| 3.1 | `APIResponse = {code, message, data}` | `{data, pagination?}`；错误 `{status_code, error, detail, error_code, request_id, timestamp}` | `apiClient` 解包 `data`；`ApiError` 带 `error_code` 供组件区分 conflict/transition |
| 3.2 | `signals/{strategy_id}/intents` | `signals/{signal_date}/intents`，`strategy_id` 永远在 query | hook path 与 query param 修正 |
| 3.3 | 未强调 strategy_id | **所有 11 个 trade 端点必填 query param** | `DEFAULT_STRATEGY_ID` 常量，所有 trade query 自动带（Task 3.1 第一步从后端 seed 确认具体 ETF 策略 id） |
| 3.4 | 假设可 codegen | `/openapi.json` live 暴露，**无 committed schema** | `bun run gen:api` 脚本 curl live schema；commit generated snapshot 作基线；experimental 变更时重跑刷新 |
| 3.5 | 未提 maturity | 整个 `/api/v1/trade` 标记 `experimental`，OpenAPI 每 operation 带 `x-ditto-maturity` | Trading 布局顶部常驻「experimental capability」标注 |

---

## 4. 架构：中间层 adapter + 分层

### 4.1 前端分层（自顶向下，单向依赖）

```
components/*              只消费 view model，不碰后端字段（零改动复用）
hooks/use-*               TanStack Query，返回 mapped view model（形状不变，内部改造）
features/trading/api/*    adapter：fetch + 解包 APIResponse + DTO→view model 映射 + 聚合分发
types/generated/api.d.ts  openapi-typescript 从后端 /openapi.json 生成（传输 DTO）
types/trading.ts          手写 UI view model（保留）
lib/api-client.ts         fetch wrapper（加 APIResponse 解包 + ApiError）
```

**硬约束：** 组件只 import view model（`types/trading.ts`），**禁止**组件直接 import generated DTO。

### 4.2 adapter 职责（薄中间层，组件零改动）

- `lib/api-client.ts`：加 `APIResponse{data,pagination?}` 解包 + `ApiError`（带 `error_code`）。
- `ditto-app/src/features/trading/api/daily-decision.ts`：`fetchDailyDecision()` 调 `/v1/trade/daily-decision`，解包 `data`。
- `ditto-app/src/features/trading/api/mappers.ts`：`DailyDecisionReportResponse` → 各 view model（positions/signals/deviation/pnl/readiness）。

### 4.3 daily-decision 聚合分发（一次调用喂多个 hook）

14 个 trading hook 的**接口形状不变**（组件零改动），内部实现改造：

- **有后端的 hook**（`usePositions`/`useSignals`/`useSignalDetail`/`useDeviation`/`usePnl`/`useRiskSummary` 的 readiness 部分）→ 内部委托 `useDailyDecision` 的 TanStack `select` 派生，一次聚合调用喂多个 hook。
- **无后端的 hook**（`useTradingSession`/`useEquity`/`useRiskVar`/`useRiskDrawdown`/`useRiskExposure`/`useRiskBreaches`）→ 保持现状调 MSW；`VITE_USE_MOCK=false` 时返回结构化空态 sentinel，组件显空态。

### 4.4 优雅降级（V1a live 边界）

`VITE_USE_MOCK=false` 时：
- 能 live 的组件（§5 表 ✅）从 `daily-decision` 取真实数据。
- 后端无端点的组件（§5 表 ⚠️）显示结构化空态「V1a 未接 live，数据待后端补齐」。Risk Page 整体标注「prototype only」但仍可访问。
- `VITE_USE_MOCK=true` 时全产品原型照常（含 Risk/Session/Equity 的 MSW）。

---

## 5. 后端能力 × 原型落点 × V1a 状态

| 后端能力 | 原型落点（复用已有组件） | V1a 状态 |
|---|---|---|
| `daily-decision` 聚合 | `DecisionBanner`（换 mock 数据源）+ Signals 队列 + Positions 区 | ✅ live |
| `signal_intents` | `SignalsList` + `SignalDetailPanel`（AI Review 三件套复用） | ✅ live |
| `positions` + `available_quantity` | `PositionsSummary`（DataTable + T+1 冻结 Badge） | ✅ live |
| `deviation` bps | `SignalDetailPanel` riskChecks 第 5 项（价格合理性）+ Overview 偏离区 | ✅ live（+增强） |
| `pnl` | `EquityPnlBlock` summary 部分 + Portfolio 概要 | ✅ live |
| `comparison`（backtest vs actual） | **Portfolio 归因 tab**（蓝图 §12 未实现区）+ 盘后复盘「持仓健康检查」 | ✅ 落地（后端新能力） |
| `fills` + `intents status` | Orders 已完成 tab + Portfolio 交易 tab + **Signal-to-Order Pipeline Strip** | ✅ Phase 4 |
| ~~`/trading/session`~~ | `TradingSessionStrip` | ⚠️ V1a 保留 MSW（后端无端点） |
| ~~`/trading/equity` 系列~~ | `EquityPnlBlock` sparkline（权益时序） | ⚠️ V1a 保留 MSW |
| ~~`/trading/risk/*`~~ | `RiskScopeStrip`/`RiskExposureSummary`/`RiskBreachesList` | ⚠️ V1a 保留 MSW |

---

## 6. Phase 3 — 只读 product slice（6 task）

### Task 3.1 分支、环境、apiClient 解包 `[M]`

**Files:** `ditto-app/` `.env.development`（create）、`vite.config.ts`、`src/main.tsx`、`src/lib/api-client.ts`、`src/features/trading/api/query-keys.ts`（create）、`src/lib/api-client.test.ts`

**Steps:**
1. `git switch -c feat/wave1-backend-wiring`（从 `feat/prototype-three-zone-architecture`）。
2. **前置确认 `DEFAULT_STRATEGY_ID`**：从后端 seed 确认一个已发布的 ETF rotation 策略 id，写入 `src/features/trading/api/query-keys.ts` 或 config 常量。
3. `.env.development`：`VITE_API_BASE_URL=/api`、`VITE_USE_MOCK=false`。
4. `vite.config.ts`：加 `server.proxy['/api']` → 本地 Ditto 后端端口。
5. `main.tsx`：MSW gate 改为 `if (import.meta.env.VITE_USE_MOCK === "true")`，移除「DEV 强制全 mock」。
6. `api-client.ts`：加 `APIResponse{data,pagination?}` 解包 + `ApiError`（含 `error_code`）；hook path 统一写 `/v1/trade/...`，apiClient 拼 `API_BASE_URL=/api` → `/api/v1/trade/...`。

**Acceptance:**
- `bun run dev` 默认打真实后端；`VITE_USE_MOCK=true` 时全产品原型可用。
- `api-client.test.ts` 覆盖解包、ApiError、base path 拼接（断言 `/v1/trade/...` 非 `/api/v1/...`）。
- `bun run check` 通过。

---

### Task 3.2 codegen + daily-decision adapter + 14 hook 改造 `[L]`

**Files:** `ditto-app/` `package.json`（加 `gen:api` script）、`scripts/gen-api.sh`（create）、`src/types/generated/api.d.ts`（生成 + commit snapshot）、`src/features/trading/api/daily-decision.ts`（create）、`src/features/trading/api/mappers.ts`（create）、`src/features/trading/hooks/*`（14 个改造）、`src/features/trading/api/__tests__/daily-decision.test.ts`、`src/features/trading/api/__tests__/mappers.test.ts`

**Steps:**
1. `scripts/gen-api.sh`：curl 后端 `/openapi.json` → `openapi-typescript` → `src/types/generated/api.d.ts`；commit snapshot 作基线。
2. `daily-decision.ts`：`fetchDailyDecision({ strategyId, tradeDate? })` 调 `apiClient.get<APIResponse<DailyDecisionReportResponse>>(withQueryParams("/v1/trade/daily-decision", { strategy_id, trade_date }))`，返回解包 `data`。
3. `mappers.ts`：DTO → UI view model。`instrument_id` 先显示 `#<id>` fallback；`direction` 映射 `BUY/SELL/HOLD`；intent status 映射 Signals UI tabs；readiness reasons 映射中文文案；deviation bps 透传。
4. 14 个 hook 内部改造：有后端的 hook 委托 `useDailyDecision` 的 `select` 派生；无后端的 hook 保留 MSW 调用 + `VITE_USE_MOCK=false` 降级空态 sentinel。
5. query-keys：`tradingKeys.dailyDecision(strategyId, tradeDate)` 等。

**Acceptance:**
- hook 单测覆盖 ready/review/blocked/failed 四态 + select 派生 + 降级空态。
- 类型来自 generated + mapper view model，无 `any`/`@ts-ignore`。
- 路径断言：`/v1/trade/daily-decision`。
- `bun run check` 通过。

---

### Task 3.3 Overview + Signals live（核心页 + selected 修复）`[L]`

**Files:** `ditto-app/src/features/trading/components/` `trading-page.tsx`、`signals-page.tsx`、`signals-list.tsx`、`signal-detail-panel.tsx`；测试 `trading-components.test.tsx`、`signals-components.test.tsx`

**Steps:**
1. **Overview**：`DecisionBanner` mock（`DECISION_BANNER_PROPS`）换 `useDailyDecision` 的 readiness + signal count + positions + deviation/pnl，组成 Primary Answer（一句话判断 + 关键数字 + 2-3 证据 + 主动作，标记 `data-primary-answer`）。信号队列区 mock（`MOCK_SIGNALS`）换 `signal_intents`（保留 priority dot / direction 着色 / confidence 阈值等产品逻辑）。
2. **Signals**：`signal_intents` 渲染复核队列。**修复 selected→overlay 联动**——`signals-page.tsx` 去掉 `DEFAULT_SIGNAL_ID="sig-001"`，改 `useState(selectedIntentId)` + `useOverlayController` + `Drawer`（直接复用 `orders-page.tsx` 参考实现）。
3. **SignalDetailPanel**：复用 AI Review 三件套（explanation + pass/warn/fail checks + 组合影响 + actions.disabled）。**增强：deviation bps 作为第 5 项 riskCheck**（价格合理性，>阈值 warn/fail）。
4. **状态矩阵硬底线**：齐备 loading（Skeleton）/ empty（区分休市 vs 错误，文案随 readiness reasons）/ failed（DittoErrorBoundary）/ selected / blocked（数据未就绪 disabled）。

**Acceptance:**
- `/trading` 显示 readiness、signal count、positions、deviation/pnl。
- `/trading/signals` selected→detail 联动正常（spec §selected 合同）。
- 无数据时显 structured empty/blocked，不报错、不空白、不沿用 mock。
- `bun run check` 通过。

---

### Task 3.4 Portfolio + Positions + 归因 tab + Pipeline Strip `[L]`

**Files:** `ditto-app/src/features/trading/components/` `portfolio-page.tsx`、`positions-summary.tsx`、`signal-to-order-pipeline-strip.tsx`（create）；测试 `positions-summary.test.tsx`、`portfolio-components.test.tsx`（create/extend）

**Steps:**
1. **PositionsSummary**：复用 DataTable + T+1 冻结 StatusBadge；`available_quantity ≠ quantity` 显「冻结」标记。换 `usePositions`（已 select 派生）。
2. **Portfolio**：`PORTFOLIO_ROWS` mock 换 positions/pnl。**归因 tab 落地**（蓝图 §12 未实现区）：复用 `DataTable`（因子贡献表）+ `DonutGauge`/`FlowBar`（行业/个股贡献），数据源 `GET /v1/trade/comparison`（backtest vs actual tracking error）。空态「无归因数据」。
3. **Signal-to-Order Pipeline Strip**（蓝图 §Trading Overview v2.0 既定需求，此前未实现）：L2 水平进度条，复用 `Metric`/`FlowBar`；数据源 `intents status` 各阶段计数（信号池→待复核→已下单→成交）。**V1a 只读阶段后两段（已下单→成交）可能为 0**，Strip 正常渲染「待成交」态。

**Acceptance:**
- `/trading/portfolio` 展示真实 positions/pnl + 归因 tab（comparison 数据或空态）。
- Pipeline Strip 渲染各阶段计数。
- `bun run check` 通过。

---

### Task 3.5 Risk/Session/Equity 降级 + 非 Trading 域空态 + MSW 双轨 `[M]`

**Files:** `ditto-app/` `src/features/trading/components/risk-page.tsx`、`trading-session-strip.tsx`、`equity-pnl-block.tsx`；`src/mocks/handlers/*`（新增 trade handler + 保留旧 handler）；非 Trading 域 page components

**Steps:**
1. Risk/Session/Equity 组件（后端无端点的 ⚠️ 项）：`VITE_USE_MOCK=false` 时显结构化空态「V1a 未接 live，数据待后端补齐」（复用 `EmptyState` 内联模式 + `StatusBadge` 标注 prototype）。**不删除组件、不伪造数据**。Risk Page 整体顶部标注「prototype only」。
2. 非 Trading 域（Home/Markets/Research/Platform）：`VITE_USE_MOCK=false` 时显示「prototype only，请切 `VITE_USE_MOCK=true`」结构化空态——不删除原型、不报错、不连真后端。
3. MSW 双轨：新增 `/api/v1/trade/daily-decision` + `fills` + `intents` handler（供组件测试 + 原型演示）；**保留**旧 `/api/trading/*` handler 给非 Trading 原型与历史组件测试。

**Acceptance:**
- `VITE_USE_MOCK=false` 时 Risk/Session/Equity 显空态不报错；全产品无白屏。
- `VITE_USE_MOCK=true` 时全产品原型正常（含 Risk/Session/Equity）。
- MSW `onUnhandledRequest:"error"` 护栏对新旧 handler 都通过。
- `bun run check` 通过。

---

### Task 6 / Task 3.6 V1a smoke + 证据 `[M]`

**Files:** `docs/acceptance/wave1a-first-real-use.md`（ditto 仓库，create）

**Steps:**
1. 起 Ditto 后端（`source scripts/acceptance/wave1_env.sh` + server）。
2. 跑 EOD 或 publish-signals 产出 ETF 策略 intents。
3. ditto-app `VITE_USE_MOCK=false` 启动，打开 `/trading`，捕获：readiness、latest signal date、signal count、positions、deviation/pnl、Pipeline Strip、Portfolio 归因。
4. 截图/记录到 `docs/acceptance/wave1a-first-real-use.md`。
5. 明确说明 Home/Markets/Research/Platform + Risk/Session/Equity 仍是 prototype/MSW，不纳入本次 live DoD。
6. 后端 `pixi run -e dev check` + 前端 `bun run check`。
7. Commit `docs: add wave1a first real use evidence`。

**Acceptance（Wave 1a DoD）：** 有人类可读证据文件证明 Trading 域 first real-use 路径；若仍 blocked，文件列 exact blockers，不假装成功。

---

## 7. Phase 4 — 写路径（3 task，Kill Switch manual/paper）

### Task 4.1 record fill action `[M]`

**Files:** `ditto-app/src/features/trading/api/fills.ts`（create）、`src/features/trading/hooks/use-record-fill.ts`（create）、`src/features/trading/components/signal-detail-panel.tsx`；测试 `fills.test.ts`、`signals-components.test.tsx`

**Steps:**
1. `recordFill(payload)` mutation 调 `POST /v1/trade/fills`，payload 对齐后端 `RecordFillRequest`。
2. 复用 `SignalDetailPanel` 的**订单确认 Sheet**（蓝图 §Signals 状态检查矩阵）：从 selected intent 预填 `intent_id/strategy_id/trade_date/instrument_id/direction/quantity`，用户输入 `fill_price/fee/slippage/notes`。
3. 表单校验：`quantity > 0`、`fill_price > 0`、`fee >= 0`、`slippage` 有限数字、`intent_id` 非空。
4. 成功后 invalidate `dailyDecision / positions / deviation / pnl / fills`；失败显结构化错误（不吞 conflict/transition，用 `error_code`）。

**Acceptance:** UI 从 selected intent 录入手工 fill；失败显结构化错误；deviation/positions/pnl refetch 后刷新；`bun run check` 通过。

---

### Task 4.2 intent status action `[M]`

**Files:** `ditto-app/src/features/trading/api/intents.ts`（create）、`src/features/trading/hooks/use-update-intent-status.ts`（create）、`src/features/trading/components/signal-detail-panel.tsx`；测试 `intents.test.ts`、`signals-components.test.tsx`

**Steps:**
1. `updateIntentStatus(intentId, status)` mutation 调 `PUT /v1/trade/intents/{intent_id}/status`。
2. 支持后端状态机：`pending / filled / partially_filled / cancelled / expired`（中文文案映射）。
3. 启用 Task 3.3 中被门控的 actions 按钮；复用 prototype 的**高风险确认 overlay**（spec §16.2：`data-impact-summary` + `data-confirm-control` + `data-cancel-control` + `data-recovery-hint` + 非颜色 `data-danger-marker`），按钮文案说明影响范围。
4. 成功后 invalidate `dailyDecision / signals / deviation`；失败保持原状态 + 结构化错误。
5. **Kill Switch**：仅 manual/paper，无自动提交；状态机校验由后端 command handler 强制。

**Acceptance:** 可更新 intent 状态；deviation refetch 后刷新；`bun run check` 通过。

---

### Task 4.3 Orders/Portfolio ledger + Pipeline Strip 补完 `[M]`

**Files:** `ditto-app/src/features/trading/api/fill-ledger.ts`（create）、`src/features/trading/components/orders-page.tsx`、`portfolio-page.tsx`、`signal-to-order-pipeline-strip.tsx`；测试 `orders-components.test.tsx`、`trading-components.test.tsx`

**Steps:**
1. `fetchFills(strategyId, startDate?, endDate?)` 调 `GET /v1/trade/fills`，解包 `APIResponse.data`。
2. `/trading/orders` 明确呈现为「手工执行流水」：fill id、intent id、direction、quantity、fill price、fee、slippage、trade date、notes（复用 `OpsConsoleLayout` + `DataTable`）。
3. `/trading/portfolio` 交易 tab 展示同一 fill ledger；无 fills 时显「尚未录入手工成交」空态，引导回 Signals。
4. **Pipeline Strip 补完四段**：fills + intents status 提供完整计数（信号池→待复核→已下单→成交）。
5. 统一 query invalidation：fill/intent 写后 `dailyDecision / fills / positions / deviation / pnl` 全刷新。
6. 前端 `bun run check`；联调后后端 `pixi run -e dev check`。

**Acceptance（Wave 1b DoD）：**
- UI 可记录手工 fill，deviation 从后端刷新。
- `/trading/orders` 清楚展示 manual execution/fill ledger（非完整券商订单系统）。
- Pipeline Strip 四段完整。
- optimizer-backed 目标组合路径已存在（plan Task 7 已完成）。

---

## 8. 测试策略

| 层 | 覆盖 |
|---|---|
| **adapter 单测** | `fetchDailyDecision` + `APIResponse{data,pagination?}` 解包 + mappers（ready/review/blocked/failed 四态）+ 路径断言（`/v1/trade/daily-decision`）+ `error_code` 映射 |
| **hook 单测** | 14 个 hook 的 `select` 派生正确性 + 后端无端点 hook 的降级空态 |
| **组件测试** | 扩展现有 7 个 trading 测试文件：selected→overlay、Pipeline Strip 四段、Portfolio 归因 tab、record fill 表单校验、intent status 确认链路 |
| **MSW 护栏** | 新增 `/api/v1/trade/daily-decision`+`fills`+`intents` handler；`onUnhandledRequest:"error"` |
| **codegen 一致性** | `bun run gen:api` 刷新 snapshot；experimental 变更时重跑 |
| **e2e smoke** | 手动：起后端 + EOD + `VITE_USE_MOCK=false` 打开 `/trading` → `docs/acceptance/wave1a-first-real-use.md` |
| **后端联调** | `pixi run -e dev check`（Phase 4 联调后） |

**前端质量门禁：** `bun run check`（biome + tsc + vitest）全绿；无 `any`/`@ts-ignore`/inline style 回归；adapter 单测必须覆盖 `APIResponse.data` 解包、`/api` base path 拼接、ready/review/blocked/failed 四态。

---

## 9. Definition of Done

### Wave 1a DoD
- [x] EOD 能发布信号包（plan Task 1 已完成）
- [x] Launch dataset readiness（Phase 1 已完成）
- [x] `/trade/daily-decision` 契约存在（plan Task 3 已完成）
- [ ] ditto-app Trading 域从真实后端显示 daily decision cockpit → **Task 3.3**
- [ ] `/trading/signals` 和 `/trading/portfolio` 使用同一 daily-decision live adapter，显示真实数据或结构化空态 → **Task 3.3 + 3.4**
- [ ] Home/Markets/Research/Platform + Risk/Session/Equity 保持 prototype/MSW 可评审状态，不计入 live DoD → **Task 3.5**
- [ ] `docs/acceptance/wave1a-first-real-use.md` 证据 → **Task 3.6**

### Wave 1b DoD
- [ ] 前端记录手工 fill → **Task 4.1**
- [ ] deviation 从后端刷新 → **Task 4.2**
- [ ] `/trading/orders` 呈现 manual execution/fill ledger → **Task 4.3**
- [x] optimizer-backed 目标组合路径（plan Task 7 已完成）

### Wave 1c DoD（后端侧，已完成）
- [x] 成交量约束填充入回测路径（plan Task 8）
- [x] Full RC1 promotion 证据（Phase 1.5 + Phase 2，2026-07-02）
- [x] 基础 attribution 支撑日常 review（plan Task 10）

---

## 10. 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| 后端 `experimental` maturity 导致 DTO 漂移 | codegen 类型失效 | commit snapshot 基线 + experimental 变更时重跑 `gen:api`；adapter 隔离 DTO，组件只消费 view model |
| `DEFAULT_STRATEGY_ID` 后端 seed 未确认 | Task 3.1 卡住 | Task 3.1 第一步确认；若无 seed，临时注册一个 ETF rotation 策略 |
| daily-decision 聚合分发与现有 hook 形状不完全匹配 | hook 改造量超预期 | mappers.ts 集中映射；hook 接口形状不变，内部实现改造；组件零改动 |
| Pipeline Strip V1a 只读阶段后两段为 0 | 半成品观感 | 接受——蓝图既定需求，V1a 渲染「待成交」态，Phase 4 补完 |
| 非 Trading 域 `VITE_USE_MOCK=false` 时空态体验 | 用户困惑 | 空态明确标注「prototype only，请切 `VITE_USE_MOCK=true`」 |
| ditto-app prototype 分支与接线冲突 | 合并困难 | 独立 `feat/wave1-backend-wiring` 分支；只 Trading 域 live，保留其他域原型 |
| 后端无端点组件（Risk/Session/Equity）误判为接线失败 | Task 3.5 返工 | §5 表明确标注 ⚠️ = 保留 MSW，不是接线目标 |

---

## 11. 与 `2026-07-01-wave1-completion-plan.md` 的差异小结

- **契约修正（§3）：** APIResponse 包装、signals 路径、strategy_id 必填、codegen 抓 live schema、maturity experimental——5 处偏差。
- **架构重构（§4）：** 从「新建 adapter 替换 14 hook」改为「薄中间层 + daily-decision 聚合分发 + 优雅降级」，组件层零改动复用原型。
- **V1a live 边界澄清（§5）：** 明确 Risk/Session/Equity 在 V1a 保留 MSW（后端无端点），plan 未显式覆盖。
- **task 重组：** plan 3.3 拆成 3.3+3.4（纳入 Portfolio 归因 tab + Pipeline Strip + selected 修复）；新增 3.5（降级空态）；Phase 4 补 Pipeline Strip 完整四段。
- **现代化增强（基于后端新能力，不破坏原型）：** Portfolio 归因 tab（comparison）、Signal-to-Order Pipeline Strip（intents status）、deviation bps 第 5 项 riskCheck。
- **deferred（同 plan §10）：** Home/Markets/Research/Platform 全量 live（按 Platform→Research→Markets→Home 逐域）、实时券商、自动交易、完整 VaR/stress、完整 Brinson/Barra attribution、cvxpy optimizer。

---

## 12. 依赖与并行

```
Task 3.1 ─ Task 3.2 ─┬─ Task 3.3 ─ Task 3.4 ─┐
                      └─ Task 3.5 ─────────────┤
                                               ├─ Task 3.6 (V1a ✅) ─ Task 4.1 ─ Task 4.2 ─ Task 4.3 (V1b ✅)
```

- 前端（Phase 3-4）与后端（Phase 1-2 已完成）独立分支、独立 PR。
- 每 task 一 PR，PR size gate：不混 task（如不把 3.3/3.4 混提）。
- Phase 4 严格依赖 Phase 3 接线完成。

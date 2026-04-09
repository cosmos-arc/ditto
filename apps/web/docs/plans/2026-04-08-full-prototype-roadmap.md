# Ditto App 全量原型落地路线图

## 概述

- **范围**: 17 页全部按蓝图落地（含 4 页需新增路由）
- **方式**: 纯前端 + MSW Mock，无后端依赖
- **交付**: 三批里程碑交付
- **创建**: 2026-04-08
- **当前状态**: Shell 完成 / 共享组件 22 个 / 400 测试 / 23 条路由占位

## 当前进度快照

| 维度 | 完成 | 待做 |
|------|------|------|
| Shell 布局系统 | AppShell + 6 Layout + Rail + Header | 响应式 hook |
| 共享组件 | 22 组件 (data/status/indicator/domain/ui) | — |
| 页面路由 | 25 路由定义，2 页有内容 (showcase + 首页骨架) | 17 页业务内容 |
| 数据层 | api-client.ts 骨架 | types / MSW handlers / hooks / stores |
| 缺失路由 | — | a-shares / calendar / factors/$id / backtest/$id |

## 三批交付里程碑

### M1: 基础可观测 (Batch 1) — 6 页

> 用户能打开应用，看到市场全貌、研究进展、交易状态、平台健康

| # | 页面 | 路由 | 页面模式 |
|---|------|------|---------|
| 1 | Home Command Center | `/` | Command Center |
| 2 | Cross-Market Overview | `/markets` | Analytical Workspace |
| 3 | Markets Screener | `/markets/screener` | Catalog / Screener |
| 4 | Research Workspace | `/research` | Analytical Workspace |
| 5 | Trading Overview | `/trading` | Analytical Workspace |
| 6 | Platform Ops Console | `/platform` | Ops Console |

### M2: 核心链路 (Batch 2) — 4 页

> 用户能查看标的详情、复核信号、编辑策略、查看回测结果

| # | 页面 | 路由 | 页面模式 |
|---|------|------|---------|
| 7 | Instrument Hub | `/instruments/$id` | Object Hub |
| 8 | Signals Inbox | `/trading/signals` | Queue / Ops Console |
| 9 | Strategy Studio | `/research/strategy-studio` | Studio / Builder |
| 10 | Backtest Result | `/research/backtest/$id` (新增) | Object Hub |

### M3: 全域覆盖 (Batch 3) — 7 页 + 4 补全

> 所有页面可访问，全功能闭环

| # | 页面 | 路由 | 页面模式 |
|---|------|------|---------|
| 11 | Orders Ledger | `/trading/orders` | Ledger / Execution Console |
| 12 | Risk Center | `/trading/risk` | Analytical Workspace |
| 13 | AI Overview | `/ai` | Command Center (轻量) |
| 14 | AI Copilot Studio | `/ai/copilot` | Studio / Builder |
| 15 | Agent Console | `/ai/agents` | Studio / Builder |
| 16 | Regime Monitor | `/research/regime` | Analytical Workspace (Chart-first) |
| 17 | Markets Intelligence | `/markets/intelligence` | Analytical Workspace |
| + | A-Shares Overview | `/markets/a-shares` (新增) | Analytical Workspace |
| + | Markets Calendar | `/markets/calendar` (新增) | Catalog |
| + | Factor Analysis | `/research/factors/$id` (新增) | Object Hub |
| + | Strategy Detail | `/strategies/$id` | Object Hub |

---

## Sprint 0: 数据基础设施 (前置)

> **目标**: 建立页面开发所需的全部数据层模式，后续 Sprint 可直接复用

### T1: API 类型体系搭建 `[L]`

为 6 个业务域定义 TypeScript 类型，基于 API 全链路文档的 106 端点。

- 创建 `src/types/` 目录，按域划分类型文件
- 每个端点的 request/response 类型
- 分页、过滤、排序等通用类型
- 复用已有 `openapi-typescript` 工具链

**验收**: 所有域类型编译通过，无 `any`

```
src/types/
├── index.ts              # barrel export
├── common.ts             # Pagination / Sorting / ApiResponse<T> / ApiError
├── platform.ts           # Platform 域 8 端点类型
├── home.ts               # Home 域 8 端点类型
├── markets.ts            # Markets 域 (overview + screener + intelligence + calendar)
├── instruments.ts        # Instrument Hub 类型
├── research.ts           # Research 域 (workspace + regime + factor + strategy + backtest)
├── trading.ts            # Trading 域 (overview + signals + orders + risk)
└── ai.ts                 # AI 域 (copilot + agent + overview)
```

**文件**: ~10 files | **测试**: 类型编译即验证 (tsc --noEmit)

---

### T2: MSW 基础设施 `[L]`

建立 MSW mock 数据生成模式，为每个页面提供逼真的静态数据。

- 为每个域创建 fixture 工厂函数（使用 faker 或手写）
- 建立 handler 注册模式（按域分文件）
- 建立 fixture 数据目录

**验收**: `GET /api/platform/health` 等 3-5 个端点可被 mock 拦截并返回类型安全数据

```
src/mocks/
├── browser.ts            # 已有
├── server.ts             # 已有 — 增强 handler 注册
├── handlers/
│   ├── index.ts          # barrel export + 路由注册
│   ├── platform.ts
│   ├── home.ts
│   ├── markets.ts
│   ├── instruments.ts
│   ├── research.ts
│   ├── trading.ts
│   └── ai.ts
└── fixtures/
    ├── platform.ts       # Platform mock 数据
    ├── home.ts
    ├── markets.ts
    ├── instruments.ts
    ├── research.ts
    ├── trading.ts
    └── ai.ts
```

**文件**: ~16 files | **测试**: handler 单元测试

---

### T3: TanStack Query Hooks 模式 `[M]`

建立按域组织的 data hooks 模式。

- 每个域一个 hooks 文件
- 统一使用 `useQuery` / `useMutation`
- 统一的 staleTime / gcTime 配置
- 统一的 error handling（复用 DittoErrorBoundary）

**验收**: 至少 3 个 hook 可用，页面组件能通过 hook 获取 mock 数据并渲染

```
src/features/platform/hooks/use-platform-health.ts   # 示例
src/features/platform/hooks/use-platform-providers.ts
src/features/platform/hooks/index.ts
src/features/home/hooks/use-home-pulse.ts
...
```

**文件**: ~8 files (初始) | **测试**: hook 单元测试 (renderHook)

---

### T4: Zustand Store 模式 `[M]`

建立客户端状态管理，用于非服务端状态（UI 状态、筛选条件、选中项等）。

- `src/stores/` 目录
- 通用 store 模式：创建 + devtools + persist
- 初始 store：theme store、navigation store

**验收**: theme store 可在 DevTools 中观察到状态变化

```
src/stores/
├── index.ts
├── create-store.ts       # 工厂函数
├── theme.store.ts        # 主题切换
└── navigation.store.ts   # 导航状态 (collapsed sections 等)
```

**文件**: ~4 files | **测试**: store 单元测试

---

### T5: 图表库选型与集成 `[M]`

共享组件设计文档提到"SVG/ECharts/Lightweight Charts 三轨制"，需确定选型并集成。

- 评估 lightweight-charts (TradingView) 用于金融图表
- 评估 recharts 或 visx 用于通用图表
- 创建 chart wrapper 组件

**验收**: 能在 showcase 页面渲染一个折线图 + 一个 K 线图

**依赖**: 需新增 npm 包（需用户批准）

```
src/components/chart/
├── index.ts
├── line-chart.tsx        # 通用折线图
├── area-chart.tsx        # 面积图 (NAV curve)
└── candlestick-chart.tsx # K 线图
```

**文件**: ~4 files + 1-2 dependencies | **测试**: snapshot 测试

---

### T6: 路由补齐 `[S]`

为 4 个缺失页面添加路由文件。

- `/markets/a-shares` — A 股总览
- `/markets/calendar` — 事件日历
- `/research/factors/$id` — 因子分析
- `/research/backtest/$id` — 回测结果

**验收**: 4 条新路由可访问，使用对应 Shell Layout

```
src/routes/markets/a-shares.tsx
src/routes/markets/calendar.tsx
src/routes/research/factors.$id.tsx
src/routes/research/backtest.$id.tsx
```

**文件**: ~4 files | **测试**: 路由快照测试

---

### Sprint 0 依赖关系

```
T1 (类型) ──┬──> T2 (MSW)
             └──> T3 (Hooks)

T4 (Stores)  — 独立
T5 (Charts)  — 独立
T6 (路由)    — 独立
```

**Sprint 0 完成标准**: `bun run check` 通过 + 至少 1 个 hook + 1 个 MSW handler 端到端验证

---

## Sprint 1: M1 — Platform + Home

> **目标**: 交付最简页面 (Platform) 作为模板 + 最复杂的聚合页面 (Home)

### T1: Platform Ops Console 落地 `[L]`

**参考蓝图**: Page 15 — Platform Ops Console
**页面模式**: Queue / Ops Console

**子任务**:
1. MSW fixtures: health strip 数据、providers 列表、pipelines 列表、alerts 列表
2. MSW handlers: Platform 域 8 个 GET 端点
3. TanStack Query hooks: `usePlatformHealth`, `useProviders`, `usePipelines`
4. 页面组件: HealthStrip + DataProviders + PipelinesTable + AlertsList
5. 四态处理: loading (skeleton) / empty / failed / stale

**关键区块**:
- Health Strip (Freshness/Completeness/Accuracy/Jobs)
- Data Providers & DQ 面板
- Pipelines & Jobs 表格
- System Alerts 列表
- Resources & Quotas

**验收**: Platform 页面显示 mock 数据，导航可用，Health Strip 指标正确

**文件**: ~8 files (handlers + fixtures + hooks + page + 5 sub-components + tests)

---

### T2: Home Command Center 落地 `[XL]` → 拆为 2 个子任务

**参考蓝图**: Page 1 — Home Command Center
**页面模式**: Global Command Center

#### T2.1: Home 数据聚合层 `[M]`
- MSW fixtures: pulse、decision-banner、pending-actions、alerts、signals/recent、agent-findings、data-health、market/indices
- MSW handlers: Home 域 8 个 GET 端点
- TanStack Query hooks: 8 个 home hooks

#### T2.2: Home 页面组件 `[L]`
- Today Pulse 区块 (综合市场状态)
- Decision Banner 区块 (使用已有 DecisionBanner 组件)
- Pending & Next Actions 区块
- Alerts & Market Snapshot 区块
- Recent Signals & Runs 区块
- Agent Findings & Data Health 区块

**验收**: Home 页面 6 个区块均有 mock 数据，Decision Banner 可交互

**文件**: ~12 files (handlers + fixtures + hooks + page + 6 sub-components + tests)

---

### Sprint 1 依赖

```
T1 (Platform) ──> 独立，最先做（作为模板）
T2.1 (Home 数据) ──> 依赖 Sprint 0 T1+T2
T2.2 (Home 页面) ──> 依赖 T2.1
```

**M1-1 交付标准**: Platform + Home 2 页端到端可用

---

## Sprint 2: M1 — Markets + Research

> **目标**: 两个 Analytical Workspace 页面落地，建立该模式的可复用模式

### T1: Cross-Market Overview 落地 `[L]`

**参考蓝图**: Page 2 — Cross-Market Overview
**页面模式**: Analytical Workspace / Radar Variant

**子任务**:
1. MSW fixtures: overview、cross-matrix、macro-drivers、capital-rotation
2. MSW handlers: Markets 域 4 个 GET 端点
3. TanStack Query hooks: `useMarketOverview`, `useCrossMatrix`, `useMacroDrivers`, `useCapitalRotation`
4. 页面组件:
   - Context Bar (市态/波动/美元/预警)
   - Scope Strip (AI 今日解读)
   - Cross-Market Card Grid (6 卡片)
   - Cross-Market Matrix 表格
   - Macro Drivers Bar
   - Bottom Tab Band (资金轮动/事件日历/AI 解读)

**验收**: 6 张市场卡片显示 mock 数据，Matrix 表格可滚动

**文件**: ~10 files

---

### T2: Research Workspace 落地 `[L]`

**参考蓝图**: Page 5 — Research Workspace
**页面模式**: Analytical Overview Workspace

**子任务**:
1. MSW fixtures: research/pulse、factors、runs、experiments、review-queue
2. MSW handlers: Research 域 5 个 GET 端点
3. TanStack Query hooks
4. 页面组件:
   - Research Header
   - Pulse Strip
   - Factor Monitor Table (DittoGrid)
   - Recent Runs 列表
   - Experiments & Review Queue
   - Analysis Band

**验收**: Research 页面显示因子表格和实验列表

**文件**: ~10 files

---

### Sprint 2 依赖

```
T1 (Markets) ──> 依赖 Sprint 1 T1 模式
T2 (Research) ──> 依赖 Sprint 1 T1 模式（可并行）
```

**M1-2 交付标准**: Markets + Research 2 页端到端可用

---

## Sprint 3: M1 — Trading Overview + Markets Screener

> **目标**: 完成 Batch 1 全部 6 页交付

### T1: Trading Overview 落地 `[L]`

**参考蓝图**: Page 9 — Trading Overview
**页面模式**: Analytical Overview Workspace

**子任务**:
1. MSW fixtures: session、equity、positions、risk/summary、signals/queue、orders/summary
2. MSW handlers: Trading 域 6 个 GET 端点
3. TanStack Query hooks
4. 页面组件:
   - Trading Header + Session Strip (交易阶段 + 两融)
   - Equity & PnL 区块
   - Risk & Alerts 区块
   - Positions Summary 表格 (DittoGrid，含 T+1 冻结标识)
   - Signal Queue 预览
   - Order Status 预览

**验收**: Trading Overview 显示会话状态、持仓表格、信号预览

**文件**: ~10 files

---

### T2: Markets Screener 落地 `[L]`

**参考蓝图**: Page 3 — Markets Screener
**页面模式**: Catalog / Screener Workspace

**子任务**:
1. MSW fixtures: screener 结果列表、presets、columns
2. MSW handlers: screener 域 3 个 GET + 1 个 POST 端点
3. Zustand store: screener filter state (筛选条件持久化)
4. 页面组件:
   - Header + Saved Views
   - Filter Toolbar (使用已有 FilterToolbar + FilterChip)
   - Results Table (DittoGrid，含排序、分页)
   - Compare Cart 浮动面板
   - Scoring & Presets 侧栏

**验收**: Screener 可筛选、排序、分页，选择标的后出现 Compare Cart

**文件**: ~10 files

---

### Sprint 3 依赖

```
T1 (Trading) ──> 依赖 Sprint 2 模式
T2 (Screener) ──> 依赖 Sprint 0 T4 (Zustand) + Sprint 0 T5 (Charts 可选)
```

**M1 完整交付标准**: 6 页全部端到端可用，`bun run check` 通过

---

## Sprint 4: M2 — Instrument Hub + Signals Inbox

> **目标**: 建立 Object Hub 和 Queue 两种新页面模式

### T1: Instrument Hub 落地 `[L]`

**参考蓝图**: Page 4 — Instrument Hub
**页面模式**: Object Hub

**子任务**:
1. MSW fixtures: instrument detail、chart data、fundamentals、corporate-actions、announcements
2. MSW handlers: 5 个 GET 端点
3. TanStack Query hooks
4. 页面组件:
   - Object Header (含停牌/复牌标识)
   - Meta Strip (关键指标)
   - Tab Bar (概览/行情/态势/基本面/公司行动/新闻/关联网络/公告)
   - 各 Tab 内容面板
   - Related & Signals & Notes 侧栏
   - Timeline & Filings

**注意**: 这是 17 页中内容最丰富的页面之一，Tab 面板可先实现概览+行情两个核心 Tab

**验收**: Instrument Hub 显示标的信息，Tab 切换正常，行情 Tab 有图表

**文件**: ~14 files

---

### T2: Signals Inbox 落地 `[L]`

**参考蓝图**: Page 10 — Signals Inbox
**页面模式**: Queue / Ops Console

**子任务**:
1. MSW fixtures: signals 列表、signal detail
2. MSW handlers: 2 个 GET 端点
3. TanStack Query hooks + mutations (confirm/ignore)
4. 页面组件:
   - Signals Header
   - Scope Strip (待复核/已确认/已忽略/已转订单)
   - Signal Table (DittoGrid)
   - Signal Detail 面板
   - Order Confirmation Sheet (使用已有 Sheet 组件)

**验收**: 信号列表可筛选，点击信号显示详情，确认/忽略按钮可触发状态变更

**文件**: ~10 files

---

### Sprint 4 依赖

```
T1 (Instrument) ──> 依赖 Sprint 0 T5 (Charts)
T2 (Signals) ──> 依赖 Sprint 3 T1 (Trading hooks 可复用)
```

**M2-1 交付标准**: Instrument Hub + Signals Inbox 2 页端到端可用

---

## Sprint 5: M2 — Strategy Studio + Backtest Result

> **目标**: 完成 Batch 2 全部 4 页 + 1 个新增路由

### T1: Strategy Studio 落地 `[XL]` → 拆为 2 个子任务

**参考蓝图**: Page 7 — Strategy Studio
**页面模式**: Studio / Builder

#### T1.1: Strategy Studio 数据层 `[M]`
- MSW fixtures: strategies、versions、factor/library
- MSW handlers: 5 个 GET/PUT/POST 端点
- Zustand store: studio editor state (当前策略、dirty flag、mode)

#### T1.2: Strategy Studio 页面 `[L]`
- Studio Header
- Mode Switch (Form Builder / Code Editor)
- Sources Panel (因子库浏览器)
- Main Studio (表单编辑器)
- Inspector Panel (策略参数预览)
- Logs & Validate & Dry Run

**注意**: Code Editor 需要评估 Monaco Editor 或 CodeMirror，v1 可先用 textarea + syntax highlight

**验收**: 策略表单可编辑，校验按钮可触发，结果在 Inspector 中显示

**文件**: ~12 files

---

### T2: Backtest Result 落地 `[L]`

**参考蓝图**: Page 8 — Backtest Result
**页面模式**: Object Hub

**子任务**:
1. MSW fixtures: backtest 结果、NAV curve、trades、risk metrics、attribution
2. MSW handlers: backtest/$id 域 GET 端点
3. 页面组件:
   - Backtest Header
   - KPI Strip (Sharpe/年化/MDD/胜率/换手/总费用)
   - Tab 内容 (概览/收益/风险/交易/归因/诊断)
   - NAV + Drawdown 图表 (双轴)
   - 交易记录表格

**验收**: 回测结果页显示 KPI 指标和 NAV 曲线图表

**文件**: ~10 files

---

### T3: 新增路由注册 `[S]`

将 Sprint 0 T6 中的 `research/factors.$id` 和 `research/backtest.$id` 路由与 Sprint 4/5 的页面组件关联。

**验收**: `/research/backtest/123` 可访问回测结果页

**文件**: ~2 files (确认 Sprint 0 T6 已创建)

---

### Sprint 5 依赖

```
T1 (Studio) ──> 依赖 Sprint 0 T4 (Stores)
T2 (Backtest) ──> 依赖 Sprint 0 T5 (Charts)
T3 (路由) ──> 依赖 T1 + T2
```

**M2 完整交付标准**: 4 页端到端可用 + 路由补齐，`bun run check` 通过

---

## Sprint 6: M3 — Orders + Risk Center

> **目标**: 交易执行链路的关键页面

### T1: Orders Ledger 落地 `[L]`

**参考蓝图**: Page 11 — Orders / Execution Ledger
**页面模式**: Ledger / Execution Console

**子任务**:
1. MSW fixtures: orders 列表、order detail (trace)
2. MSW handlers: orders 域 GET/POST 端点
3. TanStack Query hooks + mutations (cancel/retry)
4. 页面组件:
   - Orders Header
   - Status Strip (待提交/已提交/部分成交/已完成/失败已撤单)
   - Orders Ledger Table (DittoGrid)
   - Order Trace 面板 (状态时间线 + 拒绝原因 + 费用)

**验收**: 订单表格可筛选、分页，点击订单显示 Trace 时间线

**文件**: ~10 files

---

### T2: Risk Center 落地 `[L]`

**参考蓝图**: Page 12 — Risk Center
**页面模式**: Analytical Overview Workspace

**子任务**:
1. MSW fixtures: var、drawdown、exposure、breaches、incidents、stress-test
2. MSW handlers: risk 域 GET/POST 端点
3. 页面组件:
   - Risk Header
   - Risk Strip (VaR/DD/Beta/Gross/Net/Near-Limit/Breach)
   - Main Risk Charts (VaR 时序、Exposure 饼图)
   - Active Breaches 表格
   - Stress Test Summary
   - Incident Timeline

**验收**: Risk 页面显示风控指标条和图表

**文件**: ~10 files

---

### Sprint 6 依赖

```
T1 (Orders) ──> 依赖 Sprint 4 T2 (Signals hooks 可复用)
T2 (Risk) ──> 依赖 Sprint 0 T5 (Charts)
```

---

## Sprint 7: M3 — AI 三页

> **目标**: AI 域三页落地，含最复杂的交互模式

### T1: AI Overview + AI Copilot `[XL]` → 拆为 2 个子任务

**参考蓝图**: Page 17 (AI Overview) + Page 13 (AI Copilot)
**页面模式**: Command Center + Studio / Builder

#### T1.1: AI Overview `[M]`
- MSW fixtures: AI pulse、agent quick-view、copilot quick-view
- 页面组件: AI Pulse + Agent Quick View + Copilot Quick View + AI Actions

#### T1.2: AI Copilot Studio `[L]`
- MSW fixtures: sessions、messages
- MSW handlers: copilot 域 GET/POST 端点 (含 SSE 模拟)
- Zustand store: conversation state
- 页面组件:
  - Copilot Header + Mode Switch
  - Sessions Panel (会话列表)
  - Conversation (消息列表 + 输入框 + Structured Output)
  - Context Panel

**注意**: SSE 流式对话需要模拟，可用 `ReadableStream` 在 MSW 中模拟

**验收**: AI Overview 显示概览卡片，Copilot 可发送消息并显示回复

**文件**: ~14 files

---

### T2: Agent Console 落地 `[L]`

**参考蓝图**: Page 14 — Agent Console
**页面模式**: Studio / Builder

**子任务**:
1. MSW fixtures: plans、runs、findings
2. MSW handlers: agent 域 GET/POST 端点
3. 页面组件:
   - Agent Header + Tabs (Plans/Runs/Findings/Approvals)
   - Main Queue & Cards
   - Detail & Tool Trace
   - AI Confidence 框架展示

**验收**: Agent Console 显示 Plan 列表，点击查看详情和审批操作

**文件**: ~10 files

---

### Sprint 7 依赖

```
T1 (AI Overview + Copilot) ──> 依赖 Sprint 0 T4 (Stores)
T2 (Agent Console) ──> 依赖 T1.1 (AI 域 hooks 可复用)
```

---

## Sprint 8: M3 — 补全页

> **目标**: 补齐剩余 4 页 + 4 个新增路由页，实现全域覆盖

### T1: Regime Monitor `[M]`

**参考蓝图**: Page 16 — Regime Monitor (轻量蓝图)
**页面模式**: Analytical Workspace (Chart-first)

**子任务**:
1. MSW fixtures: regime/current、drivers、history、strategy-impact
2. 页面组件: Regime Status Strip + Indicator (三状态仪表) + Drivers Panel + History

**文件**: ~6 files

---

### T2: Markets Intelligence `[L]`

**参考蓝图**: Page 2.2 — Markets Intelligence
**页面模式**: Analytical Overview Workspace (Tab 视图)

**子任务**:
1. MSW fixtures: intelligence/flow、macro、fundamentals、news、network
2. 页面组件: Tab View (资金面/宏观/基本面/新闻/关联网络) + Right Rail + Analysis Band

**文件**: ~8 files

---

### T3: A-Shares Overview + Markets Calendar `[L]`

**参考蓝图**: Page 2.1 (A-Shares) + Page 4.2 (Calendar)

**子任务**:
1. A-Shares: MSW fixtures + 页面 (Header + Context Bar + Market Structure Map + Index Summary + ETF Matrix + Movers)
2. Calendar: MSW fixtures + 页面 (A 股事件日历 + 经济数据日历 + Filter Bar)

**验收**: A-Shares 页面显示市场结构，Calendar 显示事件列表

**文件**: ~10 files

---

### T4: Factor Analysis + Strategy Detail `[L]`

**参考蓝图**: Page 6 (Factor Analysis) + Strategy Object Hub

**子任务**:
1. Factor Analysis: MSW fixtures + 页面 (KPI Strip + Tabs + 2x2 Diagnostics)
2. Strategy Detail (`/strategies/$id`): 复用 Object Hub 模式 + 策略信息展示

**文件**: ~8 files

---

### Sprint 8 依赖

```
T1 (Regime) ──> 依赖 Sprint 0 T5 (Charts)
T2 (Intelligence) ──> 依赖 Sprint 2 T1 (Markets hooks 可复用)
T3 (A-Shares + Calendar) ──> 依赖 Sprint 2 T1 模式
T4 (Factor + Strategy) ──> 依赖 Sprint 5 T1 (Strategy hooks 可复用)
```

**M3 完整交付标准**: 17 页 + 4 补全页全部端到端可用，`bun run check` 通过

---

## 全局依赖图

```
Sprint 0 (数据基础设施)
  ├─ T1 类型 ──────────────────────────────────────┐
  ├─ T2 MSW ───────────────────────────────────────┤
  ├─ T3 Hooks ─────────────────────────────────────┤
  ├─ T4 Stores ────────────────────────────────────┤
  ├─ T5 Charts ────────────────────────────────────┤
  └─ T6 路由补齐 ──────────────────────────────────┤
                                                     │
Sprint 1 (Platform + Home) ◄────────────────────────┘
Sprint 2 (Markets + Research) ◄── Sprint 1 模式
Sprint 3 (Trading + Screener) ◄── Sprint 2 模式
  │
  ├── M1 交付 ✓ (6 页)
  │
Sprint 4 (Instrument + Signals) ◄── Sprint 3 数据
Sprint 5 (Studio + Backtest) ◄── Sprint 4 模式
  │
  ├── M2 交付 ✓ (4 页 + 路由)
  │
Sprint 6 (Orders + Risk) ◄── Sprint 5 模式
Sprint 7 (AI 三页) ◄── Sprint 6 模式
Sprint 8 (补全 4+4 页) ◄── Sprint 7 模式
  │
  ├── M3 交付 ✓ (全域 21 页)
```

---

## 总量预估

| 维度 | 数量 |
|------|------|
| Sprint | 9 个 (Sprint 0-8) |
| 里程碑 | 3 个 (M1/M2/M3) |
| 页面 | 21 个 (17 蓝图 + 4 补全) |
| 新增文件 | ~180 files |
| 预估测试 | ~800-1000 用例 (在现有 400 基础上) |
| 需新增依赖 | 图表库 (1-2 个)、可选 Monaco Editor |

---

## 风险与决策点

| 风险 | 影响 | 缓解 |
|------|------|------|
| 图表库选型 | 影响所有图表页面 | Sprint 0 T5 必须先决 |
| Monaco/CodeMirror | Strategy Studio 复杂度 | v1 用 textarea 降级 |
| SSE 流式模拟 | AI Copilot 对话体验 | MSW + ReadableStream |
| 17 页交互状态 | 工作量巨大 | 四态处理在每个页面 Sprint 内完成 |
| Mock 数据逼真度 | 影响视觉还原质量 | fixtures 需要手动调优 |

# Cross-Market Overview 实施计划

## 概述
- Sprint: 1 | Phase: Markets 域基础
- 创建: 2026-03-29
- 设计文档: `docs/plans/2026-03-29-cross-market-overview-design.md`

## 技术方案

### 关键决策
1. **Feature 目录**: `src/features/cross-market/` — 页面级组件 + hooks + types
2. **Shell 布局**: `src/components/layouts/radar-shell.tsx` — 跨 feature 共享的 Radar Shell 布局
3. **数据层**: TanStack Query hook + MSW mock handler，v1 不接真实 API
4. **状态管理**: TimeFrame 用 React useState（页面级局部状态），不引入 Zustand
5. **样式**: Tailwind CSS v4 utility classes + `@theme inline` 定义基础 tokens
6. **shadcn 组件**: 按需安装（button, badge, tabs, collapsible, separator）

### 目录结构（最终态）

```
src/
├── components/
│   ├── ui/                          ← shadcn 自动生成
│   │   ├── button.tsx
│   │   ├── badge.tsx
│   │   ├── tabs.tsx
│   │   ├── collapsible.tsx
│   │   └── separator.tsx
│   └── layouts/
│       ├── radar-shell.tsx          ← Radar Shell 布局容器
│       └── index.ts
├── features/
│   └── cross-market/
│       ├── components/
│       │   ├── workspace-header.tsx
│       │   ├── context-bar.tsx
│       │   ├── scope-strip.tsx
│       │   ├── market-card.tsx
│       │   ├── cross-market-card-grid.tsx
│       │   ├── cross-market-matrix.tsx
│       │   ├── macro-drivers-bar.tsx
│       │   ├── market-pulse-summary.tsx
│       │   ├── risk-and-alerts-panel.tsx
│       │   ├── upcoming-events-panel.tsx
│       │   ├── drilldown-recommendations.tsx
│       │   ├── capital-rotation-tab.tsx
│       │   ├── event-calendar-tab.tsx
│       │   ├── ai-insight-tab.tsx
│       │   └── bottom-tab-band.tsx
│       ├── hooks/
│       │   └── use-cross-market-data.ts
│       ├── mock-data.ts
│       ├── types.ts
│       └── index.ts
├── routes/
│   ├── __root.tsx                   ← 更新：添加 Rail nav
│   ├── markets/
│   │   ├── index.tsx                ← 新增：/markets
│   │   └── a-shares.tsx             ← 新增：/markets/a-shares（占位）
│   └── index.tsx                    ← 不变
└── styles/
    └── globals.css                  ← 更新：添加基础 tokens
```

---

## 任务清单

### Phase 0: 基础设施

- [ ] **Task: 定义基础 Design Tokens** `[M]`
  - 验收: `globals.css` 中有 `@theme inline` 块，包含颜色、间距、字体、圆角等基础变量；`bunx biome check .` 通过
  - 文件: `src/styles/globals.css`
  - 测试: 无需单元测试（CSS 变量），视觉验证

- [ ] **Task: 安装 shadcn/ui 基础组件** `[S]`
  - 验收: `src/components/ui/` 下存在 button、badge、tabs、collapsible、separator；`bun run check` 通过
  - 命令: `bunx shadcn@latest add button badge tabs collapsible separator`
  - 文件: `src/components/ui/*.tsx`
  - 测试: shadcn 组件自带测试保障

- [ ] **Task: 创建 RadarShell 布局组件** `[M]`
  - 验收: 渲染 70/30 CSS Grid 布局，包含 header / context / scope / main / right-rail / tabs 六个 grid area；响应式断点生效
  - 文件: `src/components/layouts/radar-shell.tsx`, `src/components/layouts/radar-shell.test.tsx`
  - 测试: 渲染子元素到正确 grid area；接受 `header` / `context` / `scope` / `main` / `right-rail` / `tabs` props

- [ ] **Task: 配置 /markets 路由** `[S]`
  - 验收: 访问 `/markets` 渲染页面占位；访问 `/markets/a-shares` 渲染占位；路由树正确生成
  - 文件: `src/routes/markets/index.tsx`, `src/routes/markets/a-shares.tsx`
  - 测试: 路由渲染测试（router provider + memory router）

### Phase 1: 类型 + 数据层

- [ ] **Task: 定义 TypeScript 类型** `[M]`
  - 验收: `bunx tsc --noEmit` 零错误；所有设计文档 §5.1 中的类型都有导出
  - 文件: `src/features/cross-market/types.ts`, `src/features/cross-market/types.test.ts`
  - 测试: 类型编译验证（type-level test，用 `expectType` 或 `satisfies`）

- [ ] **Task: 创建 Mock 数据** `[M]`
  - 验收: 导出 `mockCrossMarketData` 对象，覆盖所有字段；导出 `mockRiskOffData` 场景变体
  - 文件: `src/features/cross-market/mock-data.ts`, `src/features/cross-market/mock-data.test.ts`
  - 测试: mock 数据符合类型约束；字段完整无 undefined

- [ ] **Task: 实现 TanStack Query hook** `[M]`
  - 验收: `useCrossMarketData()` 返回 `CrossMarketOverviewData`；支持 `timeFrame` 参数切换
  - 文件: `src/features/cross-market/hooks/use-cross-market-data.ts`, `src/features/cross-market/hooks/use-cross-market-data.test.ts`
  - 测试: 使用 `renderHook` + MSW 验证数据返回；timeFrame 参数传递

### Phase 2: Shell 级组件

- [ ] **Task: 实现 WorkspaceHeader** `[S]`
  - 验收: 渲染页面标题、TimeFrameSelector（1D/1W/1M）、刷新时间戳、视图密度切换
  - 文件: `src/features/cross-market/components/workspace-header.tsx`, `workspace-header.test.tsx`
  - 测试: 渲染标题文本；timeFrame 点击触发 onChange；密度切换触发 onChange

- [ ] **Task: 实现 ContextBar** `[M]`
  - 验收: 渲染 5-6 个 ContextPill（label + value）；AlertBadge 渲染数字；regime 值显示语义色
  - 文件: `src/features/cross-market/components/context-bar.tsx`, `context-bar.test.tsx`
  - 测试: 渲染正确数量 pill；regime Risk-On 显示正向色；alertCount 正确显示

- [ ] **Task: 实现 ScopeStrip** `[S]`
  - 验收: 渲染 4-6 个 ScopeChip；强势 chip 为正向色，承压 chip 为负向色，风险事件为警示色
  - 文件: `src/features/cross-market/components/scope-strip.tsx`, `scope-strip.test.tsx`
  - 测试: 渲染正确数量 chip；各 type 应用正确颜色类

### Phase 3: 主工作面组件

- [ ] **Task: 实现 MarketCard** `[M]`
  - 验收: 渲染市场名 + regime tag + 指数 + 变化量 + 驱动摘要 + 下钻按钮；hover 时 border 高亮；整个卡片可点击
  - 文件: `src/features/cross-market/components/market-card.tsx`, `market-card.test.tsx`
  - 测试: 渲染所有字段；点击触发 onDrilldown；变化量正负显示正确颜色；regime tag 显示正确色

- [ ] **Task: 实现 CrossMarketCardGrid** `[S]`
  - 验收: 3×2 grid 渲染 6 张 MarketCard；接受 `highlightedMarketId` prop 实现联动高亮
  - 文件: `src/features/cross-market/components/cross-market-card-grid.tsx`, `cross-market-card-grid.test.tsx`
  - 测试: 渲染 6 张卡片；highlightedMarketId 对应卡片添加高亮类

- [ ] **Task: 实现 CrossMarketMatrix** `[L]`
  - 验收: 渲染表头（1D/1W/1M/Vol/Breadth/Flow）和数据行；数值正负用颜色梯度；行 hover 触发 onMarketHover
  - 文件: `src/features/cross-market/components/cross-market-matrix.tsx`, `cross-market-matrix.test.tsx`
  - 测试: 渲染正确行列数；正负值颜色正确；hover 触发回调；`-` 值不渲染颜色

- [ ] **Task: 实现 MacroDriversBar** `[M]`
  - 验收: 水平渲染 7 个 MacroDriverBlock；每个 block 显示名称 + 值 + 变化量 + 解释标签；变化量正负颜色正确
  - 文件: `src/features/cross-market/components/macro-drivers-bar.tsx`, `macro-drivers-bar.test.tsx`
  - 测试: 渲染 7 个 block；变化量颜色正确；解释标签渲染

### Phase 4: 右 Rail 组件

- [ ] **Task: 实现 MarketPulseSummary** `[S]`
  - 验收: 渲染 4-5 行市场脉搏（市场名 + 状态）；每行一行文本
  - 文件: `src/features/cross-market/components/market-pulse-summary.tsx`, `market-pulse-summary.test.tsx`
  - 测试: 渲染正确行数；文本包含市场名和状态

- [ ] **Task: 实现 RiskAndAlertsPanel** `[S]`
  - 验收: 渲染 3-4 条风险提示；high/medium/low 用不同标识；支持折叠
  - 文件: `src/features/cross-market/components/risk-and-alerts-panel.tsx`, `risk-and-alerts-panel.test.tsx`
  - 测试: 渲染正确条数；severity 标识正确

- [ ] **Task: 实现 UpcomingEventsPanel** `[S]`
  - 验收: 渲染 3-5 条事件（时间 + 名称 + 影响市场）；importance high 用高亮
  - 文件: `src/features/cross-market/components/upcoming-events-panel.tsx`, `upcoming-events-panel.test.tsx`
  - 测试: 渲染正确条数；高 importance 事件有视觉区分

- [ ] **Task: 实现 DrilldownRecommendations** `[S]`
  - 验收: 渲染 3 条推荐（理由 + 下钻按钮）；点击按钮触发导航
  - 文件: `src/features/cross-market/components/drilldown-recommendations.tsx`, `drilldown-recommendations.test.tsx`
  - 测试: 渲染 3 条推荐；按钮点击触发 onDrilldown

### Phase 5: 底部 Tab Band

- [ ] **Task: 实现 CapitalRotationTab** `[S]`
  - 验收: 渲染 3 个 KPI + 流入/流出 top3 + 总结文案
  - 文件: `src/features/cross-market/components/capital-rotation-tab.tsx`, `capital-rotation-tab.test.tsx`
  - 测试: 渲染 KPI 值；渲染流入/流出列表

- [ ] **Task: 实现 EventCalendarTab** `[S]`
  - 验收: 按时间分组（今夜/明日/本周）渲染事件；每条含名称 + 影响市场 + 共识
  - 文件: `src/features/cross-market/components/event-calendar-tab.tsx`, `event-calendar-tab.test.tsx`
  - 测试: 按分组渲染；事件字段完整

- [ ] **Task: 实现 AIInsightTab** `[S]`
  - 验收: 渲染 3 条洞察（发生了什么 / 为什么重要 / 该看哪里）
  - 文件: `src/features/cross-market/components/ai-insight-tab.tsx`, `ai-insight-tab.test.tsx`
  - 测试: 渲染 3 条洞察；每个含 3 个字段

- [ ] **Task: 实现 BottomTabBand** `[S]`
  - 验收: 3 个 tab 切换；默认显示资金轮动；内容区固定高度可滚动
  - 文件: `src/features/cross-market/components/bottom-tab-band.tsx`, `bottom-tab-band.test.tsx`
  - 测试: 默认选中第一个 tab；切换 tab 更新内容

### Phase 6: 页面组装

- [ ] **Task: 组装 CrossMarketOverviewPage** `[L]`
  - 验收: 所有组件在 RadarShell 内正确组装；TimeFrame 切换更新 MarketCard 和 Matrix；Matrix hover 联动 MarketCard 高亮；BottomTab 默认显示资金轮动
  - 文件: `src/routes/markets/index.tsx`, `src/features/cross-market/index.ts`
  - 测试: 集成渲染测试；TimeFrame 切换传递到子组件；hover 联动工作

- [ ] **Task: 创建 /markets/a-shares 占位页** `[S]`
  - 验收: 访问 `/markets/a-shares` 显示"A 股总览 — 开发中"占位内容
  - 文件: `src/routes/markets/a-shares.tsx`
  - 测试: 路由渲染占位文本

- [ ] **Task: 最终验证** `[S]`
  - 验收: `bun run check` 全部通过（tsc + biome + vitest）；测试覆盖率 ≥ 80%；页面在浏览器可访问
  - 命令: `bun run check`, `bun run test --coverage`
  - 文件: 无新增

---

## 依赖关系

```
Phase 0 (基础设施)
  ├─ Design Tokens ← 无依赖
  ├─ shadcn 组件 ← 无依赖
  ├─ RadarShell ← Design Tokens
  └─ 路由配置 ← 无依赖

Phase 1 (类型 + 数据)
  ├─ Types ← 无依赖
  ├─ Mock Data ← Types
  └─ Query Hook ← Types + Mock Data + MSW

Phase 2 (Shell 组件)
  ├─ WorkspaceHeader ← 无依赖
  ├─ ContextBar ← Types
  └─ ScopeStrip ← Types

Phase 3 (主工作面) ← Phase 1 + Phase 2
  ├─ MarketCard ← Types
  ├─ CardGrid ← MarketCard
  ├─ Matrix ← Types
  └─ DriversBar ← Types

Phase 4 (Right Rail) ← Phase 1
  ├─ PulseSummary ← Types
  ├─ RiskAlerts ← Types
  ├─ UpcomingEvents ← Types
  └─ Drilldown ← Types

Phase 5 (Bottom Tabs) ← Phase 1
  ├─ CapitalRotation ← Types
  ├─ EventCalendar ← Types
  ├─ AIInsight ← Types
  └─ TabBand ← 三个 Tab

Phase 6 (组装) ← Phase 2-5
  ├─ CrossMarketOverviewPage ← 所有组件
  ├─ a-shares 占位 ← 路由配置
  └─ 最终验证 ← 全部
```

## 并行机会

以下任务组可并行开发（无相互依赖）：
- Phase 2 的三个组件（WorkspaceHeader / ContextBar / ScopeStrip）
- Phase 3 的四个组件（MarketCard / CardGrid / Matrix / DriversBar）
- Phase 4 的四个组件（PulseSummary / RiskAlerts / UpcomingEvents / Drilldown）
- Phase 5 的四个组件（三个 Tab + TabBand）
- Phase 3 + Phase 4 + Phase 5 可完全并行

## 任务统计

| Phase | 任务数 | S | M | L | 预估组件数 |
|-------|--------|---|---|---|-----------|
| Phase 0 | 4 | 1 | 2 | 0 | 3 |
| Phase 1 | 3 | 0 | 3 | 0 | 3 |
| Phase 2 | 3 | 1 | 1 | 0 | 3 |
| Phase 3 | 4 | 1 | 2 | 1 | 4 |
| Phase 4 | 4 | 4 | 0 | 0 | 4 |
| Phase 5 | 4 | 4 | 0 | 0 | 4 |
| Phase 6 | 3 | 1 | 0 | 1 | 2 |
| **合计** | **25** | **12** | **8** | **2** | **23** |

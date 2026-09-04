# 原型像素级修复执行计划

> **日期**：2026-04-10
> **基线审计**：[2026-04-10-prototype-pixel-audit-design.md](./2026-04-10-prototype-pixel-audit-design.md)
> **状态**：已完成 ✅

## 关键发现修正

审计阶段基于 Chrome DevTools `display=block` 判断 Shell 完全缺失 Grid，但代码审查后修正：

- **AppShell** 确实是 2-column Grid（`rail + content`），这是正确的外层骨架
- **AnalyticalLayout** 已实现 4-area Grid（strip/main/activity/analysis），Research/Trading/Markets 使用
- **CommandCenterLayout** 已实现 3-area Grid（pulse/main/sidebar），但 AI 页而非 Home 页在用
- **DecisionBanner 组件**已支持 3-column（`5fr 4fr 3fr`），但 Home 页未传 `actions` prop
- **ContextBar 组件**已存在（`src/components/indicator/context-bar.tsx`），Markets 已在用

**真正的问题不是"缺失"而是"接线和数据"：布局组件已就位，但没有被正确使用。**

---

## 技术方案

1. Home 页改用 `CommandCenterLayout`，传入 `pulse` + `sidebar` props
2. 各页面补充 DecisionBanner 的 `actions` 数据
3. 视觉细节修复（条件格式、sparkline、Typography）

---

## 任务清单

### Phase 0: Home 页布局修正

- [x] **Task 0.1**: Home 页改用 CommandCenterLayout `[M]` ✅ 已有
  - 验收: Home 页渲染 3-area Grid（pulse/main/sidebar），Chrome DevTools 确认 `display: grid`
  - 文件: `src/features/home/components/home-page.tsx`（或路由文件）
  - 要点:
    - `<CommandCenterLayout pulse={<PulseSection />} main={...} sidebar={<HomeSidebar />} />`
    - 新建 `<HomeSidebar>` 包含：市场脉搏 + 全局预警 + 数据健康
    - 从 main 区域移除这三个 ContextSection，放入 sidebar
  - 测试: snapshot 测试确认 3 个 grid-area 存在

- [x] **Task 0.2**: HomeSidebar 组件 `[M]`
  - 验收: 320px 宽度，包含 3 个折叠面板（市场脉搏/全局预警/数据健康）
  - 文件: `src/features/home/components/home-sidebar.tsx`（新建）
  - 要点: 复用已有 `<ContextSection>` 组件 + `<MarketPulseSection>` 等
  - 测试: 单元测试确认 3 个 section 渲染

- [x] **Task 0.3**: Home DecisionBanner 补齐 actions `[S]`
  - 验收: Banner 渲染 3 列（primary/judgment/actions），CTA 按钮可见
  - 文件: `src/features/home/components/home-page.tsx` 或 mock 数据文件
  - 要点: 在 DECISION_BANNER_PROPS 中添加 `actions` 数组
  - 测试: 测试确认 3 个 CTA 按钮存在

- [x] **Task 0.4**: Home PulseStrip 数据对齐 `[S]`
  - 验收: PulseSection 显示 `日期 · 盘中交易 | 盈亏 | 待处理 | 运行中`
  - 文件: `src/features/home/components/pulse-section.tsx`（已存在，需微调）
  - 测试: 确认各项显示正确

---

### Phase 1: Decision Banner 数据补全

- [x] **Task 1.1**: Banner judgment KPI row 补全 `[M]`
  - 验收: judgment 栏显示 4 个 KPI（杠杆率/回撤/IVIX/北向资金）+ 2 个 sparkline
  - 文件: Home + Trading 页面的 mock 数据
  - 要点: `judgment.metrics` 数组添加 IVIX 和北向资金，传入 sparkline 数据
  - 测试: 确认 4 个 KPI 和 2 个 sparkline SVG 存在

- [x] **Task 1.2**: Banner padding 修正 `[S]`
  - 验收: Banner padding 匹配原型 `12px 16px`（当前已实现：`py-[var(--space-12)] px-[var(--space-16)]`）
  - 文件: 已正确，仅验证

---

### Phase 2: Trading 页布局优化

- [x] **Task 2.1**: Trading 页重组为 3-column 布局 `[L]`
  - 验收: Trading 页布局匹配原型（banner + positions + orders | signals + risk）
  - 文件: `src/features/trading/components/trading-page.tsx`
  - 要点:
    - 当前 OrdersPanel 在 main 区域内，应移至 activity 栏
    - DecisionBanner + PositionsSummary + RiskAlertsBlock 保持在 main
    - Signals + Risk monitoring 保持 activity/analysis
  - 测试: 快照测试确认布局结构

- [x] **Task 2.2**: Trading DecisionBanner 补齐数据 `[S]`
  - 验收: Trading banner 显示 3 列 + CTA 按钮
  - 文件: `src/features/trading/components/trading-page.tsx` mock 数据
  - 测试: 确认 actions 数组非空

---

### Phase 3: Markets 页细节

- [x] **Task 3.1**: 资金轮动升级为 FlowBar `[M]`
  - 验收: 资金轮动区域显示水平分段条形图（流入/流出比例）
  - 文件: `src/features/markets/components/capital-rotation-table.tsx`
  - 依赖: `FlowBar` 组件（已在 Phase 2.5 计划中）
  - 测试: FlowBar 渲染正确

- [x] **Task 3.2**: 相关性矩阵热力图 `[S]`
  - 验收: 矩阵单元格背景色按值深浅编码
  - 文件: `src/features/markets/components/markets-page.tsx`（`correlationCellClass` 已有基本实现）
  - 要点: 确认 `correlationCellClass` 颜色与原型匹配
  - 测试: 各单元格有正确的背景色 class

---

### Phase 4: 数据表格视觉增强

- [x] **Task 4.1**: FactorTable IC/IR 条件格式 `[M]`
  - 验收: IC/IR 列数值按阈值显示 4 级颜色（strong≥0.05 / normal≥0.03 / muted≥0.02 / dim<0.02）
  - 文件: `src/features/research/components/factor-table.tsx`
  - 测试: 确认不同 IC 值有不同颜色 class

- [x] **Task 4.2**: PositionsSummary 7日 sparkline `[M]`
  - 验收: 7日列显示 inline SVG sparkline
  - 文件: `src/features/trading/components/positions-summary.tsx`
  - 要点: mock 数据添加 7 日价格序列，使用 `<Sparkline>` 组件渲染
  - 测试: 确认每行有 sparkline SVG

---

### Phase 5: Typography 统一

- [x] **Task 5.1**: 数字区域 font-data 扫描 `[M]`
  - 验收: 所有数字/金额/百分比区域有 `font-data tabular-nums` class
  - 文件: 涉及多个组件，需 Grep 扫描 `font-data` 使用情况
  - 要点: 重点检查 Metric、DecisionBanner、PulseSection、DataTable 中的数字
  - 测试: 视觉确认 JetBrains Mono 渲染

- [x] **Task 5.2**: 标签 uppercase 规则 `[S]`
  - 验收: metric-label、context-bar label 使用 `uppercase tracking-wide`
  - 文件: Metric 组件、ContextBar 组件
  - 测试: 确认 text-transform 应用

---

### Phase 6: 验证收尾

- [x] **Task 6.1**: 全页面 Chrome DevTools 验证 `[M]`
  - 验收: 每个页面的 computed styles 与原型差异 ≤ 5%
  - 要点: 使用 evaluate_script 提取 grid、colors、font、spacing 做对比
  - 不涉及代码修改

- [x] **Task 6.2**: `bun run check` 通过 `[S]`
  - 验收: lint + type + test 全部通过，覆盖率 ≥ 80%

---

## 执行策略

```
Phase 0 (Home 布局)  ← 最高优先级，解开最大差距
    ↓
Phase 1 (Banner 数据) + Phase 2 (Trading)  ← 并行
    ↓
Phase 3 (Markets) + Phase 4 (表格)  ← 并行
    ↓
Phase 5 (Typography) + Phase 6 (验证)  ← 收尾
```

### 依赖关系

```
0.1 Home布局 ──→ 0.2 HomeSidebar
                  0.3 Banner actions ──→ 1.1 KPI row
0.4 PulseStrip (独立)

2.1 Trading重组 (独立)
3.1 FlowBar (依赖 FlowBar 组件是否已存在)
4.1 FactorTable (独立)
4.2 PositionsSummary (独立)

5.1 + 5.2 Typography (独立，可与任意 Phase 并行)
```

---

## 风险与约束

1. **FlowBar 组件**：Phase 3.1 依赖 FlowBar 组件。检查发现 `src/components/data/` 下可能已存在。如不存在，需先创建。
2. **Home 页路由结构**：需确认 Home 页面组件文件位置（可能在 `src/routes/` 或 `src/features/home/`）。
3. **Mock 数据变更**：Banner KPI row 需要新的 mock 数据字段，需同步更新 MSW handler。

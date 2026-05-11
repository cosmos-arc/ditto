# 原型设计优化 — 视觉激活与交互增强

## 概述
- 创建: 2026-05-07
- 范围: 仅原型 HTML/CSS（`docs/designs/specs/prototypes/`）
- 目标: 将列表页从"纯文本表格"提升为"数据扫描面板"，增强核心页面交互深度

## 技术方案

### 关键决策

1. **共享样式先行**: 在 `shared/layout-components.css` 中新增通用组件样式（heat-bg、inline-bar、cell-sparkline），各页面引用而非各自实现
2. **数据内联**: 列表页数据已硬编码在 HTML 中，新增的 sparkline/heat 编码也直接内联，不走 mock-data.js
3. **渐进增强**: 不改动现有布局结构，仅在现有 `<td>` 中追加可视化元素

### 复用已有基础设施

| 组件 | 位置 | 用途 |
|------|------|------|
| `.cell-sparkline` | layout-components.css:1601 | 60×20 容器，当前为空壳 → 填充 SVG |
| `.confidence-bar` | layout-components.css:1931 | 48px bar → 扩展为通用 inline-bar |
| `--heatmap-1-bg` ~ `--heatmap-5-bg` | tokens-data-viz.css:48-52 | 热力色 5 级梯度 |
| `.cell-change-up/down` | layout-components.css:1550-1558 | 方向色 → 扩展 heat-bg 变体 |

---

## Phase 1: 共享组件扩展

> 所有页面优化依赖的通用样式，必须最先完成。

### Task 1.1: 新增 heat-bg 热力背景工具类 `[S]`

- **验收**: 5 个 heat-bg 类可用，映射到 `--heatmap-*-bg` token
- **文件**: `shared/layout-components.css`（追加在 `.cell-change-flat` 之后，约 L1560）
- **改动**:
  ```css
  /* Heat-bg — table cell background tinting */
  .heat-bg-1 { background: var(--heatmap-1-bg); }
  .heat-bg-2 { background: var(--heatmap-2-bg); }
  .heat-bg-3 { background: var(--heatmap-3-bg); }
  .heat-bg-4 { background: var(--heatmap-4-bg); }
  .heat-bg-5 { background: var(--heatmap-5-bg); }
  ```
- **验收方式**: 在任一列表页 td 上添加 `heat-bg-1` class 可看到背景染色

### Task 1.2: 新增 inline-micro-bar 组件 `[S]`

- **验收**: 可在 td 内嵌 48px 宽度的水平 bar，支持 market-up/market-down 色
- **文件**: `shared/layout-components.css`（追加在 `.confidence-bar-fill` 之后，约 L1948）
- **改动**:
  ```css
  /* Inline micro-bar — compact proportional indicator */
  .micro-bar {
    display: inline-block;
    width: 48px;
    height: 4px;
    background: var(--neutral-200);
    border-radius: var(--radius-2);
    vertical-align: middle;
    margin-left: var(--space-4);
  }
  .micro-bar-fill {
    display: block;
    height: 100%;
    border-radius: inherit;
  }
  .micro-bar-fill.up { background: var(--market-up-fg); }
  .micro-bar-fill.down { background: var(--market-down-fg); }
  .micro-bar-fill.accent { background: var(--brand-accent); }
  .micro-bar-fill.risk { background: var(--risk-critical-fg); }
  ```
- **验收方式**: 在 strategy-list Sharpe 列 td 内添加可渲染

### Task 1.3: 实现 cell-sparkline SVG 填充 `[M]`

- **验收**: `.cell-sparkline` 从空壳变为渲染 60×20 SVG 迷你折线图，支持 up/down/accent 三色
- **文件**: `shared/layout-components.css`（替换 L1601-1606 的空壳定义）
- **改动**: 定义 `.cell-sparkline svg` 的 polyline/area 样式；`--spark-stroke` / `--spark-fill` CSS 变量区分方向色
- **注意**: 实际 SVG polyline 的 points 属性需在每个 td 中硬编码（原型不需要动态数据）
- **参考**: page-strategy-list detail panel 的 equity-sparkline（L573-576）作为 SVG 结构模板

---

## Phase 2: 列表页视觉激活（6 页面）

> 按视觉影响力从高到低排序。每个页面独立可执行。

### Task 2.1: Watchlist 信号强化 `[M]`

- **验收**: Watchlist 表格行内已有 signal-mix bar（当前仅 detail panel 有），direction arrow 颜色编码完整
- **文件**: `page-watchlist.html`
- **改动**:
  - Price 列添加 inline sparkline（复用 Task 1.3 的 cell-sparkline）
  - Signal 列的 buy/sell/hold pill 已有颜色编码 ✓（保持）
  - Summary strip 的 signal-mix bar 移入表格行内（或新增迷你版本）
  - Stale 行的 `opacity: 0.6` + `filter: saturate(0.4)` 已有 ✓（保持）

### Task 2.2: Factor List IC 热力编码 `[M]`

- **验收**: IC 列和 IR 列有 heat-bg 背景，Decay 列有颜色 bar
- **文件**: `page-factor-list.html`
- **改动**:
  - IC 列 td（L533, 548, 563...共 12 个）: 按 IC 值 0.018~0.062 映射到 heat-bg-1~5（低→红，高→绿）
  - IR 列 td（L534, 549, 564...共 12 个）: 同上
  - Decay 列: 已有 decay-ok/watch/risk 色码 ✓；追加 micro-bar-fill 可视化 decay 程度
  - Health pill 已有色码 ✓（保持）

### Task 2.3: Backtest List MDD/Sharpe 可视化 `[M]`

- **验收**: MDD 列有红色深度编码 + inline bar，Sharpe 列有绿色深度编码
- **文件**: `page-backtest-list.html`
- **改动**:
  - Sharpe 列 td（L385, 401, 417...共 10 个）: 值 0.35~2.12 → heat-bg 映射（低=灰，高=绿）
  - MDD 列 td（L387, 403, 419...共 10 个）: 值 -4.9%~-28.6% → heat-bg 映射（浅=低风险，深=高风险）+ micro-bar-fill.down 显示比例
  - Return 列: 已有 cell-change-up/down ✓（保持）
  - Summary strip 追加 best Sharpe 高亮标记

### Task 2.4: Strategy List 净值 sparkline + MDD bar `[M]`

- **验收**: Last Run 列有迷你净值 sparkline，MDD 列有 inline bar + 颜色编码
- **文件**: `page-strategy-list.html`
- **改动**:
  - Last Run 列（或新增一列 "趋势"）: 添加 cell-sparkline SVG
  - MDD 列 td（L371, 386, 401...共 12 个）: 追加 micro-bar-fill.risk
  - Sharpe 列: heat-bg 映射
  - Status pill.active 已有绿色 dot ✓（保持）

### Task 2.5: Experiment List 显著性 bar `[S]`

- **验收**: Significance 列从 dot+text 升级为 dot+text+confidence bar
- **文件**: `page-experiment-list.html`
- **改动**:
  - Sig 列 td（L470, 485, 500...共 10 个）: 在 `.sig-indicator` 后追加 micro-bar，宽度 = `(1 - p值)` 的百分比
  - p<0.05 → micro-bar-fill.up（绿色）；p>0.05 → 灰色
  - "computing" / "pending" 状态保持无 bar

### Task 2.6: Universe List 组成可视化 `[M]`

- **验收**: 表格行内显示成分股分布条（替代纯文本 "1,932 instruments"）
- **文件**: `page-universe-list.html`
- **改动**:
  - 成分数量列: 追加 inline bar 表示相对规模
  - Source pill（index/custom/screen）已有色码 ✓（保持）
  - Freshness badge 已有 dot ✓（保持）
  - Summary strip: 数值指标追加 mini bar 比例图

---

## Phase 3: 核心页面交互增强

### Task 3.1: Home — Global Pulse 分组 `[S]`

- **验收**: 8 个 pulse 指标按 [账户健康|风控状态|运营] 三组显示，组间有分隔线
- **文件**: `page-home.html`
- **改动**:
  - Global Pulse strip（主内容区上方）: 3 组间添加 `border-left: 1px solid var(--border-subtle)`
  - 组标题: 不需要显式文字标签，通过视觉分隔暗示分组
  - 相关指标物理相邻: Equity + PnL | Risk + VaR | Pending + Execution + Model + Data

### Task 3.2: Home — Sidebar Activity Feed 色条 `[S]`

- **验收**: Activity feed 每个事件左侧有语义色竖线（2px）
- **文件**: `page-home.html`
- **改动**:
  - 信号类事件: `border-left: 2px solid var(--market-up-fg)` 或 `var(--market-down-fg)`
  - 风控类事件: `border-left: 2px solid var(--risk-critical-fg)`
  - 数据类事件: `border-left: 2px solid var(--system-degraded-fg)`
  - Agent 类事件: `border-left: 2px solid var(--brand-accent)`

### Task 3.3: Home — Decision Card 进度指示 `[S]`

- **验收**: "review signal" CTA 按钮旁显示 `1/7` 进度
- **文件**: `page-home.html`
- **改动**:
  - `.decision-cta.primary` 按钮文本从 "复核信号" → "复核信号 (1/7)"
  - 次要按钮 "查看风险" 旁添加 badge 显示 pending risk 数量

### Task 3.4: Trading — Signal Pipeline 可点击节点 `[M]`

- **验收**: Decision Pipeline 的 4 个阶段节点可点击，展开对应面板
- **文件**: `page-trading-overview.html`
- **改动**:
  - 每个节点（Signal Pool / Pending / Ordered / Filled）包装为 `<label>` + radio input
  - 点击节点 → 展开对应 overlay drawer（信号池/待审/已下单/已成交）
  - 节点间连线添加 `stroke-dashoffset` 动画模拟信号流动
  - 保持现有 overlay drawer 模式（CSS-only）

### Task 3.5: Trading — 持仓行内微可视化 `[M]`

- **验收**: 持仓表格盈亏列有背景染色，占比列有 inline bar
- **文件**: `page-trading-overview.html`
- **改动**:
  - 盈亏列: 正值 `background: color-mix(market-up-fg 8%, transparent)`，负值用 market-down-fg
  - 占比列: 追加 micro-bar-fill 显示持仓权重
  - 成本/现价列: 保持 `cell-change-up/down` ✓

### Task 3.6: Trading — 实时价格 Flash 动画 `[S]`

- **验收**: 价格变动时有 `semantic-value-flash` 动画
- **文件**: `page-trading-overview.html`
- **改动**:
  - 持仓现价 cell 添加 `semantic-value-flash` class（已在 layout-state.css 定义）
  - 添加 `data-flash-dir="up/down"` 属性驱动颜色方向
  - 注释说明: 原型中为静态展示，React 实现时由 price update event 触发

---

## Phase 4: 高级页面深化

### Task 4.1: Cross-Market — 关联矩阵可交互 `[M]`

- **验收**: 矩阵单元格 hover 显示 tooltip，点击展开市场对走势对比
- **文件**: `page-cross-market.html`
- **改动**:
  - 矩阵 `<td>` 添加 `data-tooltip` 属性（复用 prototype-interactions.css 的 tooltip 系统）
  - 添加 radio overlay "pair-chart" — 展示两市场叠加走势图
  - 时间范围切换（1D/5D/1M/3M/1Y）用 pill tab 实现

### Task 4.2: Cross-Market — Macro Drivers Bar 增强 `[S]`

- **验收**: Macro Drivers 条有标题栏和方向箭头
- **文件**: `page-cross-market.html`
- **改动**:
  - 添加 section header "宏观驱动因子"
  - 每个因子值后添加 `data-direction="up/down/flat"` 箭头
  - 右侧添加 "对组合影响" 小面板（placeholder）

### Task 4.3: Agent Console — Finding 源数据链接 `[M]`

- **验收**: 每个 Finding 行显示数据来源标签（Wind/Tushare/内部模型）
- **文件**: `page-agent-console-v2.html`
- **改动**:
  - Findings 表格行追加 `<td class="source-tag">` 列
  - 标签使用 `.cell-badge` 样式 + 来源色码：
    - Wind → `--brand-accent`（Lapis）
    - Tushare → `--cyan-500`
    - 内部模型 → `--purple-500`
  - Inspector Panel 的 Finding 详情区追加 "数据来源" 行

### Task 4.4: Agent Console — Confidence 可视化增强 `[S]`

- **验收**: Findings 表格的 confidence 列从纯数字升级为 bar + 数字
- **文件**: `page-agent-console-v2.html`
- **改动**:
  - confidence td 内追加 `.micro-bar`（复用 Task 1.2）
  - ≥80% → `micro-bar-fill.up`；60-80% → `accent`；<60% → `risk`
  - 数字保留在 bar 右侧

### Task 4.5: Agent Console — 批量审批交互 `[M]`

- **验收**: Findings 表格支持多选 + 底部 batch action bar
- **文件**: `page-agent-console-v2.html`
- **改动**:
  - 表格首列添加 checkbox `<input type="checkbox">`
  - checkbox :checked + :has() 激活 `.batch-action-bar`（复用 layout-components.css L1802-1821）
  - bar 显示 "已选 N 项" + 批量审批 / 批量拒绝 / 添加标签
  - 批量审批时显示汇总 "预计敞口影响"

### Task 4.6: Portfolio — 归因前置迷你 donut `[S]`

- **验收**: 右侧 Activity Stack 的 PnL chart 下方有 64×64 迷你 donut chart
- **文件**: `page-portfolio.html`
- **改动**:
  - 在 PnL chart 下方插入 64×64 `conic-gradient` donut（复用页面已有 donut chart 的 CSS 模式）
  - 3-4 色行业分布 + 点击展开完整 Attribution tab
  - 使用 `<label>` + radio 触发 tab 切换

### Task 4.7: Portfolio — PnL Chart 基准线叠加 `[M]`

- **验收**: PnL 曲线图叠加沪深 300 基准虚线 + 最大回撤区间高亮
- **文件**: `page-portfolio.html`
- **改动**:
  - SVG chart 添加第二条 polyline（沪深 300）用 `--chart-grid-major` 色虚线
  - 添加 legend: "组合"（实线）/ "沪深 300"（虚线）
  - 回撤区间用 `<rect>` + `fill: color-mix(market-down-fg 10%, transparent)` 高亮

### Task 4.8: Portfolio — Exposure Heat 可点击 `[S]`

- **验收**: Exposure heat tile 点击展开行业持仓明细 overlay
- **文件**: `page-portfolio.html`
- **改动**:
  - 每个 `.exposure-tile` 包装为 `<label>` + radio
  - 添加 overlay drawer 显示该行业下所有持仓（ticker + 占比 + 盈亏）
  - 保持现有 heat tile 色码 ✓

---

## Phase 5: 跨页面一致性

### Task 5.1: Tab 样式决策文档化 `[S]`

- **验收**: 在 shared/ 目录创建 markdown 文件记录 tab 变体使用规则
- **文件**: `shared/tab-variants.md`（新建）
- **内容**:
  - Pill tab: 用于 Dashboard 布局（Home, Trading, Portfolio）
  - Underline tab: 用于 IDE 布局（Agent Console）
  - 引用 layout-components.css 中的 tab 样式类名

### Task 5.2: 数据新鲜度 stale 可视化统一 `[M]`

- **验收**: 6 个列表页的 stale 行统一使用 Watchlist 的 `opacity: 0.6 + filter: saturate(0.4)` 方案
- **文件**: 6 个列表页各自修改
- **改动**:
  - 每个列表页 State Gallery 中已有的 `[data-state="stale"]` 行添加 watchlist 风格的 stale 视觉处理
  - 在 `shared/layout-components.css` 中提取 `.data-row-stale` 通用类

### Task 5.3: 基准对比模式占位 `[S]`

- **验收**: Portfolio 和 Backtest Result 的 chart 区域添加 "对比基准" toggle（placeholder）
- **文件**: `page-portfolio.html`, `page-backtest-result.html`
- **改动**:
  - chart header 追加 benchmark selector（下拉菜单 placeholder）
  - 选项: 无基准 / 沪深 300 / 中证 500 / 创业板指
  - 原型中仅展示 UI，不实现实际叠加逻辑

---

## 依赖关系

```
Phase 1 (共享组件) ← Phase 2 (列表页) ← Phase 5 (一致性)
                        Phase 3 (核心页面)
                        Phase 4 (高级页面)
```

- Phase 1 必须最先完成（共享组件被后续所有任务依赖）
- Phase 2/3/4 可并行执行（页面间无依赖）
- Phase 5 最后执行（需要其他页面改动稳定后再统一）

## 预估工作量

| Phase | 任务数 | 预估改动量 |
|-------|:------:|-----------|
| Phase 1 | 3 | ~120 行共享 CSS |
| Phase 2 | 6 | ~600 行（每页 ~100 行 HTML+CSS） |
| Phase 3 | 6 | ~400 行 |
| Phase 4 | 8 | ~600 行 |
| Phase 5 | 3 | ~150 行 |
| **总计** | **26** | **~1,870 行** |

## 优先级排序（推荐执行顺序）

1. **Task 1.1~1.3** — 共享组件（所有后续任务依赖）
2. **Task 2.2~2.4** — Factor/Backtest/Strategy 列表页（视觉提升最大）
3. **Task 3.5~3.6** — Trading 持仓可视化（高频使用页面）
4. **Task 4.3~4.4** — Agent Console AI 透明度（核心差异化）
5. **Task 2.1, 2.5, 2.6** — Watchlist/Experiment/Universe（次要列表页）
6. **Task 3.1~3.3** — Home 微调
7. **Task 4.1~4.2** — Cross-Market 深化
8. **Task 4.5~4.8** — Agent 批量操作 + Portfolio 增强
9. **Task 5.1~5.3** — 跨页面一致性

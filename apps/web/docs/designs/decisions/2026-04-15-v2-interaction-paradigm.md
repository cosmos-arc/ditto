# v2 交互范式变更：从锁定视口到自然滚动 + 折叠

**日期**：2026-04-15
**状态**：已确认，待实施
**影响范围**：21 个原型页 + 7 个 Shell Layout + React Shell 组件

---

## 背景

v1 原型经过 4 轮迭代，21 个页面全部通过 cross-page audit。但在实际评审中发现以下交互层问题：

1. **信息遮挡**：`100vh; overflow: hidden` 锁定视口，信息量超出时各区块被迫使用 `overflow-y: auto` 区块内滚动，用户不知道某区块还有更多内容
2. **首屏信息权重**：Decision Banner 是最重要的决策信息，但被 Pulse Strip 压在下面
3. **内容狭窄**：Sidebar 固定 320px + Rail 56px，在 1536px 屏幕上内容区仅 1160px，又被 `main-primary` + `shell-secondary` 左右分栏进一步压缩
4. **区块内滚动体验差**：多个区块各自独立滚动，心智负担高；滚动条细小（6px）容易丢失；触控板/鼠标滚轮在跨区块边界时行为不一致
5. **样式 Bug**：按钮错位、数字颠倒、页面区域空白、风格颜色不一致（在交互变更后统一修复）

## 业界调研结论

| 产品 | 滚动策略 | 信息密度管理 |
|------|---------|------------|
| Bloomberg Terminal | 锁定视口 + 功能键切换 + 条目展开 | Progressive Disclosure，不滚动 |
| TradingView | 自然滚动 + 可拖拽分割面板 | 全页面滚动，图表固定 |
| Koyfin | 自然滚动 + 右侧可收起面板 | 全页面滚动，表格固定表头 |
| Databento | 自然滚动 + 粘性表头 | 单列流式 |
| Grafana | 自然滚动 + 可配置 Widget 面板 | Widget 可调大小/显隐 |
| VS Code | 锁定视口 + 侧边栏可收窄 + Tab 切换 | 面板折叠/展开 |

**结论**：自然滚动是 2024-2026 年数据密集型界面的主流趋势，但需要配合 Progressive Disclosure 保证首屏信息密度。

## 决策

### D1：Shell 布局范式 — 自然滚动 + 折叠（混合模式 C）

**Before**（v1）：
```
body { height: 100%; overflow: hidden; }
.shell { height: 100vh; overflow: hidden; }
.shell-main { overflow-y: auto; }  /* 区块内滚动 */
```

**After**（v2）：
```
body { height: 100%; overflow-y: auto; }  /* 自然滚动 */
.shell { height: 100vh; overflow: hidden; }  /* Shell 框架固定 */
.shell-main { overflow-y: auto; }  /* Main 自然滚动 */
```

**规则**：
- Shell 框架（Rail + Header）和 Sidebar 固定不动
- Main 区域自然滚动（`overflow-y: auto`），不再 `overflow: hidden`
- 首屏高度内的区块完整展示，超出部分用 `[+N more ▾]` 折叠
- 折叠/展开是纯 UI 状态，不需要路由变更

### D2：Sidebar — 固定 + 折叠 + 可收窄

**展开状态**（320px，默认）：
- 各区块用 Progressive Disclosure 折叠次要信息
- 市场脉搏：默认 3 个核心指标，其余折叠
- 全局预警：默认 critical 级别，warning/info 折叠
- 数据健康：始终展示 gauge 条 + 异常项数

**收窄状态**（48px）：
- 顶部 `≪` 按钮触发收窄
- 收窄后只显示各区块 icon，hover 显示 tooltip
- 点击 icon 弹出 popover 显示完整内容
- 收窄/展开状态记忆到 localStorage

### D3：Main 区域 — 单列流式布局

**Before**（v1）：
```
.shell-main = main-primary + shell-secondary（左右分栏）
```

**After**（v2）：
```
.shell-main = 单列流式（垂直排列，自然滚动）
```

**变更**：
- 去掉 `shell-secondary` 左右分栏
- 去掉 Workspace Placeholder（产品文档标注 "pending product spec"）
- Research Progress 和 Agent Findings 改为全宽区块，在 Priority Queue 下方自然流式排列
- 单列布局在 Sidebar 收窄后自动获得更宽的内容区域

### D4：Pulse Strip → Status Bar

**Before**（v1）：
```
┌──────────────────────────────────────┐
│ Header                               │
├──────────────────────────────────────┤
│ Pulse Strip (独立行, ~32px)          │
├──────────────────────────────────────┤
│ Decision Banner                      │
└──────────────────────────────────────┘
```

**After**（v2）：
```
┌──────────────────────────────────────┐
│ Header                               │
├──────────────────────────────────────┤
│ Status Bar (~28px, 从属于 Header)    │
├──────────────────────────────────────┤
│ Decision Banner                      │
└──────────────────────────────────────┘
```

**规则**：
- Pulse Strip 的核心信息合并到 Header 下方 Status Bar
- Status Bar 字号 10-11px，字重 regular，视觉从属于 Header
- Status Bar 显示：盘中状态 | PnL | 风险等级 | Regime | 待处理数
- Decision Banner 保留完整展示（数字 + 趋势 + sparkline + 上下文）
- 此变更仅影响 Home 页（Command Center Shell），其他页面保持各自 Strip 设计

### D5：跨页面一致性

| Shell Family | Main 滚动 | 例外 | Sidebar/Rail |
|-------------|----------|------|-------------|
| Command Center（Home, AI Overview） | 自然滚动 | — | 固定 + 可收窄 |
| Analytical（Markets Intel, Cross Market） | 自然滚动 | — | 固定 + 可收窄 |
| Catalog（A-Shares, Markets Screener） | 表格内部滚动 | 固定表头 | 固定 + 可收窄 |
| Object Hub（Instrument, Strategy Detail） | 自然滚动 | — | — |
| Studio（Strategy Studio, Factor Analysis） | 保持三栏 grid | Source/Inspector 内部可折叠 | — |
| Ops Console（Risk Center, Orders Ledger） | 自然滚动 | — | Detail 固定 + 可收窄 |
| Radar（Regime Monitor, Signals Inbox） | 自然滚动（已实现） | — | Right Rail 固定 + 可收窄 |

**统一规则**：
- 所有 Sidebar/Detail Panel/Rail 支持收窄（`≪` / `≫` 按钮）
- Catalog 页面的表格滚动是唯一例外（固定表头 + 行滚动）
- 收窄/展开状态持久化到 localStorage

## 折叠规则详细定义

### Priority Queue（Home）
- 首屏展示所有 P1 项（通常 1-3 项）
- P2/P3 折叠到 `[+N more ▾]`
- 展开后显示完整列表，不改变页面布局

### Research Progress（Home）
- 首屏展示 2 项
- 其余折叠到 `[+N more ▾]`

### Agent Findings（Home）
- 首屏展示 2 项
- 其余折叠到 `[+N more ▾]`

### 全局预警（Sidebar）
- 首屏展示所有 critical 级别
- warning/info 折叠到 `[+N more ▾]`

### 市场脉搏（Sidebar）
- 首屏展示 3 个核心指标（沪深300、波动率、涨跌比）
- 北向资金折叠到 `[更多 ▾]`

### 数据健康（Sidebar）
- 始终展示 health gauge 条 + 异常项计数
- 正常项折叠到 `[+N 正常 ▾]`

## 实施计划

### 阶段 1：交互范式变更

1. **修改 `layout-base.css`**：
   - 更新 `.shell` grid 定义（body overflow、Main 区域 overflow）
   - 新增 Status Bar 样式
   - 新增 Sidebar 收窄样式（48px icon strip）
   - 去掉 `.shell-secondary` 左右分栏样式
   - 新增折叠组件样式（`[+N more ▾]`）

2. **逐页修改原型**：
   - 每个原型页的页面级 CSS 适配新布局
   - Home 页：Pulse → Status Bar、去掉 Workspace、单列流式
   - 其他页面：Main 区域滚动行为调整、Sidebar 收窄支持
   - Catalog 页面：保持表格内部滚动

3. **更新 Shell Layout React 组件**：
   - `command-center.layout.tsx`：去掉 secondary slot，Main 自然滚动
   - 其他 layout：调整 overflow 行为
   - 新增 Sidebar 收窄组件

### 阶段 2：样式 Bug 修复

在阶段 1 完成后，逐页修复：
- 按钮对齐（`decision-cta-row`、`panel-action`）
- 数字格式（`data-ticker`、`data-counter`）
- 空白区域（mock 数据、组件渲染）
- 颜色一致性（token 使用、无硬编码）
- 字号/字重统一（`font-feature-settings: 'tnum'`）

## 可配置 Widget 布局（后续）

D 方案（可拖拽 Widget Dashboard）作为后续功能预留：
- 当前 v2 的单列流式布局是 Widget 系统的简化版本
- 后续可以在此基础上添加拖拽排列、显隐控制、大小调整
- 需要引入 Widget 框架（如 react-grid-layout），实现复杂度较高
- 建议在 v2 交互稳定后、有明确用户需求时再启动

## 验收标准

- [ ] 所有 21 个原型页的 Main 区域支持自然滚动
- [ ] Sidebar 支持收窄/展开，状态持久化
- [ ] 首屏无信息遮挡（所有核心区块完整可见）
- [ ] 折叠组件交互正确（展开/收起、计数准确）
- [ ] Status Bar 信息与 Decision Banner 无矛盾
- [ ] Catalog 页面表格滚动正常（固定表头）
- [ ] 样式 Bug 清零（按钮对齐、数字格式、颜色一致）
- [ ] 跨密度（紧/标/松）表现一致
- [ ] 跨主题（暗/亮）表现一致

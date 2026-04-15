# v3 交互框架设计决策

## Context

v2 交互范式（`docs/designs/decisions/2026-04-15-v2-interaction-paradigm.md`）解决了"锁定视口 → 自然滚动"的基础问题。但实现后暴露了新的交互层面问题：

1. **信息分层不够精细**：只有"全显示"和"折叠"两个极端，缺少中间态
2. **侧边栏折叠体验粗糙**：48px 空白图标条 + `»`/`«` 字符 toggle，没有信息保留
3. **常驻面板浪费空间**：Orders Ledger trace、Risk Center activity 栏即使未选中任何项也占 300-340px
4. **可滚动 ≠ 无限平铺**：高密度页面（Ledger、Risk）滚到底也看不完，需要信息优先级定义

**本决策文档定义 v3 交互框架** — 在 v2 滚动基础上，建立统一的信息分层、面板折叠、详情展示体系。

**范围**：设计决策文档，不涉及代码实现。

---

## D1：三级信息分层（L1/L2/L3）

### 决策

页面信息分为三个可见性层级：

| 层级 | 可见性 | 导航成本 | 内容类型 |
|------|--------|----------|----------|
| **L1 — 首屏行动区** | 打开页面即可见 | 零（无需操作） | 状态摘要 + 异常信号 + 操作入口 |
| **L2 — 背景上下文区** | 滚动即可见 | 零（自然滚动） | 趋势变化 + 参考数据 + 历史记录 |
| **L3 — 深度详情区** | 点击/Drawer/展开 | 一次点击 | 完整表格 + 详细报告 + 配置界面 |

### 设计原则

**L1/L2 是连续流**：两者之间无视觉断裂，用户感觉是一个连续的信息流。L1→L2 的过渡仅是滚动，不是认知跳转。这确保实际导航层级只有 **1 次**（L1/L2 → L3），符合 NN/g 对渐进式披露的建议（"designs that go beyond 2 disclosure levels typically have low usability"）。

**L1 准入条件**（必须全部满足）：
1. 用户打开页面时**需要立即看到**
2. **直接影响决策**
3. 数量 ≤ N 个信息单元（N 按页面类型定）

**L2 准入条件**：
1. 帮助理解 L1 的上下文和依据
2. 不需要立即行动，滚动到就能看到
3. 数量不限，但应有**视觉权重递减**

**L3 准入条件**：
1. 需要**主动触发**（点击、展开、Drawer）
2. 信息量大或操作复杂，不适合平铺
3. 查看 L3 不应**丢失 L1 上下文**

### 信息单元计数（替代百分比限制）

基于 NN/g 的建议（"the initial display can't contain too many options"）和量化终端用户是专家用户的特性，使用 Miller's Law（7±2）作为信息单元上限：

| 页面类型 | L1 最大信息单元 | 示例 |
|----------|----------------|------|
| 决策型（Home, Trading） | 5-7 个 | Decision Banner + Queue + Status Bar |
| 分析型（Risk, Research） | 6-9 个 | Metrics Strip + Gauges + Charts |
| 浏览型（Markets, Screener） | 3-5 个 | Filter Bar + Table |
| 详情型（Instrument Hub） | 5-7 个 | Price Header + Metrics + Chart |

> **信息单元** = 一个可识别的数据簇（一张 KPI 卡片、一个表格 header、一条信号项）。不含导航 rail、header chrome。

### 上下文感知的信息显示

当用户已通过筛选器/Tab 选择了特定范围时，L1 中不再重复显示该维度信息，而是用该 slot 展示下一优先级的信息。

**示例**：Risk Center 用户选了"VaR"场景后，L1 strip 中的"VaR(95%)"可以替换为"最大回撤变化趋势"。

### 待产品确认

每页的 L1/L2/L3 具体分配需要产品经理分析后确认。本决策仅定义框架和规则。

---

## D2：两级面板折叠系统

### 决策

侧边栏/右侧面板支持两级折叠：

1. **级别 1 — 面板级**：整个面板折叠为 56px 浓缩图标条
2. **级别 2 — Section 级**：面板展开时，内部各 section 可独立折叠

### 面板类型区分

| 面板类型 | 策略 | 适用页面 |
|----------|------|----------|
| **全局上下文面板** | 常驻 + 面板级折叠 + Section 级折叠 | Home sidebar, Intelligence rail, Hub sidebar |
| **选中详情面板** | 改为按需 Drawer（见 D3） | Orders Ledger trace, Risk Center activity |

### 折叠态设计（信息浓缩型）

**核心理念**：折叠态不等于空白态 — 保留信号级浓缩信息。

```
展开态 (320px)                    折叠态 (56px)
┌──────────────────┐              ┌────────┐
│ 市场脉搏          │              │  📈    │  ← section icon
│ 上证 +0.3%       │              │ spark  │  ← mini sparkline (12px)
│ ─── 北向资金 ───  │     →       │        │
│ 全局预警          │              │  ⚠️ 2  │  ← count badge
│ CRITICAL: ...     │              │        │
│ 数据健康          │              │  🟢    │  ← health dot
│ ████████░░ 80%    │              │        │
└──────────────────┘              │  [«]   │  ← expand toggle
                                  └────────┘
```

### 折叠宽度

`--shell-sidebar-collapsed-width: 56px`（从 48px 调整）

依据：
- 业界范围 48-64px（UX Planet 2024 综合分析）
- 56px 可放下 20px 图标 + 12px badge + 8px padding
- 48px 只能放图标，无法显示浓缩信号

### 折叠动画

| 属性 | 值 |
|------|-----|
| 过渡时长 | 200ms |
| 缓动函数 | `cubic-bezier(0.4, 0, 0.2, 1)` |
| 宽度变化 | `320px → 56px`（纯空间位移） |
| 透明度变化 | 无（不做 fade，避免"消失"语义） |
| 内容区扩展 | 同步 200ms |

### Toggle 按钮

替代 `»`/`«` 字符，改为 **Chevron SVG 图标 + Tooltip**：

- 展开态：`‹`（左 chevron，表示"收窄"）
- 折叠态：浓缩信息单元可点击展开（每个 section 一个可点击区域）

### 浓缩信息映射

| 页面 | 面板内容 | 折叠态浓缩 |
|------|----------|-----------|
| Home | 市场脉搏 + 预警 + 数据健康 | 趋势图标 + sparkline + 异常数 badge + 健康色点 |
| Intelligence | 关联标的 + 筛选器 + AI 摘要 | 标的数 badge + 筛选器激活数 + AI 图标 |
| Risk Center | Gauges + Breaches + Incidents | 风险色点 + breach 数 + incident 数 |
| Instrument Hub | Signals + Notes + Filings | 信号数 badge + 笔记数 + 公告数 |

### Section 级折叠

面板展开后，内部 section 使用 `<details>/<summary>` 折叠：
- `<summary>` 使用 `.context-section-disclosure` 样式（已在 layout-base.css 中定义）
- 折叠时显示 section 标题 + 隐藏项数量 badge
- 无额外动画（浏览器原生行为即可）

---

## D3：选中详情面板 → Drawer

### 决策

将"选中详情面板"（常驻右侧、内容依赖选中项）改为**按需右侧 Drawer**。

### 判断标准

| 条件 | 策略 |
|------|------|
| 面板内容是**全局上下文**（市场脉搏、筛选器） | 常驻 + D2 折叠 |
| 面板内容**依赖选中项**（订单 trace、breach 详情） | 按需 Drawer |

### 具体变更

| 页面 | 当前 | 变更为 | 效果 |
|------|------|--------|------|
| **Orders Ledger** | 常驻 340px trace 面板 | 点击行 → Drawer 滑出 | 默认表格全宽 |
| **Risk Center** | 常驻 300px activity 栏 | 点击 breach → Drawer | 默认图表区更大 |

### Drawer 规格

| 属性 | 值 |
|------|-----|
| 方向 | 从右侧滑出 |
| 宽度 | 400-480px（比原面板更宽，利用释放的空间） |
| 过渡 | 250ms ease-out |
| 背景 | 半透明 backdrop（点击可关闭） |
| 与主内容关系 | 主内容保持可见（不全屏遮挡） |
| 关闭方式 | 点击 backdrop / ESC / Drawer 内关闭按钮 |

### 保留常驻面板的页面

| 页面 | 面板 | 原因 |
|------|------|------|
| Home | 320px sidebar | 市场脉搏是全局上下文，始终相关 |
| Intelligence | 320px right rail | 筛选器需要随时可用 |
| Instrument Hub | 340px sidebar | 关联信息辅助分析 |

---

## D4：交互一致性规则

### 跨页面一致性

1. **所有可折叠面板**使用相同的折叠宽度（56px）、动画时长（200ms）、缓动函数
2. **所有 Drawer**使用相同的方向（右侧）、关闭方式（backdrop/ESC/按钮）
3. **所有 Section 折叠**使用相同的 `<details>/<summary>` 模式和样式
4. **浓缩信息**遵循相同的视觉规范（图标大小 20px、badge 样式、sparkline 尺寸 24×12px）

### 密度系统兼容

已有的密度切换系统（紧/标/松）应影响：
- L1 信息单元的紧凑程度（而非数量）
- 折叠态浓缩信息的显示粒度
- 不影响 L1/L2/L3 的层级划分

---

## 参考来源

| 来源 | 关键洞察 |
|------|----------|
| NN/g — Progressive Disclosure (2006) | 最多 2 个披露导航层级；初始展示不能太多选项 |
| Bloomberg — Concealing Complexity (2022) | 固定面板 → Tab 模型；动态窗口；渐进式更新 |
| Algolia — Information Density (2025) | 上下文感知的信息显示；slot 模型；用户可控密度 |
| UX Planet — Sidebar Best Practices (2024) | 折叠宽度 48-64px；tooltip 必备；拖拽调宽是加分项 |

---

## 实施优先级

| Phase | 内容 | 依赖 |
|-------|------|------|
| **P1** | Token 更新（56px collapsed width） | 无 |
| **P2** | layout-base.css 面板折叠动画 + 浓缩态样式 | P1 |
| **P3** | Home 页面浓缩态 HTML | P2 |
| **P4** | Intelligence/Hub 页面浓缩态 | P2 |
| **P5** | Orders Ledger trace → Drawer | P2 |
| **P6** | Risk Center activity → Drawer | P2 |
| **P7** | 各页面 L1/L2/L3 信息分配（需产品确认） | P1-P6 完成后 |

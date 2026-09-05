# 原型像素级审计 — 全页面差异清单 + 修复计划

> **日期**：2026-04-10
> **方法**：Chrome DevTools computed styles 提取 + 截图 AI 对比 + CSS 规则交叉验证
> **原型基线**：`docs/designs/specs/prototypes/` 17 页 HTML + `shared/*.css`
> **实现基线**：`src/` 当前 feat/prototype-three-zone-architecture 分支

---

## 诊断总览

| 页面 | 原型评分 | 实现保真度 | 核心差距 |
|------|---------|-----------|---------|
| Home | 9.2 | ~45% | Shell 非网格布局、右侧栏缺失、Banner 缺第 3 栏、Context Bar 缺失 |
| Research | 9.0 | ~60% | 因子表缺条件格式、分析带基本就位但图表简陋 |
| Trading | 9.1 | ~55% | Banner 3 栏结构差、持仓表缺 sparkline、信号队列缺置信度条 |
| Markets | 9.0 | ~50% | 缺 Scope Strip、资金轮动缺 FlowBar 组件、相关性矩阵样式简陋 |
| AI | 9.0 | ~65% | 结构基本对齐，缺进度条组件和 Agent 状态动画 |

---

## Phase 0: Shell 网格布局（影响全部页面）

### 0.1 Shell 使用 flex 而非 CSS Grid（CRITICAL）

**原型**（`layout-base.css`）：
```css
.shell {
  display: grid;
  grid-template-columns: var(--shell-rail-width) 1fr var(--shell-sidebar-width);  /* 56px 1fr 320px */
  grid-template-rows: var(--shell-header-height) auto 1fr;  /* 68px auto 1fr */
  grid-template-areas:
    "rail header   header"
    "rail pulse    pulse"
    "rail main     sidebar";
  height: 100vh; width: 100vw; overflow: hidden;
}
```

**实现**（`app-shell.tsx`）：
```
shell computed: display=block, gridTemplateColumns=none, gridTemplateRows=none
```

**修复**：`app-shell.tsx` 必须使用 CSS Grid 替代当前的 flex 嵌套。需要按页面类型切换 `grid-template-areas`：

| 页面 | grid-template-areas | grid-template-columns |
|------|--------------------|-----------------------|
| Home | `"rail header header" "rail pulse pulse" "rail main sidebar"` | `56px 1fr 320px` |
| Trading | `"rail header header" "rail banner banner" "rail main sidebar"` | `56px 1fr 320px` |
| Research | `"rail header" "rail strip" "rail main" "rail analysis"` | `56px 1fr` |
| Markets | `"rail header header" "rail strip strip" "rail main sidebar"` | `56px 1fr 320px` |
| AI | `"rail header header" "rail main sidebar"` | `56px 1fr 320px` |

**文件**：`src/features/shell/components/app-shell.tsx`

### 0.2 右侧栏缺失（CRITICAL）

原型 Home 页有 320px 右侧栏（`grid-area: sidebar`），包含市场脉搏、全局预警、数据健康三个面板。

实现完全没有右侧栏——所有内容塞进了主面板区域。

**修复**：
- 新增 `<Sidebar>` 容器组件，`grid-area: sidebar`
- Home 页右栏：市场脉搏 + 全局预警 + 数据健康（从当前底部区域移入）
- Trading 页右栏：信号队列 + 风控监控
- Markets 页右栏：市场事件 + 资金流向
- AI 页右栏：近期输出

**文件**：`src/features/shell/components/app-shell.tsx` + 各页面组件

### 0.3 Pulse Strip 位置错误（HIGH）

原型 Home 的 Pulse Strip 是独立的 `grid-area: pulse` 行（高度 ~32px），位于 header 和 main 之间。

实现将市场脉搏放在面板内部的折叠区域中。

**修复**：将 Home 页的 Pulse Strip 提取为 shell grid 的独立行。

**文件**：`src/features/home/components/market-pulse-section.tsx` → `src/features/shell/components/pulse-strip.tsx`

---

## Phase 1: Decision Banner（Home + Trading）

### 1.1 Banner 缺少第 3 栏（Execution/CTA）（CRITICAL）

**原型**：
```
grid-template-columns: 5fr 4fr 3fr  → 442px + 354px + 265px
3 个子区域：
  decision-primary:     今日盈亏 + sparkline + 总权益
  decision-judgment:    文字判断 + KPI row + 下一步标签
  decision-execution:   3 个 CTA 按钮（查看信号总览/进入研究/查看风控）
```

**实现**：
```
grid-template-columns: 469px + 375px  → 只有 2 列！
第 3 栏 execution 完全缺失
```

**修复**：Banner 必须是 3 列 grid。第三栏包含"下一步"标签 + CTA 按钮。

**文件**：`src/components/domain/decision-banner/decision-banner.tsx`

### 1.2 Primary 栏缺 sparkline（HIGH）

原型 primary 区有内联 SVG sparkline（近 5 日盈亏趋势），尺寸约 80×20px。

实现没有任何 sparkline。

**修复**：在 `metric-value` 下方添加 `<Sparkline>` 组件。

### 1.3 Judgment 栏缺 KPI row（HIGH）

**原型 judgment 栏内容**：
```
波动回落，北向转暖，但局部拥挤。          ← 判断文字

杠杆率 1.2x    回撤 -3.8%              ← KPI row
IVIX 18.52 [sparkline]  北向资金 +12.4亿 [sparkline]  ← KPI row + sparkline
```

**实现 judgment 栏内容**：
```
震荡偏强 — 多数板块资金净流入              ← 不同的判断文字
当前市场环境下建议维持多头配置...            ← 更长的 AI 描述
风控使用率 45%                            ← 只有 1 个 KPI
```

**差距**：
- 缺少杠杆率/回撤/IVIX/北向资金 4 个 KPI
- 缺少 2 个 inline sparkline
- 内容结构不同（应该是判断文字 + KPI row，不是长段落 + 单个指标）

### 1.4 Banner 分隔线缺失（MEDIUM）

原型 judgment 和 execution 栏有 `borderLeft: 0.8px solid oklch(0.245 0.008 253)` + `paddingLeft: 16px`。

实现只有第 2 栏有 `border-l`，第 3 栏不存在。

### 1.5 Banner 尺寸偏差

| 属性 | 原型 | 实现 | 差距 |
|------|------|------|------|
| 高度 | 148px | 117px | -31px |
| padding | 12px 16px | 0px | 缺失 |
| 列比 | 5fr:4fr:3fr | 2 列不等分 | 完全不同 |

---

## Phase 2: Context Bar（全局）

### 2.1 Context Bar 完全缺失（CRITICAL）

原型所有页面在 header 下方有 context-bar（`grid-area: pulse/strip` 或 header 内嵌）：

**Home 原型 context-bar 内容**：
```
2026-03-28 · 盘中交易 | 盈亏 +0.34% | 风险 中等 · 温和风险偏好 | 待处理 2 | 运行中 3
```

**实现**：context bar 不存在。部分数据被塞进了 decision banner。

**修复**：
- 新建 `<ContextBar>` 组件（`src/components/indicator/context-bar.tsx`）
- 放置在 shell grid 的 `pulse/strip` 行
- 样式：`height: var(--shell-context-bar-height)` (2rem/32px), `bg: var(--surface-strip)`, `border-bottom: 1px solid var(--border-subtle)`
- 子项：label(10px uppercase) + value(12px medium) + separator

**各页面 context-bar 内容**：

| 页面 | 内容 |
|------|------|
| Home | 日期 · 交易阶段 \| 盈亏 +X% \| 待处理 N \| 运行中 N |
| Trading | 交易阶段 \| 现金余额 \| 已用保证金 \| 风控预算 |
| Research | 活跃因子 42 \| 衰减因子 ▼3 \| 失败因子 ▼1 \| 审核队列 5 |
| Markets | 市态 risk_on \| 波动 18.5% \| 美元 0.72 \| 预警 2 |
| AI | 运行中计划 3 \| 待审批 2 \| COPILOT 会话 5 |

---

## Phase 3: 面板内容精修

### 3.1 Priority Queue 项缺少视觉指示器（HIGH）

**原型 queue-item**：
- 左侧 2px 色条（P1=red, P2=amber, P3=neutral）
- domain tag（交易/风控/研究/平台/数据）带背景色
- priority badge（P1/P2）
- hover 时负 margin 展开效果
- 来源 · 时间戳

**实现**：有 queue item 但缺少：
- 优先级色条
- priority badge
- hover 展开效果

### 3.2 Market Pulse 内联格式错误（HIGH）

**原型 pulse-item**：
```
标签 (10px uppercase, tertiary color) · 值 (JetBrains Mono, secondary color) · 涨跌% · [sparkline SVG]
```

**实现**：pulse 在折叠面板内，格式不同，缺少 sparkline。

### 3.3 Research Progress 项缺 attribution（MEDIUM）

**原型**：每条研究项有 `来源 · 时间`（如 "模型监控 · 2小时前"）

**实现**：有 domain tag + 时间，但格式不完全匹配。

### 3.4 Agent Insights 结构不同（MEDIUM）

**原型**：纯文本洞察（相关性分析、数据延迟、持仓变化等），按来源分类。

**实现**：信号卡片（BUY/HOLD/SELL），格式不同但信息量可接受。

---

## Phase 4: 数据表格视觉（Research + Trading）

### 4.1 Factor Table 缺条件格式（HIGH）

**原型**：IC/IR 列有 4 级颜色编码（strong/normal/muted/dim）+ spark bar 背景。

**实现**：纯数字，无颜色区分。

### 4.2 Positions Table 缺 sparkline（MEDIUM）

**原型**：7日列有 inline sparkline SVG。

**实现**：7日列只有文字。

### 4.3 Correlation Matrix 样式简陋（MEDIUM）

**原型**：5×5 热力图矩阵，数值用背景色深浅编码。

**实现**：HTML table 但无热力图背景色。

---

## Phase 5: Markets 页特定修复

### 5.1 Scope Strip 缺失（HIGH）

原型有独立的 "今日解读" scope strip（`grid-area: strip`），实现将其放在面板内。

### 5.2 资金轮动缺 FlowBar 组件（MEDIUM）

原型资金轮动使用 FlowBar（水平分段条形图）可视化流入/流出比例。

实现用纯文本行展示。

### 5.3 宏观驱动布局不同（MEDIUM）

**原型**：内联条式布局（标签 | 值 | 变化 在一行内）

**实现**：网格卡片布局

---

## Phase 6: 视觉材质感层

### 6.1 Header 签名线（已实现 ✅）

原型和实现都有 `::after` 底部渐变线。颜色需验证：
- 原型：`oklch(0.62 0.04 74 / 0.15→0.25)` (金色调)
- 实现：需确认是否匹配

### 6.2 Noise Layer 环境光线（需验证）

原型有 1.5px 顶部光线 + 1px 右侧光线。

实现已修改过，需确认参数匹配。

### 6.3 Focus Ring 系统（HIGH）

原型定义了全局 focus-visible 规则：
```css
button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 1.5px var(--color-accent), 0 0 0 4px oklch(from var(--color-accent) l c h / 0.25);
}
```

需确认实现是否已集成。

### 6.4 Hover 微交互（MEDIUM）

- Panel hover 光晕
- Queue item hover 负 margin 展开
- Market card hover inset border
- 各处 `transition: 100ms cubic-bezier(0.4, 0, 0.2, 1)`

---

## Phase 7: Typography 统一

### 7.1 数字区域缺 tabular-nums（HIGH）

原型所有数字区域使用：
```css
font-family: var(--font-family-numeric);  /* JetBrains Mono */
font-variant-numeric: tabular-nums;
letter-spacing: -0.02em;
```

实现大部分数字用 Inter 字体，无 tabular-nums。

### 7.2 标签缺 uppercase（MEDIUM）

原型 metric-label、context-bar-item label 等使用 `text-transform: uppercase; letter-spacing: 0.04em`。

实现部分标签是普通大小写。

---

## 执行策略

```
Phase 0 (Shell Grid)     ← 所有后续工作的前提，1-2 天
    ↓
Phase 1 (Decision Banner) + Phase 2 (Context Bar)  ← 并行，1 天
    ↓
Phase 3 (面板内容精修)    ← 1 天
    ↓
Phase 4 (数据表格) + Phase 5 (Markets)  ← 并行，1-2 天
    ↓
Phase 6 (材质感) + Phase 7 (Typography)  ← 并行，0.5 天
```

### 关键原则

1. **Phase 0 必须先做** — Shell Grid 是骨架，当前 display:block 布局让所有后续修改建立在不稳定基础上
2. **先结构后细节** — 网格→面板→内容→样式，每层验证后再进入下层
3. **每 Phase 后 `bun run check`** — 确保无回归

---

## 文件变更预估

| Phase | 新建文件 | 修改文件 | 复杂度 |
|-------|---------|---------|--------|
| 0 | 0 | 3-4 (app-shell, panel, 各页面) | 高 |
| 1 | 0 | 2 (decision-banner, home/trading page) | 中 |
| 2 | 1 (context-bar.tsx) | 5 (各页面) | 中 |
| 3 | 0 | 4-5 | 中 |
| 4 | 0 | 3-4 | 中 |
| 5 | 1 (flow-bar.tsx) | 2-3 | 中 |
| 6 | 0 | 2-3 | 低 |
| 7 | 0 | 5-8 | 低 |

# Edition v1 Iteration v5 — 全面质量冲刺

> 日期：2026-04-07
> 状态：Draft
> 前置：v4-complete + Lapis 配色审查（17 页 avg 9.14）
> 目标：每个页面冲刺 CSS 天花板（~9.8），消除所有已知 bug
> 约束：max 30 rounds
> 品牌色：Lapis hue 235°, chroma 0.120

---

## 1. 背景

v4 完成 Ink Indigo → Lapis 品牌色切换 + AnimatedCounter/Tooltip JS 模块 + 10 页打磨。Lapis 配色审查统一 neutral hue 253 + sparkline token 化。Three-zone 架构已全面实施。

**当前分数分布**：

| 分数段 | 页面数 | 页面 |
|--------|--------|------|
| 8.8 | 1 | markets-screener |
| 9.0 | 6 | platform, research, regime-monitor, orders-ledger, ai-copilot, token-showcase |
| 9.2 | 8 | home, cross-market, trading-overview, strategy-studio, signals-inbox, risk-center, instrument-hub, agent-console |
| 9.3 | 2 | ai-overview, markets-intelligence |

**v5 四大瓶颈**：

1. **颜色 bug**：`--market-strong-fg` / `--market-weak-fg` 红绿反转 + Ink hue 265 残留 15 处
2. **清洁度**：704 个 inline styles 残留（orders-ledger 88 → home 1）
3. **数据可视化**：sparkline 精度/色彩/动效未达生产级；hardcoded oklch 绕过 token 系统
4. **视觉天花板**：微交互不够"活"、信息密度对标彭博/TradingView 有差距

---

## 2. 策略：先修 bug → 再清债 → 后打磨

```
Phase 1 (R1-4)   颜色正确性 — market strong/weak 修正 + Ink 残留清除
Phase 2 (R5-10)  Inline Style 清剿 — 704 → <50
Phase 3 (R11-22) 逐页深度打磨 — 从最低分开始，三维发力
Phase 4 (R23-28) 跨页一致性终审 + 收尾
Phase 5 (R29-30) 最终评分 + manifest 更新
```

---

## 3. Phase 1：颜色正确性修复（Round 1-4）

### Round 1：CRITICAL — `--market-strong-fg` / `--market-weak-fg` 红绿反转

**问题**：CN 市场红涨绿跌，但 strong=green, weak=red，语义反转。

**修复**：

`shared/tokens-domain.css` lines 25-26:
```css
/* Before (WRONG for CN) */
--market-strong-fg:  var(--green-600);
--market-weak-fg:    var(--red-600);

/* After (CORRECT for CN) */
--market-strong-fg:  var(--red-600);      /* red (CN: 涨/强势) */
--market-weak-fg:    var(--green-600);    /* green (CN: 跌/弱势) */
```

`tokens-style.css` lines 41-42:
```css
/* Before */
--market-strong-fg:  oklch(0.700 0.140 155);   /* green hue 155 */
--market-weak-fg:    oklch(0.680 0.180 18);    /* red hue 18 */

/* After */
--market-strong-fg:  oklch(0.680 0.180 18);    /* red hue ~18 (CN: 涨/强势) */
--market-weak-fg:    oklch(0.700 0.140 155);   /* green hue ~155 (CN: 跌/弱势) */
```

**受影响页面**：page-home.html 10 处引用（.risk-on, .risk-off, .val-strong, .val-weak, PnL sparkline）

**验证**：Chrome MCP 截图确认 page-home 中 risk-on tag 为红色、risk-off tag 为绿色。

### Round 2：Ink Indigo hue 265 残留清除

**HTML sparkline data attributes**（7 处）：
- `page-markets-intelligence.html` lines 2249, 2257, 2273, 2281: `stroke="oklch(0.7 0.085 265)"` → 改用 `"series":"up"` 委托 JS 渲染
- `page-cross-market.html` lines 1916, 1924: `stroke="oklch(0.7 0.085 265)"` → 改用 `"series":"neutral"` 或合适的 series token
- `page-trading-overview.html` line 2019: `stroke="oklch(0.7 0.085 265)"` → 改用 `"series":"up"`（equity curve positive）

**JS fallback values**（5 处）：
- `shared/prototype-interactions.js` line 186: `'oklch(0.700 0.085 265)'` → `'oklch(0.700 0.120 235)'`（Lapis）
- `shared/prototype-interactions.js` lines 107, 468, 469: hue 253 fallback → `'oklch(0.700 0.120 235)'`
- `page-instrument-hub.html` line 3198: `'oklch(0.700 0.085 265)'` → `'oklch(0.700 0.120 235)'`

### Round 3：其他颜色 bug

- `page-markets-intelligence.html` line 2265: 下跌股 `stroke="oklch(0.65 0.15 25)"` (red) → 应为 green hue 155
- `shared/layout-base.css` line 845: `rgba(var(--brand-500-rgb), 0.1)` → `--brand-500-rgb` 未定义，改为 `oklch(from var(--brand-500) l c h / 0.1)`
- `.edition-manifest.json` lines 318, 348: "Ink Indigo" 文字 → 更新为 "Lapis"

### Round 4：验证 Phase 1

- Chrome MCP 逐一检查每个修改过的页面
- 确认 CN 模式下红涨绿跌正确
- 确认无 hue 265 残留
- 确认 Lapis hue 235 在所有 brand 位置一致

---

## 4. Phase 2：Inline Style 清剿（Round 5-10）

**目标**：704 → < 50（消除 93%）

### Round 5：提取高频 utility classes

在 `shared/layout-base.css` 中添加共用 utility classes：

```css
/* ── Flex utilities ── */
.flex-row-center { display: flex; align-items: center; }
.flex-col        { display: flex; flex-direction: column; }

/* ── Spacing presets ── */
.gap-8   { gap: var(--space-8); }
.gap-10  { gap: var(--space-10); }
.gap-12  { gap: var(--space-12); }

/* ── Text roles ── */
.text-caption  { font-size: var(--font-size-10); color: var(--text-tertiary); }
.text-label    { font-size: var(--font-size-12); font-weight: var(--font-weight-medium); color: var(--text-primary); }
.text-body     { font-size: var(--font-size-13); color: var(--text-secondary); }
.text-value    { font-size: var(--font-size-14); font-weight: var(--font-weight-semibold); color: var(--text-primary); font-variant-numeric: tabular-nums; }

/* ── Status colors ── */
.status-healthy   { color: var(--system-healthy-fg); }
.status-degraded  { color: var(--system-degraded-fg); }
.status-strong    { color: var(--market-strong-fg); }
.status-weak      { color: var(--market-weak-fg); }

/* ── Panel / Card ── */
.panel-base      { background: var(--surface-panel-base); border: 1px solid var(--border-subtle); border-radius: var(--radius-8); padding: var(--space-16); }
.panel-elevated  { background: var(--surface-panel-elevated); border: 1px solid var(--border-subtle); border-radius: var(--card-radius); padding: var(--card-padding); }

/* ── Column widths (data tables) ── */
.col-narrow  { width: 72px; }
.col-small   { width: 80px; }
.col-medium  { width: 90px; }
.col-wide    { width: 100px; }
.col-auto    { flex: 1; min-width: 0; }

/* ── Progress bar ── */
.bar-track   { height: 3px; border-radius: var(--radius-full); background: var(--surface-secondary); overflow: hidden; }
.bar-fill    { height: 100%; border-radius: var(--radius-full); }

/* ── Timeline ── */
.timeline-item { padding: var(--space-8) 0; border-left: 2px solid var(--brand-accent); margin-left: 6px; }
```

### Round 6-7：逐页清剿（HIGH 优先级）

| 页面 | inline 数 | 策略 |
|------|----------|------|
| page-orders-ledger | 88 | 65 个列宽 → .col-* classes；剩余 flex/spacing → utility |
| page-instrument-hub | 83 | 百分比 bar → .bar-track/.bar-fill；chart sizing 保留 data-driven |
| page-markets-screener | 71 | flex 布局 + typography → utility classes |
| page-regime-monitor | 71 | flex 布局 + height → utility + component classes |

### Round 8-9：逐页清剿（MEDIUM 优先级）

| 页面 | inline 数 | 策略 |
|------|----------|------|
| page-ai-overview | 59 | card panels + typography → .panel-* + .text-* |
| page-ai-copilot | 55 | timeline + card → .timeline-item + .panel-* |
| page-trading-overview | 41 | progress bars + sizing → .bar-* + utility |

### Round 10：验证 Phase 2

- `grep -c 'style="' page-*.html` 统计每页残留
- 确认 data-driven inline styles（width:N%, height:Npx 动态值）是唯一合理残留
- 确认 biome/htmlhint 无新警告

---

## 5. Phase 3：逐页深度打磨（Round 11-22）

**三维发力**：数据可视化 + 微交互 + 信息密度

### 打磨顺序（从最低分开始）

| Round | 页面 | 当前分 | 目标分 | 重点 |
|-------|------|--------|--------|------|
| R11 | markets-screener | 8.8 | 9.5+ | 表格密度、sparkline 保真、filter 交互 |
| R12 | platform | 9.0 | 9.5+ | 系统监控可视化、健康状态表达 |
| R13 | research | 9.0 | 9.5+ | 报告阅读体验、AI 摘要可视化 |
| R14 | regime-monitor | 9.0 | 9.5+ | regime 热力图、状态转换时间线 |
| R15 | orders-ledger | 9.0 | 9.5+ | 表格排版、订单状态色彩系统 |
| R16 | ai-copilot | 9.0 | 9.5+ | 对话流视觉、AI 输出排版 |
| R17 | home | 9.2 | 9.6+ | 指挥中心信息密度、动态元素 |
| R18 | cross-market | 9.2 | 9.6+ | 跨市场对比可视化、联动感 |
| R19 | trading-overview | 9.2 | 9.6+ | PnL 可视化、持仓分布图 |
| R20 | instrument-hub | 9.2 | 9.6+ | 个股详情密度、技术指标图 |
| R21 | risk-center | 9.2 | 9.6+ | 风控仪表盘、热力矩阵 |
| R22 | 其余 9.2-9.3 页面 | 9.2-9.3 | 9.5+ | 快速扫描 + 针对性修补 |

### 每页打磨检查清单

**数据可视化维度**：
- [ ] Sparkline: 数据点 ≥ 20、stroke 1.5px、渐变填充、响应 series token
- [ ] Donut/Ring: 动画过渡、中空文字、颜色对齐 domain token
- [ ] Heat Grid: 色阶连贯、hover tooltip、cell size ≥ 8px
- [ ] Progress Bar: 渐变填充、动画入场、overflow clip
- [ ] Number Ticker: 格式化（千分位/百分比/±前缀）、入场动画

**微交互维度**：
- [ ] hover: surface 提升 + border 高亮（transition 150ms）
- [ ] focus: brand-accent ring（2px offset 2px）
- [ ] active: scale(0.98) + opacity 0.9
- [ ] scroll-reveal: data-reveal 模块激活
- [ ] mouse-glow: data-glow 区域激活
- [ ] tooltip: data-tooltip 关键数据点

**信息密度维度**：
- [ ] 每个面板 ≥ 3 层信息层次（primary/secondary/tertiary text）
- [ ] 关键指标 font-variant-numeric: tabular-nums 对齐
- [ ] 合理使用 surface elevation 区分面板层级
- [ ] 间距节奏一致（space-4/8/12/16 而非任意值）
- [ ] 视觉权重对齐信息重要性（大→小→辅助）

---

## 6. Phase 4：跨页一致性终审（Round 23-28）

### Round 23-24：全局一致性扫描

**颜色一致性**：
- [ ] 所有 brand 色均为 Lapis hue 235°（无 255/265 残留）
- [ ] 所有市场色均响应 CN 红涨绿跌
- [ ] 所有 risk 色遵循 5 级体系（low/medium/high/critical/breach）
- [ ] 所有 execution 色遵循订单状态映射

**排版一致性**：
- [ ] 所有数值使用 tabular-nums
- [ ] 所有标签使用 font-weight-medium
- [ ] 所有标题层次清晰（h1→h2→h3 font-size 递减）
- [ ] 所有 body text 使用 text-secondary（非 text-primary）

**交互一致性**：
- [ ] 所有可点击元素有 hover 反馈
- [ ] 所有输入元素有 focus ring
- [ ] 所有 tooltip 使用 data-tooltip（非 title attribute）
- [ ] 所有动画遵守 prefers-reduced-motion

### Round 25-26：Token 覆盖率验证

- 确认 `tokens-data-viz.css` 中所有 chart series 在页面中被使用
- 确认 `tokens-domain.css` 中所有 7 个 domain 在对应页面中被正确引用
- 确认 `tokens-density.css` 3 种密度预设均可正常切换

### Round 27-28：最终修整

- 修复 R23-26 发现的不一致
- 补充遗漏的 hover/focus 状态
- 调整视觉权重不均的面板

---

## 7. Phase 5：最终评分 + 收尾（Round 29-30）

### Round 29：逐页评分

6 维度评分（每维 0-10，加权）：

| 维度 | 权重 | 评估标准 |
|------|------|---------|
| 视觉品质 | 25% | 色彩、排版、空间节奏、品牌一致性 |
| 信息密度 | 20% | 数据丰富度、层次感、可扫读性 |
| 交互体验 | 20% | hover/focus/active、动效、tooltip |
| 数据可视化 | 15% | sparkline/chart/heatmap 质量 |
| Token 纯度 | 10% | inline styles 残留、token 覆盖率 |
| 状态覆盖 | 10% | loading/empty/error 完整度 |

### Round 30：Manifest 更新 + 提交

- 更新 `.edition-manifest.json`：每页 v5 分数 + inline style 计数
- Git commit：`feat(prototypes): Edition v1 Iteration v5 — bug fixes + inline cleanup + visual polish`

---

## 8. 预期成果

| 指标 | v4 结束 | v5 目标 |
|------|---------|---------|
| 平均分 | 9.14 | ≥ 9.5 |
| 最低分 | 8.8 (markets-screener) | ≥ 9.3 |
| 9.5+ 页面 | 0 | ≥ 10 |
| Inline styles | 704 | < 50 |
| Ink residual | 15 处 | 0 |
| Market color bug | 有 | 0 |

---

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 30 rounds 不够打磨 16 页 | Phase 3 优先低分页，高分页快速扫描 |
| Inline 清剿引入回归 | 每页清剿后 Chrome MCP 截图验证 |
| CSS 天花板 (~9.8) 无法突破 | 接受天花板，为 React 迁移做优质 HTML baseline |
| Market color 修正影响 light mode | Round 3 验证 light mode 下颜色方向 |

---

## 10. 文件变更范围

| 文件/目录 | 变更类型 |
|-----------|---------|
| `shared/tokens-domain.css` | 修改（strong/weak 修正） |
| `shared/layout-base.css` | 修改（添加 utility classes） |
| `shared/prototype-interactions.js` | 修改（Lapis fallback） |
| `tokens-style.css` | 修改（strong/weak 修正） |
| `.edition-manifest.json` | 修改（文字 + 分数更新） |
| 16 个 `page-*.html` | 修改（bug fix + inline 清除 + 视觉打磨） |

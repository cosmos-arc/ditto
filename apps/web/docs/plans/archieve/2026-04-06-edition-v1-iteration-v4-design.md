# Edition v1 Iteration v4 — 全面突破设计

> 日期：2026-04-06
> 状态：Approved
> 前置：v3-complete（17 页均 ≥ 9.0，avg 9.14）
> 目标：所有页面向 10.0 冲刺
> 约束：max 30 rounds

---

## 1. 背景

v3 通过 Vanilla JS 交互库突破 CSS 天花板，17 页均 ≥ 9.0（avg 9.14）。但距 10.0 仍有差距：

| 分数段 | 页面数 | 页面 |
|--------|--------|------|
| 8.8 | 1 | markets-screener |
| 9.0 | 6 | platform, research, regime-monitor, orders-ledger, ai-copilot, token-showcase |
| 9.2 | 8 | home, cross-market, trading-overview, strategy-studio, signals-inbox, risk-center, instrument-hub, agent-console |
| 9.3 | 2 | ai-overview, markets-intelligence |

**三大瓶颈**：
1. 品牌色仍用 V1 hue 255°（太大众 SaaS，与 Brass 搭配土气）
2. 部分页面 inline styles 拖累（token-showcase 89, instrument-hub 73, orders-ledger 65）
3. JS 交互模块已够用但缺乏"活"的感觉（无加载态、无 tooltip、无数值动画）

---

## 2. 策略：按主题推进

```
Phase 1 (R1-6)   品牌基础升级 — Ink Indigo + Token 对齐 + inline 清剿
Phase 2 (R7-18)  逐页深度打磨 — 从最低分开始，三维发力
Phase 3 (R19-28) JS v4 扩展 — 新模块 + 二次增强
Phase 4 (R29-30) 终审冲刺 — 跨页一致性 + 最终评分
```

---

## 3. Phase 1：品牌基础升级（Round 1-6）

**目标**：建立从 9.0 → 9.5 的地基。

### Round 1-2：Ink Indigo 落地

更新 `shared/tokens-base.css` brand primitives：

```css
/* Before (V1) */
--brand-500: oklch(0.700 0.165 255);

/* After (Ink Indigo) */
--brand-500: oklch(0.700 0.085 265);
```

变更范围：
- `tokens-base.css`：brand-300~700 全量更新（hue 255° → 265°, chroma 减半）
- `tokens-semantic.css`：accent/interaction 色自动继承
- `tokens-interaction.css`：focus/selected/active 自动继承
- 17 页无需逐页修改（CSS 变量透传）

### Round 3：APCA 校验 + light mode

- brand-500 在 surface-app / surface-panel / surface-elevated 上的对比度校验
- light mode brand token scale 定稿（hue 微调至 266-267° 补偿亮度背景）
- Ink Indigo + Brass 同画面视觉确认

### Round 4：Inline Style 清剿

重点目标：
| 页面 | inline 数 | 目标 |
|------|----------|------|
| token-showcase | 89 | < 10 |
| instrument-hub | 73 | < 15 |
| orders-ledger | 65 | < 10 |

方法：提取高频 inline pattern → utility class 或 component token。

### Round 5-6：跨页 Token 一致性审计

- 全 17 页扫描 deprecated tokens、hardcoded colors
- 间距/字号一致性校正
- 建立一致性基准线

---

## 4. Phase 2：逐页深度打磨（Round 7-18）

**目标**：所有页面 ≥ 9.5，领先页面 ≥ 9.7。

### 优先级队列

| Round | 页面 | 当前分 | 打磨重点 |
|-------|------|--------|---------|
| 7 | markets-screener | 8.8 | 数据表格密度、Sparkline 保真度、筛选交互 |
| 8 | token-showcase | 9.0 | inline 清剿后视觉重组、展示层次 |
| 9 | orders-ledger | 9.0 | 表格数据密度、状态列视觉编码、FlowBar 增强 |
| 10 | platform | 9.0 | 系统状态面板、拓扑图精致度、空状态处理 |
| 11 | research | 9.0 | 报告卡片层次、Sparkline 组合、滚动叙事 |
| 12 | regime-monitor | 9.0 | 热力矩阵视觉、regime 状态转换动效 |
| 13 | ai-copilot | 9.0 | 对话气泡精致度、thinking chain 动画、输入区设计 |
| 14 | instrument-hub | 9.2 | inline 清剿 + MouseGlow 精细化、tab 切换流畅度 |
| 15 | home | 9.2 | 信息密度优化、Banner 层次感、Pulse 区节奏 |
| 16-17 | markets-intelligence + ai-overview | 9.3 | 领先页面向 10 冲刺：微交互极致化、数据叙事完整性 |
| 18 | 跨页一致性微调 | — | 间距/字号/动效节奏全局校正 |

### 三维发力标准

每轮打磨需覆盖三个维度：

1. **微交互**：hover/focus transition timing、scroll-driven reveals 节奏编排
2. **数据可视化**：Sparkline 曲线平滑度、HeatGrid 色阶细腻度、Donut 描边精度
3. **视觉一致性**：间距 grid 对齐、字号层级严格遵循 type scale、surface elevation 层次

---

## 5. Phase 3：JS 交互库 v4 + 二次增强（Round 19-28）

**目标**：通过新 JS 能力突破 9.5 天花板，所有页面 ≥ 9.7。

### Round 19-21：新模块开发

新增 3 个模块到 `shared/prototype-interactions.js`：

| 模块 | data 属性 | 功能 | 核心页面 |
|------|----------|------|---------|
| AnimatedCounter | `data-counter` | 数值变化平滑过渡（ease-out + 千分位格式化） | trading-overview, risk-center, instrument-hub, home |
| SkeletonPulse | `data-skeleton` | 加载态骨架屏动画（shimmer + 渐显） | 所有页面的卡片/表格区域 |
| TooltipSystem | `data-tooltip` | 悬停信息气泡（自动定位 + 延迟显示） | 表格单元格、指标卡片、热力格 |

设计约束（延续 v3 哲学）：
- 零依赖
- 声明式 data-* 驱动
- 尊重 prefers-reduced-motion
- 渐进增强（JS-off 页面仍 ≥ 9.5 CSS baseline）

### Round 22-26：逐页二次增强

每轮 2-3 页快速轮转：
- AnimatedCounter 替换关键数值静态展示
- SkeletonPulse 添加到数据加载区域
- TooltipSystem 添加到表格指标、图表数据点
- 微调已有模块：Sparkline 插值优化、NumberTicker easing 升级

### Round 27-28：动效节奏全局调优

- 统一 transition duration：fast 120ms / normal 200ms / slow 350ms
- ScrollReveal stagger 间隔跨页面一致
- prefers-reduced-motion 下降级体验校验

---

## 6. Phase 4：终审冲刺（Round 29-30）

### Round 29：跨页面一致性终审

- 全 17 页并排截图对比
- 检查维度：间距 grid、字号层级、surface elevation、动效节奏、品牌色使用
- 修正不一致项

### Round 30：最终评分 + Manifest 更新

- 逐页 5 维度评分：视觉层次 / 数据呈现 / 交互品质 / 一致性 / 品牌感
- 更新 `.edition-manifest.json`：
  - 新增 `iterationV4` 字段
  - 记录最终分数、rounds used、JS 模块统计
  - status: `v4-complete`
- Git tag: `edition/v1/iteration-v4-complete`

---

## 7. 预期产出

| 指标 | Before (v3) | After (v4 target) |
|------|-------------|-------------------|
| 平均分 | 9.14 | 9.7+ |
| 最低分 | 8.8 (markets-screener) | ≥ 9.5 |
| 最高分 | 9.3 (ai-overview, markets-intelligence) | ≥ 9.8 |
| inline styles 总数 | ~442 | < 100 |
| JS 模块数 | 9 | 12 |
| 品牌色 | V1 hue 255° C 0.165 | Ink Indigo hue 265° C 0.085 |

---

## 8. 风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| Ink Indigo APCA 不通过 | 低 | 备选：微调 lightness ±0.02 保持 hue/chroma 不变 |
| 30 轮不够 | 中 | Phase 3 新模块可裁剪（SkeletonPulse 优先级最低） |
| CSS 原型天花板 < 9.8 | 中 | 接受现实：~9.8 即为 HTML prototype 极限，10.0 需 React migration |
| inline 清剿引入回归 | 低 | 每轮结束 git diff 验证视觉不变 |

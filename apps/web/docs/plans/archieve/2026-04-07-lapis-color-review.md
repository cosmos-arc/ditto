# Lapis 品牌色切换后 — 全局配色审查报告

> **日期**: 2026-04-07
> **背景**: 品牌色从 Ink Indigo (hue 265) 切换至 Lapis (hue 235, chroma 0.120)
> **定位**: 内部量化工具，"Calibrated Intelligence" 设计哲学
> **参考**: [accent-color-exploration](../research/2026-04-05-accent-color-exploration.md), [color-system-v1-design](2026-04-03-color-system-v1-design.md), [key-design-decisions](../decisions/2026-03-28-key-design-decisions.md)

---

## 审查结论总览

| # | 层级 | 决策 | 变更 |
|---|------|------|------|
| 1 | Neutral Skeleton | 统一 hue 253 | style 层 hue 260 → 253 |
| 2 | Lapis 品牌色阶 | 微调 chroma | 300→0.065, 400→0.090 |
| 3 | Signature Brass | 3 触点扩展 | Rail 微光点 + 标题双色调渐变 |
| 4 | 市场色 Down | 回归 hue 155 | 175 (teal) → 155 (纯绿) |
| 5 | 风险色阶 | 5 级制去 Info | Info 改 neutral 灰 |
| 6 | 图表色板 | 主 4 色 + 亮度变体 | chart-5/6 改亮度区分 |
| 7 | 资产类别 Bond | hue 210 | 235 (Lapis) → 210 (偏青蓝) |
| 8 | Sparkline 硬编码 | 修为 token 引用 | CN 惯例 + CSS 变量 |

---

## 1. Neutral Skeleton — hue 253 统一

### 现状问题

三处定义不一致：

| 文件 | hue | 用途 |
|------|-----|------|
| `tokens-base.css` | 253 | 15 级灰阶 |
| `01-primitives.css` | 254 | 12 级灰阶 (runtime) |
| `tokens-style.css` | 260 | surface elevation 6 级 |

### 决策

**统一为 hue 253**。与 Lapis 235 相距 18°，中性灰带有微蓝倾向但不与 accent 混淆。Style 层的 260 偏紫过多，在 Lapis 切换后不协调。

### 业界对标

- **Vercel**: neutral hue ~255，accent ~265，间距 10°（更紧）
- **Linear**: neutral hue ~270，accent ~280，间距 10°
- **Bloomberg**: 无蓝味中性灰
- 我们的 18° 间距属于"微妙可感知但不过度"的区间，适合量化工具的专业感

---

## 2. Lapis 品牌色阶 — Chroma 微调

### 决策值（Dark Mode）

| Token | L | C (原→新) | H |
|-------|---|-----------|---|
| brand-300 | 0.830 | 0.050 → **0.065** | 235 |
| brand-400 | 0.760 | 0.080 → **0.090** | 235 |
| brand-500 | 0.640 | 0.120 (不变) | 235 |
| brand-600 | 0.540 | 0.100 (不变) | 235 |
| brand-700 | 0.450 | 0.080 (不变) | 235 |

### 理由

brand-300/400 用于浅色 accent 文字和 hover 态，chroma 过低时在暗背景上"读不出蓝色"。提升后：
- 300 从 0.050→0.065：浅色标签仍有品牌辨识
- 400 从 0.080→0.090：hover 态视觉反馈更明确
- 500-700 核心区间不变，保持 Lapis 沉稳基调

### 业界对标

- **Vercel**: accent chroma ~0.10（更灰）
- **Linear**: accent chroma ~0.12（相同）
- **TradingView**: accent chroma ~0.18（过饱和，不适合我们）
- 我们的 0.120 在"品牌辨识"与"专业克制"之间平衡良好

---

## 3. Signature Brass — 3 触点扩展

### 现状

Brass (hue 74) 仅出现在 `.style-label` 文字色，视觉面积 <0.5%。作为"品牌签名锚点"，存在感不足。

### 决策：新增 2 个触点

| 触点 | 实现 | 效果 |
|------|------|------|
| **Rail 当前页图标** | 图标下方加 Brass 微光点 (2px dot) | 最高频视觉锚点 |
| **页面标题下划线** | `brand-accent → brand-signature-fg → transparent` 三段渐变 | Lapis→Brass 双色调流动 |
| **保持现有** | style-label、shell marker、empty state | 不变 |

预估视觉面积: 0.5% → ~1.2%，仍在 1.5% 上限内。

### 设计哲学

"身份层在框架，功能层在内容"——Brass 出现在 Shell/Navigation 结构上，不出现在数据内容和交互元素中。

---

## 4. 市场色 — Down 回归 hue 155

### 现状问题

Prototype 的 Teal/Coral 调和将市场下跌色从 hue 155 (纯绿) 偏移至 hue 175 (青绿/teal)。与 Lapis 235 间距仅 60°，在暗背景上可能混淆。

### 决策

**Down 回归 hue 155**，与 Lapis 间距恢复至 80°。

| 方向 | 色相 | OKLCH 参考 | 与 Lapis 间距 |
|------|------|-----------|---------------|
| Up (涨) | 20 | oklch(0.670 0.170 20) | 215° |
| Down (跌) | **155** | oklch(0.680 0.120 155) | **80°** |
| Flat (平) | 253 | neutral | — |

Teal/Coral 审美可保留在 badge 背景层 (bg tint)，但前景指标色必须保证红/绿/蓝三色一目了然。

### 业界对标

- **Wind/Bloomberg**: 纯红纯绿，无调和，最高辨识度
- **TradingView**: 纯红纯绿
- **我们的选择**: hue 155 纯绿而非 175 teal，偏向专业工具的辨识度优先

---

## 5. 风险色阶 — 5 级制去 Info

### 现状问题

1. **Info hue 235 = Lapis 品牌色**，蓝色 badge 可能被误认为品牌 UI 而非风险等级
2. 6 级制偏多，用户在 Warning vs Moderate 之间犹豫

### 决策

**删除 Info 级别**，改为 neutral foreground-tertiary 灰色。保留 4 级真风险色 + 灰色"无风险"。

| 级别 | 用途 | 色相 |
|------|------|------|
| Critical | 严重违规/熔断 | red 25 |
| High | 高风险 | orange-red 40 |
| Warning | 警告 | amber 85 |
| Normal | 正常 | green 155 |
| Info → Neutral | 纯信息/无风险 | neutral gray (foreground-tertiary) |

### 理由

"Info"不是风险等级——它是"不需要关注的纯信息"。用灰色表达"无需行动"更准确，也避免与品牌色撞车。

---

## 6. 图表色板 — 主 4 色 + 亮度变体

### 决策

定义 4 个主色，5-6 序列使用已有色的亮度变体（明度 ±10%），而非引入新色相。

| 序号 | 色相 | OKLCH | 用途 |
|------|------|-------|------|
| chart-1 | 235 (Lapis) | oklch(65% 0.15 235) | 主序列 |
| chart-2 | 155 (绿) | oklch(70% 0.16 155) | 第二序列 |
| chart-3 | 85 (琥珀) | oklch(75% 0.15 85) | 第三序列 |
| chart-4 | 300 (紫) | oklch(60% 0.16 300) | 第四序列 |
| chart-5 | — | chart-1 亮度变体 (L+8%) | 第五序列 |
| chart-6 | — | chart-2 亮度变体 (L+8%) | 第六序列 |

### 理由

- 暗色模式下 6 个独立色相难以同时保持高辨识度
- 符合"每页不超过 4 个功能色家族"原则
- chart-4 (紫 300) 与 chart-1 (蓝 235) 间距 65° 仍可接受，因两者 chroma 和 lightness 差异明显

---

## 7. 资产类别 — Bond hue 调整

### 问题

Bond (债券) 用 hue 235 = Lapis 品牌色。在资产分配饼图中"债券"区块与品牌 accent 元素视觉混淆。

### 决策

Bond 改为 **hue 210** (偏青蓝)，与 Lapis 235 拉开 25°，但仍保持"蓝色系 = 稳健"的金融直觉。

| 资产 | 原 hue | 新 hue |
|------|--------|--------|
| Equity 股票 | 30 | 30 (不变) |
| **Bond 债券** | **235** | **210** |
| Commodity 商品 | 85 | 85 (不变) |
| FX 外汇 | 195 | 195 (不变) |
| Crypto 加密 | 300 | 300 (不变) |
| Derivative 衍生品 | 150 | 150 (不变) |

---

## 8. Sparkline 硬编码修复

### 问题

`page-home.html` 和 `page-markets-screener.html` 的 sparkline `data-sparkline` JSON 属性中硬编码了：

```json
{
  "strokeUp": "oklch(0.55 0.15 155)",   // 西方惯例: 绿=涨
  "strokeDown": "oklch(0.6317 0.1567 22.64)"  // 红=跌
}
```

这违反了 CN 市场惯例（红涨绿跌），且绕过了 token 系统。

### 决策

改为 JS 运行时读取 CSS token：

```javascript
const style = getComputedStyle(document.documentElement);
const marketUp = style.getPropertyValue('--market-up-fg').trim();
const marketDown = style.getPropertyValue('--market-down-fg').trim();
```

---

## 不需要变更的项

| 项目 | 现状 | 理由 |
|------|------|------|
| 热力图 5 级 (hue 235 单色) | ✅ | 单色热力图适合表达强度，与品牌一致 |
| 执行状态色 (5 级) | ✅ | Filled/Partial/Pending/Cancelled/Rejected 分布合理 |
| AI Agent 状态色 | ✅ | running=Lapis, idle=neutral, error=red, success=green, thinking=cyan |
| Signal 色 (buy/sell/hold) | ✅ | 继承市场色 + amber，无需额外调整 |
| System Status (3 级) | ✅ | healthy/degraded/down 清晰明了 |
| Data Quality (3 级) | ✅ | good/delayed/stale 合理 |
| Code block (hue 280) | ✅ | 紫色调代码块与主色系区分，保持 |

---

## 实施优先级

| 优先级 | 项目 | 影响 |
|--------|------|------|
| **P0** | Neutral hue 统一 253 | 全局影响，一切色彩的基础 |
| **P0** | Lapis chroma 微调 (300/400) | 品牌色核心 |
| **P0** | Sparkline 硬编码修复 | CN 市场惯例违反 |
| **P1** | 市场色 Down hue 155 | 数据辨识度 |
| **P1** | 风险色阶去 Info | 语义清晰度 |
| **P1** | Bond hue 210 | 图表可读性 |
| **P2** | 图表色板 4+2 | 使用频次低于 P0/P1 |
| **P2** | Brass 3 触点扩展 | 品牌身份提升，非功能阻塞 |

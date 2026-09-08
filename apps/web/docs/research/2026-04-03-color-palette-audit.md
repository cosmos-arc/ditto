# Ditto 配色体系审计 — 行业定位 + 原型 Token 执行质量

> 日期：2026-04-03
> 背景：评估当前品牌色和整体配色是否落入 AI 设计的标准传统配色；审计原型 token 体系的执行精度

---

## 一、结论速览

| 维度 | 评分 | 说明 |
|------|------|------|
| 远离 AI Slop | **9/10** | 紫/渐变/发光全部避开，视觉宪章纪律强 |
| 色彩架构成熟度 | **10/10** | 7 域语义色 + 9 层 token，业界罕见 |
| 品牌独特性 | **5/10** | 品牌蓝 hue 263° 落在 indigo 邻域，冷灰 260° 落在 Linear 族 |
| 金融工具适配度 | **9/10** | 涨跌色/域色/色盲安全完备 |
| 长时间使用舒适度 | **7/10** | 冷灰长时间盯看略感冰冷 |

**Ditto 不是 AI Slop，但归入了 "Premium Dark Tech" 族。**

---

## 二、族谱定位

```
  AI Slop                    Premium Dark Tech          金融传统
  ─────────────────────────   ────────────────────────   ─────────────
  ChatGPT 紫 (~290°)         Linear (Magic Blue)         Bloomberg 琥珀
  Claude 橙-棕                Vercel (Geist Blue)         TradingView 深色
  Gemini 蓝                   Raycast                     Wind/同花顺
  Copilot 紫                  Arc Browser                 ┈┈┈┈┈┈┈┈┈┈
  ┈┈┈┈┈┈┈┈┈┈                 Stripe                      Ditto ←
                              ┈┈┈┈┈┈┈┈┈┈
                              ★ Ditto 在这里
```

**关键数字对比：**

| 产品 | 品牌色色相 | 中性色色温 |
|------|-----------|-----------|
| Linear | ~234° (Magic Blue) | 正在转向暖灰 |
| Vercel | ~220° (Geist Blue) | 冷灰 |
| Tailwind 默认 | 239° (Indigo-500) | 冷灰 |
| **Ditto** | **~263° (OKLCH)** | **冷灰 260°** |
| Stripe | ~260° (Stripe Blue) | 微暖灰 |

品牌蓝 `oklch(0.664 0.160 263)` + 石墨灰 hue 260 + 深色默认 = 整体观感接近 Linear / Vercel / Stripe。

---

## 三、已避开的 AI Slop 特征

| AI Slop 特征 | Ditto 状态 |
|---|---|
| 紫-蓝渐变 | 完全没有 |
| 霓虹发光效果 | 视觉宪章明确禁止 |
| 粉紫色极光背景 | 不存在 |
| ChatGPT 紫色系 (~290°) | 品牌色 hue 263°，远离 |
| 三列卡片 + 居中 Hero | 布局体系完全不同 |
| 纯白/纯黑 | 所有表面都带 hue 260 色温 |

---

## 四、Ditto 配色的核心优势

### A. 7 域语义色系统 — 最强视觉资产

```
Market 域     红/绿 + CN/Intl 区域切换
Risk 域       低/中/高/危险 4 级 + near-limit/breach
Execution 域  pending/partial/filled/cancelled/rejected
System 域     healthy/degraded/stale/down/recovering
DataQuality 域 fresh/delayed/missing/partial/revised
Model 域      stable/degrading/drifting/invalid/candidate
Agent 域      idle/running/waiting/blocked/failed
```

Linear / Vercel / Stripe 只有品牌色 + 语义色（success/warning/error），没有业务域色彩语义化。

### B. 市场区域感知

`[data-market-region="cn"]` / `[data-market-region="intl"]` 涨跌色切换，考虑中国用户认知习惯。

### C. Paul Tol 色盲安全数据可视化

科学背书，不是"看着好看就行"。

### D. 15 级中性色 + 6 级表面层级

UI 层次感可控到极高精度。

---

## 五、风险点

### 风险 1：品牌蓝 hue 263° 在 indigo 邻域（严重程度：中）

- 接近 Tailwind Indigo（Adam Wathan 公开道歉："我让地球上所有 AI 生成的 UI 都变成了 indigo"）
- 接近 Shopify Polaris 主操作色
- 但 Ditto 品牌色使用克制（< 5% 视觉面积），实际影响有限

### 风险 2：冷灰 hue 260° 趋势逆风（严重程度：低-中）

- Linear 2026.3 转向 warm gray："inch toward a warmer gray that still feels crisp, but less saturated"
- Adobe / Canva 2026 趋势指向 warm neutrals 和 earthy tones
- 冷灰长时间使用略感冰冷，对 8h+/天的量化交易员可能有舒适度影响

### 风险 3："Premium Dark Tech" 同质化（严重程度：视场景）

- Linear / Vercel / Raycast / Arc / Cursor / Windsurf 同族
- 内部工具无影响；如需对外展示（demo / pitch deck），"又一个 Linear 风格"不利于品牌记忆

---

## 六、待定优化方案

### 方案 A：维持现状（推荐内部工具）

- 改动：零
- 理由：内部工具，Linear 级审美已足够；7 域语义色才是视觉核心
- 适用：Ditto 只在内部使用，未来 12 个月无对外展示需求

### 方案 B：微暖调整（性价比最高）

- 改动：中性色 hue 260° → 255° + 品牌蓝微调到 ~258°
- 效果：脱离冷灰族视觉指纹；屏幕长时间使用更舒适
- 代价：需重新验证所有域色的对比度

### 方案 C：引入第二强调色（最大差异化）

- 改动：保留品牌蓝做功能强调，引入 teal/cyan 或 warm amber 做品牌识别
- 效果：立刻脱离 "又一个蓝灰 SaaS"
- 代价：需增加 token 层，设计第二强调色的完整语义映射

---

## 七、参考来源

- [Why Your AI Keeps Building the Same Purple Gradient Website](https://prg.sh/ramblings/Why-Your-AI-Keeps-Building-the-Same-Purple-Gradient-Website)
- [AI Purple Problem: Make Your UI Unmistakable](https://dev.to/jaainil/ai-purple-problem-make-your-ui-unmistakable-3ono)
- [Why Does AI Have an Indigo Obsession in Web Design?](https://gradientshub.com/blog/why-does-ai-have-and-indigo-obsession-in-web-design/)
- [The One Color Decision That Makes a UI Look Expensive](https://pixicstudio.medium.com/color-decision-premium-ui-design-d6890efe11ba)
- [Fintech Brand Colors Guide](https://www.patrickhuijs.com/blog/fintech-brand-colors-guide)
- [Designing the Bloomberg Terminal for Color Accessibility](https://www.bloomberg.com/company/stories/designing-the-terminal-for-color-accessibility/)
- [A calmer interface for a product in motion - Linear](https://linear.app/now/behind-the-latest-design-refresh)
- [Geist Colors - Vercel](https://vercel.com/geist/colors)
- [2026 Design Trends - Adobe](https://www.adobe.com/express/learn/blog/design-trends-2026)
- [2026 Design Trends - Canva](https://www.canva.com/newsroom/news/design-trends-2026/)

---

# 附录：原型 Token 体系执行质量审计

> 审计范围：`prototype/shared/` 下 9 个 token 文件 + `tokens-style.css`
> 说明：生产 `src/styles/globals.css` 仅落地了原型 token 的 ~40%，本节审计的是原型设计规格本身

---

## A. 总评

**架构设计 9.5/10，执行精度 7/10。**

9 层分层、7 域语义、OKLCH 空间、Paul Tol 色板等设计决策属于行业顶尖。但具体 token 值的执行存在系统性问题。

| 维度 | 分 | 说明 |
|------|----|------|
| 分层架构 | **9.5** | 9 层职责清晰，从 primitive 到 density |
| 色彩空间选型 | **10** | OKLCH + Paul Tol，无可挑剔 |
| 域语义设计 | **9** | 7 域覆盖完整，但 bg 值大量复制粘贴 |
| Token 值精度 | **6.5** | neutral 色相不一致、semantic 硬编码、functional 命名歧义 |
| 双主题完整性 | **7** | light mode 覆盖不完整（banner、intl 组合、quaternary） |
| 代码卫生 | **7** | 冗余定义、缺失中间变量 |
| 可维护性 | **7.5** | 引用链断裂（semantic 层不引用 base 层） |

---

## B. P0 — 结构性问题

### B1. 中性色色相不一致（241°-254°，跨度 13°）

15 级 neutral primitive 的色相从 neutral-0 (254.17°) 到 neutral-400 (241.39°) 波动剧烈。在 OKLCH 中 13° 的色相偏移在中性灰上肉眼可辨。

| Token | Hue |
|-------|-----|
| neutral-0 | 254.17 |
| neutral-100 | 251.45 |
| neutral-200 | **246.97** |
| neutral-400 | **241.39** ← 最大偏移 |
| neutral-900 | 244.73 |

Graphite Studio 用 hue=260 统一覆盖掩盖了此问题，但 base 层本身不干净。未来换风格或维护时会暴露。

### B2. Semantic 层硬编码绕过了 primitive 引用链

`tokens-semantic.css` 中 surface/text/border 使用硬编码 oklch 值而非 `var(--neutral-X)`：

| Semantic Token | 硬编码 L | 对应 Primitive L | 偏差 |
|----------------|---------|-----------------|------|
| --surface-app | 0.155 | --neutral-0: 0.1665 | -0.0115 |
| --surface-panel-base | 0.185 | --neutral-25: 0.1844 | +0.0006 |
| --surface-panel-elevated | 0.215 | --neutral-75: 0.2146 | +0.0004 |

语义层应引用基础层。当前调整 primitive 时 semantic 不会跟随，打破了分层架构的设计意图。

### B3. Domain bg 值大面积复制粘贴

以下值被 4-5 个不同域重复使用，应提取为中间变量：

| 值 | 使用次数 | 建议变量名 |
|----|---------|-----------|
| `oklch(0.2280 0.0238 162 / 0.2)` | 4+ 域 | `--domain-green-bg` |
| `oklch(0.2229 0.0212 76.17 / 0.2)` | 5+ 域 | `--domain-amber-bg` |
| `oklch(0.2165 0.0265 47.45 / 0.2)` | 3 域 | `--domain-orange-bg` |
| `oklch(0.2242 0.0365 8.74 / 0.25)` | 5+ 域 | `--domain-red-bg` |
| `oklch(0.2242 0.0365 8.74 / 0.3)` | 2 域 | `--domain-red-critical-bg` |

---

## C. P1 — 一致性问题

### C1. Functional primitives 400/500/600 命名不符合亮度逻辑

| Level | Green L | 与上级 Delta |
|-------|---------|-------------|
| 400 | 0.4479 | — |
| 500 | 0.6442 | **+0.20** |
| 600 | 0.7055 | +0.06 |

400→500 跳了 0.20，500→600 只跳了 0.06。所有 6 个功能色都有相同模式。对比 brand 是 300→700 均匀递减的，两套命名范式混用。

### C2. Graphite surface-strip (L=0.180) 低于 surface-panel-base (L=0.185)

Graphite 覆盖将 strip 设为比 panel-base 更暗，与 elevation 层级的语义矛盾。Base semantic 中两者相同（L=0.185），是合理的。

### C3. 缺少 light mode 的 feedback banner 覆盖

`tokens-interaction.css` 的 light mode 块只覆盖了 hover/active/dragging，warning/critical banner 在 light 下沿用 dark 值。

### C4. Domain fg 色相与 base primitives 偏离

| Domain Token | 色相 | 最接近 Primitive | 偏差 |
|-------------|------|----------------|------|
| --market-down-fg | 175° | green-500: 156.74° | **+18°** (向 teal 偏移) |
| --risk-critical-bg | 8.74° | red-500: 22.64° | **-14°** (向橙红偏移) |
| --agent-running-bg | 261.76° | brand-500: 263.63° | -2° (微小) |

market-down 的 18° 偏移已从 green 跨入 teal。

---

## D. P2 — 完整性缺口

| 缺失项 | 文件 | 影响 |
|--------|------|------|
| `info` / `success` banner token | tokens-interaction.css | 只有 warning/critical |
| `intl + light` 组合覆盖 | tokens-domain.css | 国际涨跌色在亮色下 alpha 不对 |
| `text-quaternary` / `text-data-stale` 的 Graphite light 覆盖 | tokens-style.css | 亮色四级文本走 base 值 |
| `overlay-5` | tokens-semantic.css | 梯度从 4 跳到 6 |
| motion `x-slow`（500ms） | tokens-base.css | modal/page transition 无可用时长 |

---

## E. P3 — 代码卫生

| 问题 | 位置 |
|------|------|
| density compact 预设与 :root 100% 重复 | tokens-density.css |
| font-family 在 base 和 style 层重复定义 | tokens-base.css + tokens-style.css |
| sparkline 尺寸在 data-viz 和 style 层重复 | tokens-data-viz.css + tokens-style.css |
| Graphite domain critical bg C=0.180 与 "clean graphite" 风格矛盾 | tokens-style.css |

---

## F. 优化建议（按落地生产优先级排序）

1. **修复 base neutral 色相** — 用 OKLCH 统一色相到目标值（如 254° 或 260°），确保 15 级梯度只变 L 和 C
2. **Semantic 层改用 `var()` 引用** — 替换硬编码值为 `var(--neutral-X)` 引用，保持引用链完整
3. **提取 domain 中间变量** — 创建 `--domain-{color}-bg` 变量消除复制粘贴
4. **补全 light mode 覆盖** — feedback banner、intl 组合、text-quaternary
5. **统一 functional 命名** — 要么把 400 改名为 "dark" 语义，要么补齐 300/700 级别
6. **修复 Graphite surface-strip 亮度** — 设为 ≥ panel-base

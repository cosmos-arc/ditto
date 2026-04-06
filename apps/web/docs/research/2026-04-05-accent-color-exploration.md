# 交互色探索：Ink Indigo 方向确认

> 日期：2026-04-05
> 状态：Direction Confirmed（待 token scale 定稿 + APCA 校验）
> 前置文档：[color-system-v1-design.md](../plans/2026-04-03-color-system-v1-design.md)

---

## 1. 背景

V1 配色体系（Graphite Studio / Calibrated Intelligence）已完成实施。暗色骨架（hue 253°）和 Brass 身份层（hue 74°）表现良好，但 **brand-accent 交互蓝** 存在审美问题：

- hue 255° 的靛蓝太大众化 SaaS 脸
- 与 Brass 暖色搭配在按钮上"特别土"
- 骨架 (253°) 和交互蓝 (255°) 只差 2°，层次感不足

本次探索目标：在保持暗色骨架 + Brass 身份层 + 7 域语义色不变的前提下，寻找更具高级感的交互色。

---

## 2. 探索过程

共 6 轮、28+ 方案对比，通过自包含 HTML Demo 页面在同一视口内并排展示。

### Round 1 — 5 种基础方向

| 方案 | Hue | 结论 |
|------|-----|------|
| Current V1 (对照) | 255° | 问题基线 |
| Teal Steel | 185° | 方向好但偏 fintech startup |
| Warm Copper | 28° | 与 Brass 太近 |
| Frost Blue | 220° | 低饱和蓝灰，安全但不够独特 |
| Electric Cyan | 200° | AI 气质但饱和度偏高 |

### Round 2 — 5 种个性方向

| 方案 | Hue | 结论 |
|------|-----|------|
| Sage Moss | 155° | 绿域，排除 |
| Slate Violet | 295° | 有趣但不够克制 |
| Arctic Mint | 170° | 偏绿，排除 |
| Desert Sand | 55° | 与 Brass 太近 |
| Obsidian Rose | 345° | 最大胆但非此方向 |

### Round 3 — 5 种极致方向

| 方案 | Hue | 结论 |
|------|-----|------|
| Champagne Gold | 80° | 与 Brass 几乎重叠 |
| Petrol Deep | 195° | 沉稳但偏工具感 |
| **Ink Indigo** | **265°** | **命中方向，克制高级** |
| Burnt Sienna | 18° | 红域，排除 |
| Phantom Silver | 253° | 近无色，太极端 |

### Round 4 — 蓝青紫域 5 种精选

| 方案 | Hue | 结论 |
|------|-----|------|
| Blueprint Blue | 230° | 理性但不独特 |
| Dusk Lavender | 280° | 暖紫，有潜力 |
| Cerulean Depth | 210° | 深空感但偏传统 |
| Dusty Plum | 310° | 奢侈品质感但色域偏远 |
| Steel Teal | 190° | 冷锐但偏青 |

### Round 5 — 8 种蓝青紫弧段深度采样

Prussian Blue / Lapis Lazuli / Cobalt Night / Wisteria / Glacier Ice / Amethyst Smoke / Sapphire Steel / Iris Mist

确认 Ink Indigo 方向最优后，进入 Round 6 精调。

### Round 6 — Ink Indigo 微调 + 暖色系对照

**Ink Indigo 4 变体：**

| 变体 | 调整 | 感受 |
|------|------|------|
| Ink Indigo (基线) | hue 265° C=0.060 | 稍淡，按钮存在感弱 |
| Ink · Warm Shift | hue 258° C=0.055 | 偏暖，接近骨架 |
| Ink · Cool Shift | hue 272° C=0.065 | 偏紫，性格变化 |
| **Ink · More Pigment** | **hue 265° C=0.085** | **按钮有存在感但不喊叫，最终选定** |

---

## 3. 选定方案

### Ink Indigo · More Pigment

```
hue: 265°
chroma: 0.085（极低饱和）
lightness: 0.700（交互级亮度）
```

### 为什么高级

1. **克制 = 高级**：C=0.085 是"有存在感但不喊叫"的临界点。奢侈品设计的铁律：越贵的品牌颜色越安静。
2. **材料级配色**：不是"被选出来的颜色"，是石墨里自然渗透出来的深色。Montblanc 墨水 + Moleskine 笔记本的气质。
3. **业界无先例**：没有任何量化平台使用此方向。Bloomberg 用橙、TradingView 用蓝绿、Thinkorswim 用绿。Ink + Brass 组合为 Ditto 独有。

### 与现有体系的搭配

| 体系层 | Hue | 与 Ink (265°) 关系 |
|--------|-----|--------------------|
| 中性骨架 | 253° | 差 12°，同族不同层 |
| Brass 身份 | 74° | 差 191°，近互补张力而非对冲 |
| Market 涨 | 20° | 差 245°，远距离互补无冲突 |
| Market 跌 | 175° | 差 90°，正交无干扰 |

---

## 4. 候选 Token Scale（待 APCA 校验）

```css
:root {
  /* Brand Primitives — Ink Indigo */
  --brand-300: oklch(0.850 0.045 265);
  --brand-400: oklch(0.785 0.065 265);
  --brand-500: oklch(0.700 0.085 265);  /* 核心交互色 */
  --brand-600: oklch(0.615 0.072 265);
  --brand-700: oklch(0.525 0.058 265);
}

[data-theme="light"] {
  --brand-300: oklch(0.670 0.060 267);
  --brand-400: oklch(0.610 0.080 266);
  --brand-500: oklch(0.550 0.100 265);
  --brand-600: oklch(0.490 0.088 266);
  --brand-700: oklch(0.430 0.072 267);
}
```

### 与 V1 现有值的对比

| Token | V1 (当前) | Ink Indigo (候选) | 变化 |
|-------|----------|-------------------|------|
| brand-500 hue | 255° | 265° | +10° 偏紫 |
| brand-500 chroma | 0.165 | 0.085 | -48% 饱和度 |
| brand-500 lightness | 0.700 | 0.700 | 不变 |

核心变化：**同一亮度下饱和度减半**，从"蓝色"变成"墨色"。

---

## 5. 下一步

1. **APCA 校验**：验证 brand-500 在 surface-app / surface-panel / surface-elevated 上的对比度
2. **light mode token 定稿**：确保亮色模式下 Ink Indigo 仍有辨识度
3. **Brass 共存视觉确认**：在真实页面中验证 ink + brass 同画面无冲突
4. **domain 色交叉验证**：确认 ink 不干扰 risk / execution / agent 等域语义色
5. **实施迁移**：更新 tokens-base.css brand primitive → 全链路生效

---

## 6. 业界先例

| 品牌 | 配色 | 和 Ditto 的关系 |
|------|------|----------------|
| Montblanc | 深墨蓝 + 金色硬件 | 几乎同构：ink accent + brass signature |
| Moleskine | 无色封面 + 内页墨迹 | 骨架无色，信息层才有色 |
| Linear App | 极低饱和紫灰 | 证明低饱和 = 高级的路线可行 |
| Bang & Olufsen | 石墨壳 + 金色细节 | 材料级的克制 |

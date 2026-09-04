# 交互色探索：Lapis Blue 方向确认

> 日期：2026-04-05（初版 Ink Indigo），2026-04-06（修订为 Lapis）
> 状态：Direction Confirmed — Lapis (hue 235°) 已选定
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

### Phase 1：Ink Indigo 方向（已废弃）

共 6 轮、28+ 方案对比。Round 1-5 探索了 28+ 色相方向后锁定 Ink Indigo (hue 265°)，Round 6 精调选定 `Ink · More Pigment` (hue 265°, C=0.085)。

**废弃原因**：在深色主题实际页面验证中，Ink Indigo 与深色骨架搭配感不佳——饱和度太低导致交互色缺乏存在感，偏紫 hue 265° 在暗底上显得沉闷。

### Phase 2：Lapis Blue 方向（最终选定）

在 Ink Indigo 废弃后，重新评估蓝域候选。关键约束：

1. 色相需远离涨跌色（红 hue 25° / 绿 hue 155°）→ 安全区 210°-260°
2. 色相需与 Brass (hue 75°) 保持清晰距离 → 避免暖色域
3. 暗色主题下有足够存在感 → chroma 不能太低

候选对比：

| 候选 | Hue | Chroma | 结论 |
|------|-----|--------|------|
| Ink Indigo | 265° | 0.085 | 与深色搭配沉闷，已废弃 |
| **Lapis** | **235°** | **0.120** | **选中：奢侈品克制气质 + 暗色存在感** |
| Cobalt | 248° | 0.140 | 更饱和更专业，但偏主流 TradingView/Coinbase 风格 |
| Dark Honey | 50° | 0.120 | 与 Brass (75°) 仅差 25°，破坏三层架构 |

### Lapis 选中理由

1. **业界罕见**：无量化平台使用此色相方向（Bloomberg 橙、TradingView 蓝绿、Thinkorswim 绿）
2. **奢侈品克制气质**：C=0.120 保持"有存在感但不喊叫"的临界点
3. **三层色彩架构清晰**：
   - 与 Brass (75°) 距离 160° — 清晰分层
   - 与涨红 (25°) 距离 210° — 安全隔离
   - 与跌绿 (155°) 距离 80° — 正交无干扰
4. **暗色主题表现优异**：在 Home / AI Copilot / Research 三个页面实际验证，Lapis 按钮和交互元素在深色底上辨识度高且不刺眼

---

## 3. 选定方案

### Lapis Blue — hue 235°, chroma 0.120

```css
:root {
  /* Brand Primitives — Lapis Blue hue 235 */
  --brand-300: oklch(0.830 0.050 235);
  --brand-400: oklch(0.760 0.080 235);
  --brand-500: oklch(0.640 0.120 235);
  --brand-600: oklch(0.540 0.100 235);
  --brand-700: oklch(0.450 0.080 235);
}

[data-theme="light"] {
  --brand-300: oklch(0.660 0.050 235);
  --brand-400: oklch(0.610 0.080 235);
  --brand-500: oklch(0.550 0.100 235);
  --brand-600: oklch(0.490 0.088 235);
  --brand-700: oklch(0.430 0.078 235);
}
```

### 与现有体系的搭配

| 体系层 | Hue | 与 Lapis (235°) 关系 |
|--------|-----|---------------------|
| 中性骨架 | 253° | 差 18°，同族不同层 |
| Brass 身份 | 74° | 差 161°，清晰分层 |
| Market 涨 | 20° | 差 215°，远距离安全 |
| Market 跌 | 155° | 差 80°，正交无干扰 |

### 与 V1 原始值的对比

| Token | V1 原始 | Lapis (选定) | 变化 |
|-------|---------|-------------|------|
| brand-500 hue | 255° | 235° | -20° 偏蓝 |
| brand-500 chroma | 0.165 | 0.120 | -27% 饱和度 |
| brand-500 lightness | 0.700 | 0.640 | -8% 更沉稳 |

---

## 4. 下一步

1. **APCA 校验**：验证 brand-500 在 surface-app / surface-panel / surface-elevated 上的对比度
2. **light mode token 定稿**：确保 Lapis 在亮色模式下仍有辨识度
3. **生产源 token 同步**：`src/styles/tokens/01-primitives.css` 更新
4. **domain 色交叉验证**：确认 Lapis 不干扰 risk / execution / agent 等域语义色

---

## 5. 业界先例

| 品牌 | 配色 | 和 Ditto 的关系 |
|------|------|----------------|
| Montblanc | 深墨蓝 + 金色硬件 | 类似结构：Lapis accent + Brass signature |
| Bang & Olufsen | 石墨壳 + 金色细节 | 材料级的克制 |
| Vercel | 极低饱和冷灰蓝 | 证明冷蓝 + 深色可行 |
| Linear App | 低饱和紫灰 | 证明低饱和 = 高级的路线可行 |

### Chroma 微调 (2026-04-07)

brand-300 chroma 0.050→0.065, brand-400 chroma 0.080→0.090 — 提升浅色级蓝色辨识度，与 Lapis 235° 主色调更协调。同时 neutral hue 统一为 253°，market-down hue 175→155° 纯绿。

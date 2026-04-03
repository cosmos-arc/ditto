# Ditto 配色 9.5+ 升级设计（V1）

> 日期：2026-04-03
> 状态：Draft
> 基线：以 prototype token 为准，不以当前 runtime token 为准

---

## 1. 背景

当前 Ditto 原型配色体系已经具备明显优势：

- 7 域业务语义色完整
- `data-market-region` 已考虑中外涨跌认知差异
- 品牌蓝已从典型 indigo 区域收敛到更克制的交互色
- 视觉宪章明确反对 AI Slop 的渐变、发光、过度装饰

但如果目标从“优秀”提升到“行业领先”，仍有两个关键指标需要继续拉高：

1. **品牌独特性**：脱离蓝灰 SaaS 同质化
2. **长时间使用舒适度**：支持量化用户 8h+ 高频盯屏

本设计的任务不是推翻现有体系，而是在不伤害业务语义表达的前提下，为 Ditto 建立更强的品牌识别与更稳的暗色工作台体验。

---

## 2. 本次设计结论

### 2.1 风格名与理念分离

- **视觉风格名**：继续使用 `Graphite Studio`
- **设计理念 / 品牌叙事**：使用 `Calibrated Intelligence`

二者不是同一层概念，不应混用。

`Graphite Studio` 描述的是外观系统；`Calibrated Intelligence` 描述的是产品气质，即“像被校准过的专业仪器，而不是一套蓝灰 SaaS 皮肤”。

### 2.2 V1 的核心方向

V1 采用 **四通道角色分离**：

1. `Neutral Skeleton`：中性骨架，负责 surface / text / border
2. `Interaction Blue`：交互工具色，负责 focus / selected / CTA
3. `Signature Brass`：品牌身份色，负责 shell / context / 空状态等低频品牌触点
4. `Domain Semantic`：业务语义色，继续负责 Market / Risk / Execution / System / Data Quality / Model / Agent

此版本的关键目标是：

- 让蓝色不再同时承担“品牌”和“按钮”
- 让黄铜身份色承担“Ditto 是谁”
- 让 7 域语义色继续承担“系统当前发生了什么”

### 2.3 V1 的品牌意图确认

V1 的设计意图不是把品牌从 `indigo / violet` 彻底推向 `true blue`。

因此，上一轮草案中将 interaction blue 候选值下探到 `hue 251°` 的方向，**不再采用**。原因有二：

1. 它会明显改变当前 Graphite Studio 的品牌性格
2. 它与计划中的 neutral spine `253°` 过于接近，容易削弱感知分层

V1 的正确策略是：

- **neutral skeleton** 收敛到 `253°` 的 achromatic-neutral 方向
- **interaction blue** 保持在 `255°-257°` 区间，延续现有 Graphite Studio 的交互气质
- **signature brass** 负责额外品牌记忆点，而不是靠 brand hue 的大幅漂移来制造差异

也就是说，V1 不是 “263 → 251” 的品牌换性格方案，而是：

> **保住当前交互蓝气质，修复 primitive 引用链，并让 brass 承担新的品牌身份层。**

---

## 3. V1 需要修正的认识

### 3.1 `253°` 不叫 warm，叫 `achromatic-neutral`

本次设计不再使用“微暖 graphite”表述。

将 surface hue 从 `260°` 收敛到 `253°` 的真实意图不是“变暖”，而是：

- 降低蓝紫偏置
- 在极低 chroma 下更接近 achromatic neutral
- 降低“又一个冷蓝灰开发者工具”的既视感

因此，V1 的中性骨架目标应定义为：

> **Neutralized Graphite**
> 去蓝偏、低色偏、长时间稳定的石墨中性骨架

如果未来确实要做“暖感”，应由 `Signature Brass` 或独立暖中性方案承担，而不是把 `253°` 称为 warm。

### 3.2 文本层级调整必须先通过 APCA / WCAG 双重验证

V1 不接受一次性大幅抬升 `text-secondary` / `text-tertiary`。

原因：

- 量化工作台的高密环境中，primary 与 secondary 的区分度比“整体更亮”更重要
- 表格、面板、标签、时间戳等元素层级复杂，文本梯度过窄会削弱扫描效率

V1 的原则是：

- 先计算当前值在 `surface-app` / `surface-panel-base` / `surface-panel-elevated` 上的 APCA Lc
- 再计算候选值
- 以“区分度 + 可读性”共同最优为目标，而不是仅凭视觉直觉提亮

### 3.3 Brass hairline 不能过度依赖 alpha

`Signature Brass` 的身份感能否成立，很大程度取决于 1px marker / line 是否真正可见。

因此 V1 规定：

- `brand-signature-line` 作为独立实色 token 定义
- 不使用过轻 alpha 作为默认 hairline 方案
- 如果使用 alpha 变体，透明度不低于 `0.55`

换句话说：

> Brass 可以克制，但不能蒸发。

---

## 4. V1 范围与 V2 范围

### 4.1 V1 必做

- 重建 `neutral primitive` 的色相一致性
- 建立 `semantic -> primitive` 的明确引用链
- 引入 `Signature Brass` 的 dark / light 双主题 token
- 保持 `Interaction Blue` 只承担交互职责
- 保持 7 域语义色职责边界不变
- 舒适度模式只提供 `standard` 与 `high-contrast`

### 4.2 V1 不做

- 不做模块微气候的全量铺开
- 不做 `night-soft` 第三舒适度档
- 不做第二套大规模主题变体
- 不让 brass 进入 Risk / Market / Execution / System 的状态系统

### 4.3 V2 再考虑

- `data-module="research|trading|risk|agent"` 的模块微气候
- `night-soft` 模式
- 更精细的 module pattern token
- 单模块试点验证（优先 Research）

---

## 5. 建议 Token（V1 方向值）

以下数值为 **方向候选值**，需在 APCA / WCAG 校验后定稿。

```css
:root {
  /* Neutral Primitives — full 15-step candidate scale */
  --neutral-0:   oklch(0.166 0.010 253);
  --neutral-25:  oklch(0.184 0.011 253);
  --neutral-50:  oklch(0.198 0.012 253);
  --neutral-75:  oklch(0.215 0.012 253);
  --neutral-100: oklch(0.240 0.013 253);
  --neutral-150: oklch(0.261 0.014 253);
  --neutral-200: oklch(0.303 0.015 253);
  --neutral-300: oklch(0.342 0.013 253);
  --neutral-400: oklch(0.420 0.012 253);
  --neutral-500: oklch(0.495 0.011 253);
  --neutral-600: oklch(0.594 0.009 253);
  --neutral-700: oklch(0.707 0.008 253);
  --neutral-800: oklch(0.814 0.006 253);
  --neutral-900: oklch(0.920 0.004 253);
  --neutral-950: oklch(0.978 0.002 253);

  /* Brand Primitives — keep Graphite Studio blue personality */
  --brand-300: oklch(0.820 0.090 258);
  --brand-400: oklch(0.760 0.130 257);
  --brand-500: oklch(0.700 0.165 255);
  --brand-600: oklch(0.620 0.150 255);
  --brand-700: oklch(0.530 0.130 256);

  /* Neutralized Graphite — semantic layer uses primitive mapping */
  --surface-app:            var(--neutral-0);
  --surface-panel-base:     var(--neutral-25);
  --surface-panel-elevated: var(--neutral-75);
  --surface-strip:          var(--neutral-25);
  --surface-overlay:        oklch(0.255 0.006 253);
  --surface-modal:          oklch(0.290 0.007 253);

  --text-primary:           oklch(0.925 0.004 253);
  --text-secondary:         oklch(0.655 0.007 253);
  --text-tertiary:          oklch(0.555 0.007 253);
  --text-quaternary:        oklch(0.490 0.006 253);
  --text-disabled:          oklch(0.415 0.005 253);

  --border-subtle:          oklch(0.255 0.006 253);
  --border-default:         oklch(0.325 0.008 253);
  --border-strong:          oklch(0.425 0.010 253);

  /* Interaction Blue */
  --brand-accent:           var(--brand-500);
  --brand-accent-hover:     var(--brand-400);
  --brand-accent-subtle:    oklch(from var(--brand-500) l c h / 0.10);

  /* Signature Brass - dark */
  --brand-signature-fg:     oklch(0.760 0.055 74);
  --brand-signature-muted:  oklch(0.660 0.040 74);
  --brand-signature-line:   oklch(0.620 0.040 74);
  --brand-signature-subtle: oklch(0.760 0.055 74 / 0.08);
}

[data-theme="light"] {
  --neutral-0:   oklch(0.988 0.001 253);
  --neutral-25:  oklch(0.958 0.002 253);
  --neutral-50:  oklch(0.944 0.002 253);
  --neutral-75:  oklch(0.932 0.003 253);
  --neutral-100: oklch(0.900 0.004 253);
  --neutral-150: oklch(0.860 0.005 253);
  --neutral-200: oklch(0.810 0.006 253);
  --neutral-300: oklch(0.720 0.008 253);
  --neutral-400: oklch(0.640 0.009 253);
  --neutral-500: oklch(0.560 0.010 253);
  --neutral-600: oklch(0.470 0.010 253);
  --neutral-700: oklch(0.390 0.010 253);
  --neutral-800: oklch(0.300 0.009 253);
  --neutral-900: oklch(0.200 0.007 253);
  --neutral-950: oklch(0.150 0.006 253);

  --surface-app:            var(--neutral-0);
  --surface-panel-base:     var(--neutral-25);
  --surface-panel-elevated: var(--neutral-75);
  --surface-strip:          var(--neutral-25);
  --surface-overlay:        oklch(0.995 0.000 0);
  --surface-modal:          oklch(0.998 0.000 0);

  --brand-300: oklch(0.660 0.110 259);
  --brand-400: oklch(0.610 0.145 258);
  --brand-500: oklch(0.550 0.185 258);
  --brand-600: oklch(0.490 0.175 259);
  --brand-700: oklch(0.430 0.155 260);

  --brand-signature-fg:     oklch(0.520 0.060 72);
  --brand-signature-muted:  oklch(0.470 0.050 72);
  --brand-signature-line:   oklch(0.440 0.045 72);
  --brand-signature-subtle: oklch(0.520 0.060 72 / 0.10);
}
```

### 5.1 关于 primitive 引用链的硬性要求

V1 不允许只修改 `--brand-accent` 而不修改 `--brand-300~700`。

原因很明确，当前 prototype 共享层中已有多个地方直接消费 brand primitive：

- `--text-link` / `--brand-accent` 使用 `var(--brand-500)`，见 [tokens-semantic.css](../designs/specs/prototypes/shared/tokens-semantic.css#L32)
- `--agent-running-fg` 使用 `var(--brand-500)`，见 [tokens-domain.css](../designs/specs/prototypes/shared/tokens-domain.css#L75)
- `action-priority.medium` / `alert-dot.info` 等共享样式也使用 `var(--brand-500)`，见 [layout-base.css](../designs/specs/prototypes/shared/layout-base.css#L962)

因此，**brand primitive scale 必须整体迁移**，否则 semantic 与 domain 会出现断链或风格撕裂。

### 5.2 关于 light mode 的确认

V1 的 light mode 也应收敛到同一条 `253°` 的 neutral spine，保持主题家族一致性。

只有极近白的 `surface-overlay` / `surface-modal` 可以继续保留近似 achromatic 写法，因为在该亮度区间 hue 几乎不可感知。

---

## 6. 使用纪律

### 6.1 面积纪律

- `brand-accent` 总视觉面积建议 `<= 3%`
- `brand-signature` 总视觉面积建议 `0.5% - 1.5%`
- 单页功能色家族建议 `<= 4`

### 6.2 Brass 允许出现的位置

- shell 顶部 / 侧边 1px marker
- 当前 workspace / context 标识
- onboarding / empty state / settings / export cover
- 分析带标题的低频身份点缀

### 6.3 Brass 禁止出现的位置

- Market 涨跌
- Risk 等级
- Execution 成功 / 失败
- System 健康 / 故障
- 高优先级 CTA 填充按钮

### 6.4 Brass 在 prototype 中的首批消耗面

V1 不追求大面积替换，只替换最能建立“身份层”的低频触点。

建议首批落点：

1. **Shell 顶部 hairline / marker**
   - 各页面 `.shell-header::after`
   - 当前这些位置大量由 `brand-accent` 承担身份感，适合切换为 `brand-signature-line`

2. **Header title 的非交互装饰线**
   - 例如 Home / Trading 的 `.header-title::after`
   - 它们属于品牌骨架，不属于操作反馈

3. **非语义型 empty state**
   - 仅限“空、待配置、即将推出、无内容”这类非状态性空态
   - 例如 Home 的 workspace placeholder、AI Overview / Research 的通用 empty card
   - 这些位置可将 `.state-empty-icon` 或其外圈边界换为 brass

4. **Workspace / style label / shell identity 文案**
   - 例如 Research 页的 style label、workspace 名称、非操作性 context 标识

V1 明确不改的 brand-accent 消耗面：

- active tab 下划线与 tab count
- `overlay-btn-primary` / `.btn-primary` / header CTA
- 图表主线、sparkline、研究强信号条
- 带有“当前选择 / 当前操作 / 当前进行中”含义的交互元素

也就是说：

> brass 先吃“身份层”，blue 继续留在“交互层”。

---

## 7. V1 定稿前的补充确认

### 7.1 surface-strip 的语义定义

当前提案中 `--surface-strip` (L=0.176) 低于 `--surface-panel-base` (L=0.182)。

明确定义：**strip 是 panel-base 的微回退变体**，用于工具条、分隔带等结构性区域，需要视觉上比面板内容区略暗以形成"凹陷"感。这不是 elevation 层级错误，而是有意设计。

### 7.2 brand-signature-subtle 的可见度

`oklch(0.760 0.055 74 / 0.08)` 在 L=0.155 背景上实际叠加效果约 L≈0.204。这是"只可意会"级别的底色。

- 如果用于需要被注意到的场景（empty state 卡片、onboarding 背景），alpha 应提到 `0.12-0.15`
- 如果用于"有它没它都行但有了更舒服"的场景（微妙的区域区分），`0.08` 可以保留
- 验证阶段需确认各使用场景对应哪个档位

### 7.3 text-tertiary 提升后的层级间距

提案将 text-tertiary 从 L=0.430 提到 L=0.555，secondary-tertiary 间距从 0.180 缩到 0.100。

在密集表格中，标签（secondary）和辅助信息（tertiary）的区分度会变弱。APCA 验证时需关注：

- 如果 tertiary 定在 L=0.555，secondary 是否需要同步提到 L=0.700+ 以维持间距
- 最终以 APCA Lc 差值作为裁决依据，而非亮度差值

### 7.4 domain bg 中间变量提取

Phase 1 同步处理 `tokens-domain.css` 中反复出现的 domain bg 值：

```css
/* 提取为中间变量 */
--domain-green-bg:    oklch(0.2280 0.0238 162 / 0.20);
--domain-amber-bg:    oklch(0.2229 0.0212 76.17 / 0.20);
--domain-orange-bg:   oklch(0.2165 0.0265 47.45 / 0.20);
--domain-red-bg:      oklch(0.2242 0.0365 8.74 / 0.25);
--domain-red-strong-bg: oklch(0.2242 0.0365 8.74 / 0.30);
```

各域 bg 改为引用中间变量，消除复制粘贴。

### 7.5 brass 与 blue 同画面共存

两者可能出现在同一视口（brass hairline 的 shell + blue focus ring / selected tab）。

需在验证阶段确认：

- brass L=0.760 C=0.055 与 blue L=0.715 C=0.145 在同一画面中不产生"黄蓝对冲"违和感
- 特别关注 brass marker 旁边的 selected-tab（blue）交界区域
- 在 C=0.055 (brass) 和 C=0.145 (blue) 的低饱和度下，此问题大概率不严重，但需视觉确认

---

## 8. 验证标准

V1 定稿前至少完成以下验证：

1. **APCA**
   - `text-primary / secondary / tertiary` 在 3 类深色 surface 上的 Lc
   - high-contrast 模式的增强幅度

2. **WCAG**
   - 正文文本 `>= 4.5:1`
   - 大字文本 `>= 3:1`
   - 颜色不作为唯一信息通道

3. **Dark Interface 连续性**
   - 常用任务流中无白底弹窗、亮 loading、浅色骨架闪烁

4. **品牌辨识度审查**
   - 截屏灰度化后，结构仍成立
   - 恢复颜色后，brass 能被明确感知为“身份层”而非“状态层”

---

## 9. 实施顺序建议

### Phase 1：基础色彩修复

- 更新 15 级 neutral primitive
- 更新 semantic surface / text / border 映射
- 改善 primitive 与 semantic 的引用链
- 建立 `--domain-{color}-bg` 中间变量，消除 tokens-domain.css 中的值重复

### Phase 2：品牌角色分离

- 保留蓝色为交互色
- 新增 brass token
- 替换 shell / context / empty state 等品牌触点

### Phase 3：舒适度增强

- 提供 `standard`
- 提供 `high-contrast`
- 建立验证矩阵

### Phase 4：V2 试点

- 在单模块试点微气候（优先 Research）

---

## 10. 最终判断

这次升级不是为了“更设计感”，而是为了完成一次更高层级的系统校准：

- 从“品牌蓝 + 深灰底”的常规高级 SaaS 方案
- 升级为“去蓝偏石墨骨架 + 交互蓝 + 黄铜身份层 + 7 域语义”的专业量化工作台方案

如果 V1 按上述边界执行，Ditto 的目标应从：

- `Premium Dark Tech`

稳定升级为：

- **Graphite Studio / Calibrated Intelligence**

这会是一个更有记忆点、也更耐用的方向。

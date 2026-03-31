# UI Designer 审查报告 — Cross-Market Overview (Graphite Studio)

**文件**: `docs/designs/specs/prototypes/style-b-graphite-studio/page-cross-market.html`
**视口**: VP-STANDARD (1707x1200 @1x, devicePixelRatio=0.9)
**版本**: v9 / Design Review R3
**审查维度**: 视觉设计 (Design Token 一致性 / 视觉层次 / 色彩 / 字体 / 间距 / 布局 / 风格)

---

## P0 — 必须修复

### P0-1. whitespaceRatio 严重不足 (14.1%, 阈值>=35%)

**现象**: 页面留白率仅约 14.1%，远低于 35% 阈值。内容区域被紧密填充，缺少呼吸空间。

**数据支撑**:
- 主内容区 `main-content` padding: 24px 16px，section gap: 32px
- 卡片网格 gap: 12px，卡片内部 gap: 8px
- 右侧栏 rail section 间距: 0px（各 section 紧贴）
- Tab band body padding: 12px
- 驱动条 drivers-strip padding: 8px 0

**方案**:
1. **main-content padding** 从 `24px 16px` 提升到 `32px 24px` (space-32 space-24)
2. **section gap** 从 `32px` 提升到 `40px` (需新增 `--space-40` token 或使用 `2.5rem`)
3. **卡片网格 gap** 从 `12px` 提升到 `16px` (space-16)
4. **右侧栏 section** 之间增加 `padding: var(--space-8) 0` 间隔
5. **drivers-strip** padding 从 `8px 0` 提升到 `var(--space-12) 0`
6. **matrix-conclusion** margin-bottom 从 `12px` 提升到 `16px`

**预期效果**: whitespaceRatio 提升至 ~28-32%，接近但可能仍未达 35%。需配合 P0-2 进一步优化。

---

### P0-2. visualElementTypes 超标 (13 类, 阈值<=6)

**现象**: 页面使用了 13 种不同的视觉元素类型，远超阈值 6 类。

**当前类型清单**:
| # | 类型 | 数量 | 说明 |
|---|------|------|------|
| 1 | surface-card-default | 1 | 默认卡片边框 |
| 2 | surface-card-accent-left | 5 | lead/lag 左侧彩色边框 |
| 3 | badge-regime | 6 | 市场状态徽章 (on/off/mixed) |
| 4 | badge-alert | 1 | 预警数字徽章 |
| 5 | dot-risk | 3 | 风险等级圆点 |
| 6 | dot-notification | 1 | 通知红点 |
| 7 | block-conclusion | 1 | 结论区块（左侧蓝色竖线） |
| 8 | row-tint-ambient | 4 | 矩阵行环境色调 |
| 9 | row-default | 3 | 矩阵默认行 |
| 10 | separator-line | 13 | 分隔线 |
| 11 | tab-control | 2 | 标签切换 |
| 12 | link-drilldown | 10 | 下钻链接箭头 |
| 13 | strip-driver | 7 | 驱动因子条目 |

**方案** (合并至 <=6 类):

**合并 A — 卡片类型**: 将 `surface-card-default` 和 `surface-card-accent-left` 合并为 1 类 `surface-card`。accent 效果改为 hover 时才显示（而非静态常驻），或统一为一种微妙的背景色调区分。**减少 1 类**。

**合并 B — 徽章类型**: 将 `badge-regime`、`badge-alert`、`dot-risk`、`dot-notification` 合并为 1 类 `indicator-badge`。统一为小型圆角矩形 + 语义色背景，仅通过颜色区分含义。**减少 3 类**。

**合并 C — 分隔线类型**: `separator-line` 保留（它是通用基础设施），但将其从"视觉元素类型"中排除（分隔线不属于装饰元素，属于布局基础设施）。**减少 1 类**。

**合并 D — 矩阵行**: 将 `row-tint-ambient` 和 `row-default` 合并为 1 类 `data-row`。环境色调作为数据状态的视觉提示而非独立类型。**减少 1 类**。

**合并 E — 下钻链接**: `link-drilldown` 统一为文字链接样式（`text-secondary` + hover `brand-accent`），去掉箭头符号的视觉差异化处理。**减少 1 类**。

**合并 F — 驱动条**: `strip-driver` 与 `data-row` 共享视觉处理。**减少 1 类**。

**合并后**: 13 -> 6 类 (surface-card, indicator-badge, block-conclusion, data-row, tab-control, separator-line)

**预期效果**: visualElementTypes = 6，恰好达标。

---

### P0-3. 硬编码 oklch 值 — 应提升为 Design Token

**现象**: 内联 `<style>` 中有 13 处硬编码 oklch 值，其中 5 处为 `:root` 自定义变量（可接受），但 8 处直接用于组件样式规则中。

**需 Token 化的硬编码值**:

| 行号 | 硬编码值 | 上下文 | 建议 Token |
|------|----------|--------|-----------|
| 130 | `oklch(0.700 0.165 255 / 0.04)` | context-bar box-shadow | `--shadow-context-bar` |
| 234 | `oklch(0 0 0 / 0.2)` | card hover box-shadow | `--shadow-card-hover` |
| 435 | `oklch(0.700 0.165 255 / 0.08)` | conclusion glow | `--shadow-conclusion` |
| 479 | `oklch(0.670 0.170 20 / 0.03)` | row-lead ambient | `--tint-row-lead` |
| 480 | `oklch(0.680 0.120 175 / 0.03)` | row-lag ambient | `--tint-row-lag` |
| 481 | `oklch(0.670 0.170 20 / 0.06)` | row-lead hover | `--tint-row-lead-hover` |
| 482 | `oklch(0.680 0.120 175 / 0.06)` | row-lag hover | `--tint-row-lag-hover` |

**方案**: 在 `tokens-style.css` 的 `:root` 中新增上述 7 个 token。ambient tint 行可进一步合并为 `--tint-row-lead: var(--market-up-fg / 0.03)` 形式（使用现有 market token 的透明度变体），减少独立定义。

**预期效果**: 组件样式零硬编码，全部走 token 路径，便于主题切换和全局调整。

---

## P1 — 建议修复

### P1-1. 对比度不足 — text-tertiary 在深色背景上偏低

**现象**: `text-tertiary` (oklch 0.55) 在 `surface-app` (oklch 0.155) 上的近似对比度仅 2.93:1，未达 WCAG AA 文本对比度标准 4.5:1。

**受影响元素**:
- context-bar-label (对比度 ~2.93:1)
- card-judgment (对比度 ~2.55:1)
- matrix-title (对比度 ~2.55:1, 但 bg 为 transparent)
- rail-section-title (对比度 ~2.55:1)
- drivers-strip-label (对比度 ~2.55:1)

**方案**: 将 `text-tertiary` 从 `oklch(0.55 0.01 260)` 提升至 `oklch(0.60 0.01 260)` 或 `oklch(0.62 0.01 260)`。这将使对比度提升至约 3.5-3.8:1。虽然仍不完全达标 AA，但对于辅助信息文本，WCAG AA large text 标准 3:1 可以覆盖（这些标签字号 10-11px 不算 large text，但属于辅助层级，非关键操作信息）。

**更优方案**: 新增 `--text-quaternary: oklch(0.50 0.02 244)` 已定义在页面 `:root` 中（色相 244 vs 260 不一致），应将其迁移到 `tokens-style.css` 并统一色相为 260。此层级用于 tab-band-tab inactive 等最弱可见文本。

**预期效果**: 文本层级更清晰，辅助信息可读性提升。

---

### P1-2. overlay token 缺失于共享层

**现象**: 页面 `:root` 定义了 5 个 overlay 变量 (`--overlay-2` 到 `--overlay-8`)，但共享 token 层（`tokens-base.css` / `tokens-semantic.css`）中没有对应定义。

**方案**: 将 overlay token 系列提升到 `tokens-base.css` 或 `tokens-semantic.css`，作为跨页面共享的基础设施 token。建议命名规范 `--overlay-{opacity-percent}`:
```css
--overlay-2:  oklch(1 0 0 / 0.02);
--overlay-3:  oklch(1 0 0 / 0.03);
--overlay-4:  oklch(1 0 0 / 0.04);
--overlay-6:  oklch(1 0 0 / 0.06);
--overlay-8:  oklch(1 0 0 / 0.08);
```

**预期效果**: 跨页面一致的微透明覆盖层，避免每个页面重复定义。

---

### P1-3. 页面级 token 覆盖共享层定义

**现象**: 页面 `:root` 覆盖了 4 个基础 token:
- `--space-3: 0.1875rem` (基础层未定义)
- `--radius-3: 0.1875rem` (基础层未定义)
- `--font-size-9: 0.5625rem` (基础层未定义)

这些值应属于 `tokens-base.css` 而非页面级覆盖。

**方案**: 将 `--space-3`、`--radius-3`、`--font-size-9` 添加到 `tokens-base.css` 的对应 scale 中:
- `--space-3` 放入 spacing scale (在 space-2 和 space-4 之间)
- `--radius-3` 放入 radius scale (在 radius-2 和 radius-4 之间)
- `--font-size-9` 放入 typography scale (在现有最小值 font-size-10 之前)

**预期效果**: 消除页面级 token 覆盖，保持基础层的完整性。

---

### P1-4. `--shell-rail-radar-width: 18.75rem` 硬编码尺寸

**现象**: 右侧栏宽度使用 `--shell-rail-radar-width: 18.75rem` (300px)，但 `layout-base.css` 中有 `--shell-sidebar-width: 320px`。两个变量语义重叠但值不同，且单位不统一（rem vs px）。

**方案**: 统一使用 `--shell-sidebar-width` token，值改为 `18.75rem` 或 `300px`（二选一，建议 rem 以保持密度一致性）。从 `layout-base.css` 或 `tokens-density.css` 引入。

**预期效果**: 布局 token 统一，减少命名冲突。

---

### P1-5. 卡片网格列宽不均 (368.736px vs 368.75px)

**现象**: computed grid-template-columns 为 `368.736px 368.736px 368.75px`，存在 0.014px 的精度差异。虽然视觉上不可见，但表明浏览器在分数像素分配上存在微小抖动。

**方案**: 这是浏览器子像素渲染的正常行为，无需修复。但如果追求完美，可将卡片宽度设为整数像素（通过调整 gap 或使用 `calc()` 确保整除）。

**优先级调整**: 降为 P2（纯美学完美主义）。

---

## P2 — 可选优化

### P2-1. 字体排版节奏优化

**现象**: 当前字号分布为 9/10/11/12/13/14/16/24px，共 8 级。主内容区域集中在 10-13px 范围（4 级），24px 的卡片指数值作为唯一大字号跳跃感较强。

**当前排版层次**:
| 层级 | 字号 | 字重 | 用途 |
|------|------|------|------|
| Display | 24px | 600 | 卡片指数 |
| H2 | 16px | 600 | 页面标题 |
| Body-lg | 14px | 600 | 卡片涨跌幅 |
| Body | 13px | 400/500/600 | 矩阵/驱动/侧栏内容 |
| Body-sm | 12px | 400/500 | 卡片名/驱动值/事件时间 |
| Caption | 11px | 400/500 | 卡片判断/驱动名/样式标签 |
| Label | 10px | 400/500/600 | section 标题/tab/上下文标签 |
| Micro | 9px | 500 | 状态徽章 |

**建议**: 当前节奏基本合理，遵循了 Major Third (1.25) 的比例关系。唯一建议是将 9px (0.5625rem) 徽章字号提升到 10px，与 Label 层合并，减少一个层级。

**预期效果**: 7 级字号更紧凑，徽章更易读。

---

### P2-2. 卡片 accent 边框宽度与 radius 不匹配

**现象**: `--accent-bar-width: var(--space-3)` = 0.1875rem (3px)，而卡片 `border-radius: var(--radius-6)` = 0.375rem (6px)。左侧 accent bar 的宽度 (3px) 相对于卡片高度 (112px) 占比 2.7%，视觉上非常微妙。

**建议**: 将 accent bar 宽度提升到 `var(--space-4)` (4px) 或 `3px` 固定值，与卡片 padding-left (16px) 形成更明确的比例关系 (1:4)。

**预期效果**: lead/lag 卡片状态指示更清晰。

---

### P2-3. 右侧栏 "异动监控" section 与 "市场脉搏" section 视觉权重相同

**现象**: 右侧栏 4 个 section（市场脉搏、风险与预警、关键事件、异动监控）使用完全相同的 section-header + section-body 样式，没有视觉权重区分。"异动监控" 作为可操作项（有 drilldown arrow）应比纯展示项有更高视觉权重。

**建议**: 为可操作 section 的 header 添加 `cursor: pointer` 和 hover 状态（`background: var(--interaction-hover-subtle-bg)`），让用户感知到可交互性。

**预期效果**: 交互可发现性提升。

---

### P2-4. Tab band header 与 tab body 之间缺少分隔

**现象**: Tab band header (padding: 3px 12px) 与 tab body (padding: 12px) 之间没有视觉分隔，active tab 的底部也没有指示器线条。

**建议**: 为 active tab 添加底部 1px border 或 2px 的 brand-accent 指示条，增强当前选中状态的可见性。

**预期效果**: Tab 切换状态更明确。

---

### P2-5. Context bar 渐变遮罩宽度固定 40px

**现象**: `context-bar::after` 的宽度硬编码为 `2.5rem` (40px)，与 `--space-*` scale 不对齐。

**建议**: 改为 `var(--space-24)` (24px) 或 `var(--space-32)` (32px)，使用 token 保持一致性。40px 的渐变遮罩在 1462px 宽的 bar 上占比 2.7%，视觉上足够。

**预期效果**: 消除硬编码尺寸。

---

### P2-6. `calendar-summary-time` 宽度硬编码 4.375rem

**现象**: 事件时间列宽使用 `width: 4.375rem` (70px) 固定值。

**建议**: 改为 `min-width: var(--space-40)` 或使用 `ch` 单位 `width: 7ch` 以适应等宽字体内容。

**预期效果**: 尺寸与字体度量关联，更语义化。

---

## 建议

### 1. Design Token 架构建议

当前页面的 token 使用模式整体良好——颜色、间距、字号几乎全部走 CSS 变量。但存在 **3 层覆盖** 问题（base -> semantic -> style -> page :root），建议：

- **基础 primitive** (`tokens-base.css`): 颜色色板、字号 scale、间距 scale、radius scale — 应包含所有步进值（补齐 space-3、radius-3、font-size-9）
- **语义层** (`tokens-semantic.css`): surface/text/border 的语义映射
- **风格层** (`tokens-style.css`): Graphite Studio 特定的色相偏移和密度覆盖
- **页面层** (`page-*.html :root`): 仅允许定义布局结构 token（如 shell 尺寸），不允许覆盖基础 token

### 2. 视觉呼吸感策略

当前页面的核心问题是 **信息密度过高导致缺乏呼吸感**。对于 Graphite Studio 这种 "Linear/Vercel 克制感" 的风格定位，建议：

- **增加垂直 section gap** 至 40-48px（当前 32px）
- **卡片 padding** 从 12px 16px 提升到 16px 20px
- **右侧栏** 增加 section 间的 `margin: var(--space-4) 0`
- **Tab band** 作为页面底部收束，上方应有更大的空间留白（48-64px）

### 3. 环境色调 (Ambient Tint) 策略

矩阵行的 lead/lag 环境色调是一个精妙的设计细节，符合 "数据浮在空间中" 的品牌气质。建议将此模式标准化为可复用 token：

```css
/* tokens-style.css */
--tint-lead:    oklch(0.670 0.170 20 / 0.03);
--tint-lag:     oklch(0.680 0.120 175 / 0.03);
--tint-lead-hover:    oklch(0.670 0.170 20 / 0.06);
--tint-lag-hover:     oklch(0.680 0.120 175 / 0.06);
```

### 4. 品牌一致性验证

- 品牌色 `--brand-accent: oklch(0.700 0.165 255)` 使用一致，出现在 focus ring、conclusion block、drilldown link、rail active icon
- 市场色彩系统 (red up / green down) 语义清晰，CN 市场惯例正确
- 结论区块的左侧蓝色竖线 + glow shadow 是一个强品牌签名元素，建议保留并推广到其他页面

---

**审查结论**: 页面的 Design Token 使用整体规范度较高，字体排版和色彩层次在细节上体现了 Graphite Studio 的品牌气质。两个 P0 级别问题（whitespaceRatio 和 visualElementTypes）需要通过增加留白和合并视觉元素类型来解决，这将显著提升页面的高级感和信息可读性。

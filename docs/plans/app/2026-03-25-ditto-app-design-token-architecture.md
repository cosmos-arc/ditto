# Ditto Design Token 架构设计

> 基于 [产品设计方案](../research/2026-03-24-ditto-app-product-design.md) 和 [技术选型清单](../research/2026-03-24-ditto-app-techstack.md)，为 Ditto 量化交易平台前端定义 Design Token 体系。
> 状态：设计中（迭代中）
> 决策日期：2026-03-25

---

## 1. 架构总览

### 1.1 规范引用

> DTCG 2025.10 稳定版定义的是 token 的**交换格式**（JSON `$value`/`$type`）和 **resolver 机制**（多上下文解析），**不强制**团队采用三层命名架构。三层（Primitive → Semantic → Component）是业界常见实践，Ditto 选择两层起步是基于 Tailwind v4 + shadcn/ui + AG Grid + 量化产品场景做出的**工程化折中**。

### 1.2 两层起步 + 升级触发条件

当前：**Primitive + Semantic 两层**。Component Token 暂由 shadcn CVA 变体承担。

**引入第三层的触发条件**（任一即触发）：
- 同一语义在不同组件里**长期需要不同表达**（如"危险态"在 Button / Table / Card 上视觉要求不同）
- 同类组件形成**稳定尺寸/密度/状态谱系**
- 设计评审反复出现"按钮危险态 ≠ 表格危险态 ≠ 卡片危险态"
- 启动白标 / 租户化 / 品牌主题需求

### 1.3 层间职责边界

```
Primitive（去业务化）          Semantic（带业务语义）
─────────────────          ─────────────────────────
oklch(0.65 0.2 145)   →    --color-market-up
oklch(0.55 0.22 25)   →    --color-market-down
0.5rem                 →    --color-surface-panel
0.625rem               →    --color-text-primary
0.375rem               →    --color-border-subtle
Inter / JetBrains Mono →    --font-sans / --font-mono
150ms                  →    --motion-fast
```

**Primitive 层只存**：色板色阶、灰阶、间距、圆角、阴影、字体族、z-index、动画时长/缓动函数。
**Semantic 层才表达**：市场语义、风险语义、系统状态、UI 上下文（surface / text / border）。

### 1.4 市场色 vs 系统状态色：严格分离

量化产品的**关键边界**，禁止混用：

| 域 | 语义 | Token 示例 | 消费场景 |
|---|------|-----------|---------|
| **市场** | 涨/跌/平 | `--color-market-up` / `--color-market-down` / `--color-market-flat` | K 线、盈亏、涨跌幅、收益热力图 |
| **风险** | 低/中/高/临界 | `--color-risk-low` / `--color-risk-medium` / `--color-risk-high` / `--color-risk-critical` | 风控仪表盘、暴露度、回撤区间 |
| **系统** | 成功/警告/错误/处理中 | `--color-status-success` / `--color-status-warning` / `--color-status-error` / `--color-status-pending` | Toast、表单校验、订单状态、后台任务 |
| **信号** | 买入/卖出/持有 | `--color-signal-buy` / `--color-signal-sell` / `--color-signal-hold` | 策略信号、因子有效性 |

**禁止**：系统 `error` 直接复用市场 `down`，否则下单失败、回测报错、市场下跌全挤在同一个红色家族里。

### 1.5 文件结构

```
apps/web/src/styles/
  globals.css                 # 入口：@import tokens + @theme inline
  tokens/
    primitives.css            # Layer 1：色板、灰阶、间距、圆角、阴影
    semantic-core.css         # Layer 2：surface / text / border / ring
    semantic-market.css       # Layer 2：涨跌、信号
    semantic-risk.css         # Layer 2：风险等级
    semantic-status.css       # Layer 2：系统状态（成功/警告/错误）
    charts.css                # Layer 2：图表色板（基础 UI / 市场序列 / 策略序列）
    grid.css                  # Layer 2：AG Grid 桥接 + 密度策略
    typography.css            # Layer 2：字体族、字号阶梯、tabular-nums
    motion.css                # Layer 2：动画时长、缓动函数、闪烁策略
```

### 1.6 @theme 注册边界

| 放入 `@theme inline`（生成 utility） | 留在 `:root` / `.dark`（不生成 utility） |
|---|---|
| surface / text / border / ring 系列 | K 线涨跌渐变、深度图透明度 |
| market-up / market-down / flat | 图表坐标轴、网格线、十字光标色 |
| risk-* / status-* / signal-* 系列 | AG Grid 局部覆盖变量 |
| spacing / radius / font-family | motion token（通过 CSS 变量直接引用） |
| chart-1 ~ chart-8 基础色板 | 图表策略序列色（基准、超额、信号标记等） |

### 1.7 暗色优先 + 浅色一等公民

- 暗色为默认主题（量化用户长时盯盘场景）
- 浅色不是补丁：Primitive 定义中性原始值，Semantic 按 `:root` 和 `.dark` **分别完整映射**
- 组件只消费 Semantic，不直接引用 Primitive

### 1.8 色彩空间

- 采用 **OKLCH** 作为内部色彩主表示
- shadcn/ui v4 默认 OKLCH，Tailwind v4 原生支持
- 感知均匀的亮度通道，暗色面板/边框/hover/muted 层次控制更稳

---

## 2. Primitive 色板

### 2.1 结构原则

- **彩色 Primitive**：red / green / amber / blue / violet / purple，各 6 级（50-500）
- **中性 Primitive**：单独 12 级完整灰阶 ramp，不复用彩色体系的 Neutral 6 级
- **图表系列色**：独立于 UI 色板，不硬复用同一组 primitive ramp（需补 cyan/teal/rose 提升序列区分度）
- **彩色 C 值不机械同构**：Amber/Green 在暗色底需压低 chroma 防止"发飘""荧光感"
- **灰阶非线性**：低亮度区域更密（暗色面板层次），高亮度区域更疏，不强求全局等比

### 2.2 彩色色阶（6 级 × 6 色相）

```
              50           100          200          300          400          500
              最浅          浅           中浅          中           中深          深
Red       0.97 0.02 25  0.92 0.06 25  0.85 0.12 25  0.75 0.18 25  0.65 0.22 25  0.55 0.24 25
Green     0.97 0.02 155 0.92 0.05 155 0.85 0.10 155 0.78 0.13 155 0.70 0.16 155 0.60 0.17 155
Amber     0.98 0.02 85  0.94 0.05 85  0.88 0.08 85  0.82 0.12 85  0.75 0.13 85  0.65 0.13 85
Blue      0.97 0.01 260 0.93 0.04 260 0.86 0.08 260 0.75 0.14 260 0.62 0.19 260 0.50 0.21 260
Violet    0.97 0.01 295 0.93 0.04 295 0.86 0.08 295 0.75 0.14 295 0.62 0.19 295 0.50 0.21 295
Purple    0.97 0.01 320 0.92 0.05 320 0.84 0.09 320 0.72 0.14 320 0.58 0.18 320 0.48 0.18 320
```

> 格式：`oklch(L C hue)`。C 值按 hue 特性差异化，Amber/Green 压低 chroma。

### 2.3 中性灰阶（12 级）

```
Level   L 值      用途直觉
──────────────────────────────────────
0       0.985    几乎纯白（浅色背景）
1       0.955    浅灰面板
2       0.900    subtle border、分割线
3       0.800    浅色 muted 文字
4       0.700    次要文字、placeholder
5       0.600    中灰
6       0.500    中深灰
7       0.400
8       0.300    深色 muted 文字
9       0.220    暗色卡片 surface
10      0.180    暗色面板 surface
11      0.140    暗色 app background
```

> 低亮度区域（L 0.14-0.30）间隔更密，服务于暗色面板的表面层次区分。

### 2.4 图表系列色（独立色板，非 UI ramp）

图表需要"相邻曲线一眼分开"，色相分布与 UI 色板不同，补入 cyan/teal/rose。完整定义见 [10.4 通用多曲线色板](#104-通用多曲线色板8-色)。

### 2.5 扩展路径

- v1：6 级彩色 + 12 级灰阶 + 8 色图表系列，满足一期需求
- v1.x：若选中态/pressed 态/热力图/分层 badge 增多，给彩色加 600 深档即可
- 不建议一期扩到 950 级：量化平台大量消耗层级的是 surface/border/text/muted，非彩色 ramp

---

## 3. Semantic Core — Surface / Text / Border

### 3.1 Surface 层级

量化暗色面板系统需要 3-4 级表面层次，浅色依赖 border/shadow/radius 拉开而非色差。

**暗色主题**：

```
Token                        值                     用途
──────────────────────────────────────────────────────────────────
--color-surface-app          oklch(0.140 0 0)       应用级背景
--color-surface-panel        oklch(0.180 0 0)       面板/卡片背景
--color-surface-elevated     oklch(0.220 0 0)       弹窗/下拉/浮层
--color-surface-hover        oklch(1 0 0 / 6%)      行悬停、按钮悬停
--color-surface-selected     oklch(1 0 0 / 10%)     表格行选中、导航 active、tab 选中
--color-surface-pressed      oklch(1 0 0 / 15%)     按下态（可选）
```

**浅色主题**：

```
Token                        值                     用途
──────────────────────────────────────────────────────────────────
--color-surface-app          oklch(0.985 0 0)       应用级背景
--color-surface-panel        oklch(1 0 0)           面板/卡片（纯白）
--color-surface-elevated     oklch(1 0 0)           弹窗/下拉（纯白 + shadow）
--color-surface-hover        oklch(0 0 0 / 4%)      行悬停
--color-surface-selected     oklch(0 0 0 / 7%)      选中态
--color-surface-pressed      oklch(0 0 0 / 10%)     按下态
```

> 浅色下 surface-panel 和 surface-elevated 均为纯白，层次由 border/shadow/radius 承载（与 shadcn 默认主题一致）。

### 3.2 Text 层级

```
Token                        Dark              Light              用途
──────────────────────────────────────────────────────────────────────────────
--color-text-primary         L0.985            L0.145             正文、标题、表头
--color-text-secondary       L0.700            L0.400             辅助说明、时间戳、次标
--color-text-muted           L0.450            L0.600             ⚠️ 仅限 incidental：placeholder、
                                                               图例次标、分隔性元信息、disabled 旁弱提示
                                                               不适合承载需要阅读的正文/标签
```

> text-muted 对比度不满足 WCAG AA 4.5:1（dark ~2.7:1, light ~3.8:1），仅用于非关键装饰性文本。
> 若未来需要可读的第三档，引入 `--color-text-tertiary`（dark L0.550, light L0.500）。

### 3.3 Border / Ring

```
Token                        Dark               Light              用途
──────────────────────────────────────────────────────────────────────────────
--color-border-subtle        oklch(1 0 0 / 7%)  oklch(0 0 0 / 7%)  装饰性分隔线
--color-border-default       oklch(1 0 0 / 12%) oklch(0 0 0 / 12%) 一般容器边界
--color-border-strong        oklch(1 0 0 / 20%) oklch(0 0 0 / 20%) 关键分组/高密度表格
--color-border-input         oklch(1 0 0 / 18%) oklch(0 0 0 / 18%) 输入框边框（独立定义）
--color-ring-focus           oklch(0.60 0.15 260) oklch(0.50 0.18 260) 焦点环
```

**工程约束**：
- subtle/default/strong alpha border 为**装饰性**，不单独承担关键控件的可识别性（不满足 WCAG 3:1 非文本边界要求）
- 关键控件必须由 input border + focus ring + 背景变化或阴影**共同表达**
- ring-focus 独立存在，不复用 border

### 3.4 shadcn/ui 完整桥接表

Ditto 保留 shadcn 原生 token 名，底层映射到 Ditto semantic token：

```
shadcn 原生 token               Ditto 映射
──────────────────────────────────────────────────────────────────
--background              ←    --color-surface-app
--foreground              ←    --color-text-primary
--card                    ←    --color-surface-panel
--card-foreground         ←    --color-text-primary
--popover                 ←    --color-surface-elevated
--popover-foreground      ←    --color-text-primary
--primary                 ←    --color-accent-primary（品牌/主操作色）
--primary-foreground      ←    --color-text-on-accent
--secondary               ←    --color-surface-hover
--secondary-foreground    ←    --color-text-primary
--muted                   ←    --color-surface-hover（或独立 muted-surface）
--muted-foreground        ←    --color-text-secondary
--accent                  ←    --color-surface-selected
--accent-foreground       ←    --color-text-primary
--destructive             ←    --color-status-error
--destructive-foreground  ←    --color-text-on-status-error
--border                  ←    --color-border-default
--input                   ←    --color-border-input
--ring                    ←    --color-ring-focus
--chart-1 ~ --chart-5     ←    图表系列色 chart-1 ~ chart-5
--sidebar-background      ←    --color-surface-panel（sidebar 复用 panel）
--sidebar-foreground      ←    --color-text-primary
--sidebar-primary         ←    --color-accent-primary
--sidebar-primary-foreground ←  --color-text-on-accent
--sidebar-accent          ←    --color-surface-selected
--sidebar-accent-foreground ←  --color-text-primary
--sidebar-border          ←    --color-border-default
--sidebar-ring            ←    --color-ring-focus
```

> 组件继续使用 `bg-background`、`text-foreground` 等 shadcn 工具类，保持生态兼容。

---

## 4. Semantic Market — 涨跌 / 信号

### 4.1 消费位规范

每个语义域的 token 按 **fg（前景文字） / bg（背景染色） / stroke（边框/描边）** 三类拆分，
落地为可直接消费的单值 CSS 变量，不留口头规则。

### 4.2 A 股涨跌色

A 股文化中红=涨（吉祥）、绿=跌。token 用 `market-up` / `market-down` 语义名，不用 red / green：

```
Token                          Dark                      Light                     用途
──────────────────────────────────────────────────────────────────────────────────────
--color-market-up-fg           oklch(0.68 0.22 25)       oklch(0.60 0.22 25)       涨幅数字、盈亏文字
--color-market-up-bg           oklch(0.68 0.22 25 / 12%) oklch(0.60 0.22 25 / 8%)  行/单元格底色
--color-market-up-stroke       oklch(0.68 0.22 25 / 30%) oklch(0.60 0.22 25 / 25%) badge 边框、微型图描边

--color-market-down-fg         oklch(0.72 0.17 155)      oklch(0.60 0.17 155)      跌幅数字
--color-market-down-bg         oklch(0.72 0.17 155 / 12%)oklch(0.60 0.17 155 / 8%) 行/单元格底色
--color-market-down-stroke     oklch(0.72 0.17 155 / 30%)oklch(0.60 0.17 155 / 25%) badge 边框

--color-market-flat-fg         oklch(0.60 0.01 0)        oklch(0.50 0.01 0)        平盘数字
--color-market-flat-bg         oklch(1 0 0 / 5%)         oklch(0 0 0 / 4%)         平盘底色
--color-market-flat-stroke     oklch(1 0 0 / 12%)        oklch(0 0 0 / 10%)        平盘描边
```

> bg/stroke 使用 OKLCH + alpha 合成，直接产出可消费值。Dark 下 Green C 值 0.17 防荧光感。

### 4.3 信号色（策略信号 / 因子方向）

信号色**迁出红绿家族**，使用 blue/violet/gray，与市场涨跌彻底脱钩。
研究页、交易页、监控页并屏时，"策略动作"和"市场结果"视觉上一眼可分：

```
Token                          Dark                      Light                     用途
──────────────────────────────────────────────────────────────────────────────────────
--color-signal-buy-fg          oklch(0.68 0.16 260)      oklch(0.50 0.18 260)      买入信号文字
--color-signal-buy-bg          oklch(0.68 0.16 260 / 12%)oklch(0.50 0.18 260 / 8%) 买入行底色
--color-signal-buy-stroke      oklch(0.68 0.16 260 / 30%)oklch(0.50 0.18 260 / 25%) 买入 badge 描边

--color-signal-sell-fg         oklch(0.65 0.18 310)      oklch(0.48 0.20 310)      卖出信号文字
--color-signal-sell-bg         oklch(0.65 0.18 310 / 12%)oklch(0.48 0.20 310 / 8%) 卖出行底色
--color-signal-sell-stroke     oklch(0.65 0.18 310 / 30%)oklch(0.48 0.20 310 / 25%) 卖出 badge 描边

--color-signal-hold-fg         oklch(0.60 0.01 0)        oklch(0.50 0.01 0)        持有信号
--color-signal-hold-bg         oklch(1 0 0 / 5%)         oklch(0 0 0 / 4%)         持有底色
--color-signal-hold-stroke     oklch(1 0 0 / 12%)        oklch(0 0 0 / 10%)        持有描边
```

> buy=blue, sell=violet, hold=gray。WCAG 要求颜色不是唯一信息通道，信号必须配合图标/文案。

---

## 5. Semantic Risk — 风险等级

风险域按**等级递进**设计，不与 status 共用色相。低风险≠成功，高风险≠错误：

```
Token                          Dark                      Light                     等级
──────────────────────────────────────────────────────────────────────────────────────
--color-risk-low-fg            oklch(0.65 0.12 195)      oklch(0.50 0.14 195)      低（teal）
--color-risk-low-bg            oklch(0.65 0.12 195 / 12%)oklch(0.50 0.14 195 / 8%) 底色
--color-risk-low-stroke        oklch(0.65 0.12 195 / 30%)oklch(0.50 0.14 195 / 25%)描边

--color-risk-medium-fg         oklch(0.75 0.13 85)       oklch(0.60 0.13 85)       中（amber）
--color-risk-medium-bg         oklch(0.75 0.13 85 / 12%) oklch(0.60 0.13 85 / 8%)  底色
--color-risk-medium-stroke     oklch(0.75 0.13 85 / 30%) oklch(0.60 0.13 85 / 25%) 描边

--color-risk-high-fg           oklch(0.72 0.16 55)       oklch(0.58 0.18 55)       高（orange）
--color-risk-high-bg           oklch(0.72 0.16 55 / 12%) oklch(0.58 0.18 55 / 8%)  底色
--color-risk-high-stroke       oklch(0.72 0.16 55 / 30%) oklch(0.58 0.18 55 / 25%) 描边

--color-risk-critical-fg       oklch(0.68 0.22 25)       oklch(0.55 0.22 25)       临界（red）
--color-risk-critical-bg       oklch(0.68 0.22 25 / 12%) oklch(0.55 0.22 25 / 8%)  底色
--color-risk-critical-stroke   oklch(0.68 0.22 25 / 30%) oklch(0.55 0.22 25 / 25%) 描边
```

> 等级梯度：teal → amber → orange → red，色相间距 > 40°，相邻等级不会混淆。
> critical 独立于 status-error（虽然同 hue 但不同 token 名，语义不混用）。

---

## 6. Semantic Status — 系统状态

保持通用产品语义，接受与 market/risk 共享部分色相家族，
靠组件上下文、图标、文案、容器样式区分，不追求纯色相去重：

```
Token                          Dark                      Light                     用途
──────────────────────────────────────────────────────────────────────────────────────
--color-status-success-fg      oklch(0.65 0.15 155)      oklch(0.50 0.15 155)      操作成功
--color-status-success-bg      oklch(0.65 0.15 155 / 12%)oklch(0.50 0.15 155 / 8%) toast/badge 底色
--color-status-success-stroke  oklch(0.65 0.15 155 / 30%)oklch(0.50 0.15 155 / 25%) 描边

--color-status-warning-fg      oklch(0.75 0.13 85)       oklch(0.60 0.13 85)       注意
--color-status-warning-bg      oklch(0.75 0.13 85 / 12%) oklch(0.60 0.13 85 / 8%)  底色
--color-status-warning-stroke  oklch(0.75 0.13 85 / 30%) oklch(0.60 0.13 85 / 25%) 描边

--color-status-error-fg        oklch(0.68 0.20 25)       oklch(0.55 0.20 25)       错误
--color-status-error-bg        oklch(0.68 0.20 25 / 12%) oklch(0.55 0.20 25 / 8%)  底色
--color-status-error-stroke    oklch(0.68 0.20 25 / 30%) oklch(0.55 0.20 25 / 25%) 描边

--color-status-pending-fg      oklch(0.65 0.12 260)      oklch(0.50 0.14 260)      处理中
--color-status-pending-bg      oklch(0.65 0.12 260 / 12%)oklch(0.50 0.14 260 / 8%) 底色
--color-status-pending-stroke  oklch(0.65 0.12 260 / 30%)oklch(0.50 0.14 260 / 25%) 描边
```

> status 用于 Toast、表单校验、订单状态、后台任务。与 market/risk 的视觉区分由组件上下文 + 图标 + 文案保证。

---

## 8. Typography — 字体体系

### 8.1 字体选择

| 角色 | 字体 | 理由 |
|------|------|------|
| UI 文字 | **Inter** | 屏幕专用，9 种字重，x-height 适中，内置 tabular-nums OpenType 特性 |
| 技术型字段 | **JetBrains Mono** | 等宽、0O/1lI 可区分，用于订单号、日志、ticker、终端式字段 |

> Inter 和 JetBrains Mono 均为 SIL OFL 免费开源字体。

### 8.2 数字策略（两层）

**默认数字样式**：Inter + `tabular-nums` + `lining-nums`
- 适用：表格数值、KPI 卡片、图表轴刻度、收益率、价格、持仓量
- 效果：数字等宽对齐，但保持 sans-serif 的紧凑与舒适
- 实现：Tailwind utility `font-sans tabular-nums`

**技术型字段**：JetBrains Mono
- 适用：订单号、成交 ID、日志输出、原始 ticker、代码片段
- 效果：字符辨识优先于阅读舒适
- 实现：Tailwind utility `font-mono`

> **不要把"所有数值"默认切到 mono**。大部分研究页、看板页、回测页应保持 sans + tabular-nums 的专业金融产品观感，而非 IDE 观感。

### 8.3 字号阶梯

```
Token                          值                  Tailwind 映射       用途
──────────────────────────────────────────────────────────────────────────
--font-size-page-title         20px (1.25rem)      text-xl             页面标题
--font-size-section-header     14px (0.875rem)     text-sm semibold     面板标题、区块头
--font-size-body-default       14px (0.875rem)     text-sm             正文默认（设置页、对话框、帮助）
--font-size-body-compact       13px (0.8125rem)    text-[13px]         紧凑正文（交易台、列表、持仓、监控）
--font-size-label              12px (0.75rem)      text-xs             标签、表头、轴刻度
--font-size-caption            11px (0.6875rem)    text-[11px]         次标、图例、脚注
--font-size-kpi                28px (1.75rem)      text-[28px]         大数字展示（Dashboard KPI）
```

> body 分两层：default 14px 用于非核心阅读区域，compact 13px 用于高密度专业页面。
> 表格单行密集行用 1.25 行高；双行或中英混排单元格用 1.3–1.4。

### 8.4 行高 / 字重

```
Token                          值           用途
──────────────────────────────────────────────────────
--line-height-tight            1.25         密集表格单行
--line-height-default          1.40         正文默认
--line-height-relaxed          1.60         表单说明、帮助文本
--font-weight-default          400          正文
--font-weight-medium           500          表头、标签强调
--font-weight-semibold         600          区块标题
--font-weight-bold             700          KPI 数字、页面标题
```

### 8.5 Tailwind 注册

```css
@theme inline {
  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "Cascadia Code", monospace;
}
```

---

## 9. Motion — 动效体系

### 9.1 设计原则

> 量化/监控产品里动画不是为了炫，而是为了"提醒变化但不惊扰"。

**允许**：状态切换过渡（hover/focus/selected/展开收起）、Toast 出入、面板展开收起、图表加载渐显。

**禁止**：数字滚动/计数动画、价格跳动动画、骨架屏 shimmer、大面积脉冲/呼吸效果。

### 9.2 时长 / 缓动函数

```
Token                          值                              用途
──────────────────────────────────────────────────────────────────────
--duration-fast                100ms                           hover、focus、微交互
--duration-normal              200ms                           面板展开、tab 切换
--duration-slow                350ms                           页面转场、大型面板动画

--ease-standard                cubic-bezier(0.4, 0, 0.2, 1)    标准过渡
--ease-emphasized              cubic-bezier(0.2, 0, 0, 1)      强调进场
--ease-decelerate              cubic-bezier(0, 0, 0.2, 1)      减速退出
```

### 9.3 实时数据闪烁策略

```
Token                          值                              行为
──────────────────────────────────────────────────────────────────────
--motion-flash-duration        300ms                           闪烁持续时间
--motion-flash-up-color        var(--color-market-up-bg)        涨时闪烁色
--motion-flash-down-color      var(--color-market-down-bg)      跌时闪烁色
--motion-flash-enabled         1                               允许闪烁（默认）
```

**规则**：
- 闪烁 = 短暂背景色高亮（300ms），不做数字变形/缩放/位移
- 用户可通过 `--motion-flash-enabled: 0` 全局关闭
- WebSocket 推送频率 > 10/s 时自动降级为"仅更新值、不闪烁"
- **单点闪烁不超过 3 次/秒**（WCAG 安全线）
- **爆发式更新合并到一帧**：同一单元格的多条 tick 合并为一次闪烁，不逐条触发

### 9.4 Reduced Motion（token 级关停）

```css
@media (prefers-reduced-motion: reduce) {
  :root {
    --duration-fast: 0ms;
    --duration-normal: 0ms;
    --duration-slow: 0ms;
    --motion-flash-enabled: 0;
  }
}
```

> 不使用全局 `* { animation-duration: 0.01ms !important }` 硬清空。
> 通过 token 级关停，全系统仍由 token 驱动，行为可控，且不会误杀第三方组件的必要过渡（如焦点提示、透明度变化）。
> 图表、grid、toast 可根据各自 token 做差异化降级。

---

## 10. Charts Token — 图表色板

图表不是普通 UI，需要独立于 UI Primitive 的色板体系。按三类消费场景拆分。
**不进入 `@theme inline`**，图表库通过 `getComputedStyle()` 在运行时读取 CSS 变量。

### 10.1 基础 UI（坐标轴 / 网格 / 交互元素）

```
Token                          Dark                       Light                      用途
──────────────────────────────────────────────────────────────────────────────
--chart-axis-line              oklch(1 0 0 / 15%)        oklch(0 0 0 / 15%)        坐标轴线
--chart-grid-line              oklch(1 0 0 / 6%)         oklch(0 0 0 / 6%)         网格线
--chart-crosshair              oklch(1 0 0 / 20%)        oklch(0 0 0 / 20%)        十字光标
--chart-crosshair-label-bg     oklch(0.30 0 0)           oklch(0.95 0 0)           十字光标标签背景
--chart-tooltip-bg             oklch(0.22 0 0)           oklch(1 0 0)               Tooltip 背景
--chart-tooltip-border         oklch(1 0 0 / 12%)        oklch(0 0 0 / 12%)        Tooltip 边框
--chart-selection              oklch(0.60 0.15 260 / 20%)oklch(0.50 0.18 260 / 15%)框选区域
--chart-zero-line              oklch(1 0 0 / 25%)        oklch(0 0 0 / 25%)        零线（仅用于语义 0 基准）
```

> `--chart-zero-line` 仅用于收益率图、超额收益图、振荡指标中的**语义 0 基准线**，不用于普通坐标轴 baseline。

### 10.2 市场序列（K 线 / 成交量 / 均线）

```
Token                          值                         用途
──────────────────────────────────────────────────────────────────────
--chart-candle-up              oklch(0.68 0.22 25)        K 线阳线（涨）
--chart-candle-down            oklch(0.72 0.17 155)       K 线阴线（跌）
--chart-volume                 oklch(0.55 0.08 260)       成交量柱（默认色）
--chart-volume-up              oklch(0.68 0.22 25 / 60%)  涨日成交量
--chart-volume-down            oklch(0.72 0.17 155 / 60%) 跌日成交量
```

**均线约定**（颜色 + 线型双重区分，不单靠颜色）：

```
Token                          值                         线型
──────────────────────────────────────────────────────────────────────
--chart-ma-5                   oklch(0.70 0.18 25)        实线, 1.5px
--chart-ma-10                  oklch(0.70 0.14 85)        实线, 1.5px
--chart-ma-20                  oklch(0.60 0.15 260)       实线, 1.5px
--chart-ma-60                  oklch(0.62 0.15 310)       虚线, 1.5px
```

> WCAG 要求不能仅用颜色传达信息。均线通过线型（实线/虚线）和颜色双重区分，色弱用户可依靠线型辨识。

### 10.3 策略序列（净值 / 基准 / 信号 / 风控）

策略序列**不复用市场红绿语法**，形成独立视觉语法：

```
Token                          值                         用途
──────────────────────────────────────────────────────────────────────
--chart-strategy-nav           oklch(0.60 0.16 260)       策略净值曲线（蓝系）
--chart-benchmark              oklch(0.55 0.05 260)       基准指数（灰蓝）
--chart-excess-return          oklch(0.70 0.14 195)       超额收益（cyan/teal）
--chart-drawdown-fill          oklch(0.60 0.12 310 / 40%) 回撤区间填充（低饱和紫红）
--chart-signal-buy-marker      oklch(0.65 0.16 260)       买入信号标记
--chart-signal-sell-marker     oklch(0.65 0.18 310)       卖出信号标记
--chart-risk-threshold         oklch(0.72 0.16 55)        风控阈值线（amber/orange）
--chart-factor-exposure        oklch(0.65 0.15 175)       因子暴露（teal）
```

> 图中"绩效 / 基准 / 超额 / 回撤 / 风控"形成清晰视觉语法，不与 K 线涨跌红绿混淆。

### 10.4 通用多曲线色板（8 色）

```
Token                          值                         预设用途
──────────────────────────────────────────────────────────────────────
--chart-series-1               oklch(0.65 0.20 25)        曲线 A
--chart-series-2               oklch(0.70 0.16 155)       曲线 B
--chart-series-3               oklch(0.62 0.19 260)       曲线 C
--chart-series-4               oklch(0.70 0.14 195)       曲线 D
--chart-series-5               oklch(0.65 0.17 310)       曲线 E
--chart-series-6               oklch(0.60 0.16 85)        曲线 F
--chart-series-7               oklch(0.62 0.17 295)       曲线 G
--chart-series-8               oklch(0.65 0.15 175)       曲线 H
```

> 色相分布补入 cyan(195) / teal(175) / rose(310)，相邻曲线色相间距 > 50°，一眼可分。
> 多线图建议配合线宽（1px / 1.5px / 2px）或 dash 规则做辅助区分。

---

## 11. Grid Token — AG Grid 桥接 + 密度策略

### 11.1 桥接原则

**单一路径**：`themeQuartz.withParams()` 作为 AG Grid 主题主入口，参数值直接引用 Ditto CSS 变量。
CSS 层仅保留密度切换和少量 JS API 不方便表达的细节覆盖。不在 JS 和 CSS 两边同时维护同一组参数。

### 11.2 主题工厂（主路径）

```typescript
import { themeQuartz } from "ag-grid-community";

export function createDittoGridTheme() {
  return themeQuartz.withParams({
    // 色彩：直接引用 Ditto semantic CSS 变量
    backgroundColor: "var(--color-surface-app)",
    foregroundColor: "var(--color-text-primary)",
    headerBackgroundColor: "var(--color-surface-panel)",
    headerTextColor: "var(--color-text-secondary)",
    borderColor: "var(--color-border-default)",
    // 行交互：三档明确分离
    rowHoverColor: "var(--color-surface-hover)",
    oddRowBackgroundColor: "oklch(1 0 0 / 3%)",         // 极轻斑马纹，不与 hover 混淆
    selectedRowBackgroundColor: "var(--grid-row-selected)", // 带 accent 的选中态（CSS 定义）
    // 焦点与强调
    accentColor: "var(--color-ring-focus)",
    // 字体
    fontFamily: "var(--font-sans)",
    fontSize: "var(--grid-font-size, 13px)",
  });
}
```

### 11.3 CSS 补充层（密度 + 少量细修）

```css
.ag-theme-ditto {
  /* 选中行：带 accent 气质，不是普通 surface 选中块 */
  --grid-row-selected: oklch(0.60 0.15 260 / 12%);

  /* 密度变量（由 data-attribute 切换） */
  --grid-row-height: 32px;
  --grid-header-height: 36px;
  --grid-cell-padding-x: 8px;
  --grid-cell-padding-y: 4px;
  --grid-font-size: 13px;
  --grid-size: 2px;
}
```

### 11.4 密度策略（三档）

```
Token                          comfortable    compact(默认) ultra-compact(专业)
──────────────────────────────────────────────────────────────────────────────
--grid-row-height              40px           32px           26px
--grid-header-height           44px           36px           30px
--grid-cell-padding-x          12px           8px            6px
--grid-cell-padding-y          8px            4px            2px
--grid-font-size               13px           13px           11px
--grid-size                    4px            2px            1px
```

**切换方式**：

```css
:root { --grid-row-height: 32px; /* compact 为默认 */ }

[data-grid-density="comfortable"] {
  --grid-row-height: 40px;
  --grid-header-height: 44px;
  /* ... */
}

[data-grid-density="ultra-compact"] {
  --grid-row-height: 26px;
  --grid-header-height: 30px;
  /* ... */
}
```

> compact（32px）为默认主力档，适用于持仓/订单/监控等多数页面。
> ultra-compact（26px）标为"专业模式/高密监控"，需用户显式 opt-in（AG Grid 在极低行高下会压缩排序图标、筛选器、触控命中空间）。
> comfortable（40px）用于研究分析页、详情页等低密度阅读场景。

---

## 12. 调研参考

### 12.1 业界对标平台

| 平台 | 参考点 |
|------|--------|
| TradingView | 暗色主题色板、K 线配色、十字光标交互、多图同步 |
| Bloomberg Terminal | 功能优先、信息密度、键盘导航、可定制工作区 |
| QuantConnect LEAN | 回测结果 UI（9 图表 + 20+ 统计 + 多 Tab） |
| Interactive Brokers TWS | 多图同步、快捷键、可停靠面板 |
| RiceQuant / JoinQuant | A 股红涨绿跌、中文 UI、因子分析可视化 |

### 12.2 关键设计原则（从业界提炼）

- 暗色主题默认，A 股红涨绿跌
- 模块化面板布局，可拖拽/调整大小
- 2 秒评估原则：P&L 和持仓状态始终可见
- 钻取层级：组合 → 行业 → 标的 → 交易 → 指标
- 跨图表时间同步：缩放一个图表，所有图表联动
- 高频流绕开 React 渲染链（Lightweight Charts / ECharts imperative API）
- 数字右对齐 + tabular-nums（默认 sans，mono 仅限技术型字段）
- 实时更新用闪烁高亮，禁止数字滚动动画

### 12.3 技术栈约束

- shadcn/ui v4：CSS variables 主题 + CVA 变体 + `data-slot` 精确样式化
- Tailwind CSS 4.x：`@theme inline` 注册 utility，CSS-first 配置
- AG Grid Community 35.x：`themeQuartz.withParams()` + CSS 变量桥接
- Lightweight Charts 4.x / ECharts 5.x：imperative API，CSS 变量消费
- OKLCH 色彩空间，W3C DTCG 格式（未来跨平台时引入 Style Dictionary）

# Design System Standardization Design

> 基于 Google Labs `design.md` 规范分析，为 Ditto 设计的 AI 设计系统标准化方案。
>
> 日期：2026-04-24
> 状态：待实施

---

## 1. 背景与动机

### 1.1 Google DESIGN.md 规范概览

Google Labs 发布了 `design.md` 规范（alpha），核心思路：

- **YAML front matter**：机器可读的 design tokens（colors、typography、spacing、rounded、components）
- **Markdown body**：人类可读的设计理念说明
- **CLI 工具链**：`lint`（WCAG 对比度、断链引用）、`diff`（版本对比）、`export`（Tailwind/DTCG）
- **目标**：给 AI 编码代理提供结构化的设计系统理解

### 1.2 Ditto 当前状态

| 维度 | Ditto 现状 |
|------|-----------|
| Token 架构 | 9 层 CSS 变量（base/semantic/atmosphere/shell/data-viz/component/interaction/domain/density） |
| Token 数量 | 138+ tokens（95 色 + 16 排版 + 11 间距 + 6 圆角 + 5 动效 + 5 无障碍） |
| 色彩空间 | OKLCH |
| 主题系统 | dark/light/market-intl + 6 域签名色 + Chromatic Atmosphere 时间色变 |
| Agent 理解 | CLAUDE.md + .claude/rules/ + prompt pack（Claude 专属） |
| 验证体系 | 4 层视觉验证（L0 完整性 + L1 Token + L2 布局 + L2.5 微观样式 + L3 像素） |
| 组件系统 | shadcn/ui + semantic tokens + barrel export |
| 成熟度 | 已有 29 页 prototype + 完整 5 阶段 pipeline |

### 1.3 核心动机

1. **标准化设计描述**：创建跨 AI 工具通用的设计系统描述格式
2. **借用 lint/diff 工具**：WCAG 对比度检查、断链引用检测、版本 diff
3. **纯研究/学习**：跟踪业界 AI 设计规范和 W3C Design Token 标准趋势
4. **视觉风格审视**：重新评估"Graphite Studio"（对标 Linear/Vercel/Raycast）是否最适合量化工作站的气质

### 1.4 关键判断

> **DESIGN.md ≠ Design Token 标准**
>
> W3C DTCG Design Token Format 才是"CSS design-token 标准"。Google DESIGN.md 是"AI agent 设计系统描述"规范。
> Ditto 不需要用 DESIGN.md 替代现有的 CSS token 体系，而是借鉴其结构化描述思路。

---

## 2. 优先级排序

| 优先级 | 方向 | 理由 |
|:---:|------|------|
| **P0** | 创建 Ditto DESIGN.md + 全面改造规则/工作流 | 立即可做，复用现有素材，直接解决跨 AI 工具理解痛点 |
| **P1** | 验证工具链增强 | 补充 WCAG 对比度、断链检测、版本 diff |
| **P2** | Token 格式标准化（DTCG 互通） | 当前无多平台导出需求，ROI 不高 |

---

## 3. P0 方案：Ditto DESIGN.md

### 3.1 文件位置

```
docs/DESIGN.md          ← 新增：AI 设计系统描述文件
```

### 3.2 YAML Front Matter 结构

```yaml
---
version: "1.0"
name: Ditto Graphite Studio
description: >
  Personal quantitative research and live-trading professional workstation.
  Terminal-style workspace with high information density.

colors:
  # L1 Base primitives (38 tokens)
  neutral:
    0: "oklch(0.988 0.004 253)"
    25: "oklch(0.960 0.004 253)"
    50: "oklch(0.875 0.006 253)"
    # ... 15-step scale through 950
  brand:
    300: "oklch(0.760 0.120 235)"
    400: "oklch(0.640 0.120 235)"
    500: "oklch(0.520 0.140 235)"   # Lapis hue 235°
    600: "oklch(0.430 0.130 235)"
    700: "oklch(0.350 0.110 235)"
  functional:
    green: { 400: "...", 500: "...", 600: "..." }
    red:   { 400: "...", 500: "...", 600: "..." }
    amber: { 400: "...", 500: "...", 600: "..." }
    orange: { 400: "...", 500: "...", 600: "..." }
    cyan:  { 400: "...", 500: "...", 600: "..." }
    purple: { 400: "...", 500: "...", 600: "..." }

  # L2 Semantic (57 tokens)
  surface:
    app: "oklch(0.176 0.004 253)"
    panel-base: "oklch(0.166 0.010 253)"
    panel-elevated: "..."
    strip: "..."
    overlay: "..."
    modal: "..."
    muted: "..."
    elevated: "..."
    frosted: "..."
    frosted-subtle: "..."
  text:
    primary: "oklch(0.940 0.004 253)"
    secondary: "..."
    tertiary: "..."
    quaternary: "..."
    disabled: "..."
    inverse: "..."
    # ... 12-level hierarchy
  border:
    subtle: "oklch(0.255 0.006 253)"
    default: "..."
    strong: "..."
    focus: "..."
    error: "..."
    warning: "..."
  brand-accent:
    accent: "{colors.brand.500}"
    accent-hover: "..."
    accent-subtle: "..."
    accent-fg: "..."

  # L7 Domain signatures
  domain:
    trading:
      fg: "oklch(...)"      # Brass hue 74
      muted: "..."
      line: "..."
      subtle: "..."
    markets:
      fg: "oklch(...)"      # Cyan hue 220
      muted: "..."
      line: "..."
      subtle: "..."
    research:
      fg: "oklch(...)"      # Purple hue 300
      muted: "..."
      line: "..."
      subtle: "..."
    platform:
      fg: "oklch(...)"      # Lapis hue 235
      muted: "..."
      line: "..."
      subtle: "..."
    home:
      fg: "oklch(...)"      # Brass hue 74
      muted: "..."
      line: "..."
      subtle: "..."
    ai:
      fg: "oklch(...)"      # Magenta hue 310
      muted: "..."
      line: "..."
      subtle: "..."

typography:
  ui:
    fontFamily: Inter
    fallback: "Noto Sans SC Variable (Source Han)"
    sizes: [10, 11, 12, 13, 14, 16, 24]  # px
    weights: [400, 500, 600]
    lineHeight: { body: 1.5, compact: 1.35, dense: 1.25 }
    letterSpacing: { label: "-0.01em", heading: "-0.02em" }
  heading:
    fontFamily: "Geist Sans"
    fallback: Inter
  numeric:
    fontFamily: Inter
    features: "tabular-nums slashed-zero"
  code:
    fontFamily: "Geist Mono"
    fallback: "JetBrains Mono"

spacing:
  scale: 4pt
  steps: [2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 32]  # px

rounded:
  steps: [2, 3, 4, 6, 8, 12]  # px

shadows:
  # If applicable, elevation system

components:
  panel:
    backgroundColor: "{colors.surface.panel-base}"
    borderColor: "{colors.border.subtle}"
    rounded: "{rounded.6}"
  button-primary:
    backgroundColor: "{colors.brand-accent.accent}"
    textColor: "{colors.surface.app}"
    rounded: "{rounded.4}"
  button-secondary:
    backgroundColor: "{colors.surface.elevated}"
    textColor: "{colors.text.primary}"
    borderColor: "{colors.border.default}"
    rounded: "{rounded.4}"
  # ... more shadcn/ui component tokens
---
```

### 3.3 Markdown Body 章节结构

遵循 Google DESIGN.md 的 8 节顺序 + Ditto 扩展：

```
## Overview
  设计哲学 + 产品定位 + "视觉服务于判断"核心原则

## Colors
  调色板体系（base → semantic → domain）
  OKLCH 色彩空间说明
  品牌色 Lapis (hue 235°) 的选择理由
  签名色 Brass 的使用规则
  域签名色体系说明
  禁止事项（跨域颜色混用等）

## Typography
  4 角色字体系统（heading/body/numeric/code）
  字号层级（7 级：10-24px）
  字重使用规则（400/500/600 的使用场景）
  数字排版的 tabular-nums 规则
  行高/字距与密度系统联动

## Layout
  Shell 三区架构（Rail + Header + Main）
  密度系统（Dense 34px / Compact 36px / Comfortable 42px）
  页面类型与布局模板（仪表盘/列表/详情/构建器/控制台）
  信息层级（L1/L2/L3 三级折叠）
  一页一主面 + 允许一个辅面原则

## Elevation & Depth
  表面层级（10 级 elevation）
  毛玻璃效果（frosted/frosted-subtle）
  Overlay 系统（7 级透明度）
  z-index 规范

## Shapes
  圆角系统（6 级）
  边框系统（subtle/default/strong）
  分割线规范

## Components
  shadcn/ui 核心组件 + semantic token 映射
  Panel 组件族（panel / panel-header / panel-grow）
  Table 组件族（data-table / column-header / row）
  Status 组件族（badge / indicator / tag）
  交互组件族（button / input / select / command）

## Domain Identity
  6 域签名色体系
  签名色流转规则（header 下划线 / rail 光条 / panel 呼吸边框）

## Chromatic Atmosphere
  时间色变机制（亚感知级背景色温偏移）
  运行时动态 token 说明
  与静态 token 的关系

## Do's and Don'ts
  10 项禁止事项（从 Prompt Pack 迁移）
  关键 dos（token 引用、语义化颜色、双维度表达等）

## Glossary
  术语表（density / shell / rail / panel / context-rail / pulse 等）
```

### 3.4 与 Google DESIGN.md 的差异

| Google DESIGN.md | Ditto DESIGN.md | 原因 |
|-----------------|----------------|------|
| hex 色值 | OKLCH 色值 | 更精确的色域控制 |
| 无主题系统 | dark/light/market-intl 主题 | Ditto 支持多主题 |
| 单字体系统 | 4 角色字体系统 | 不同功能域有不同排版需求 |
| 无域概念 | 6 域签名色 + 品牌色 | Ditto 有业务域语义色系统 |
| 无动态效果 | Chromatic Atmosphere | 运行时色温偏移 |
| 简单 components | shadcn/ui 组件映射 | 更复杂的组件 token 体系 |
| 8 节固定 | 11 节（+Domain/Atmosphere/Glossary） | Ditto 特有的设计概念 |

---

## 4. P0 方案：规则和工作流全面改造

### 4.1 CLAUDE.md 更新

**位置**：`/home/chevy/projects/ditto-app/CLAUDE.md`

**新增内容**（在"项目规范"章节）：

```markdown
### 设计系统描述

`docs/DESIGN.md` 是 Ditto 设计系统的 **AI 可读入口**。所有 AI agent 在参与 Ditto 的设计或编码工作前，应先阅读此文件以理解：
- 调色板体系（OKLCH + 域签名色）
- 排版系统（4 角色字体）
- 间距/圆角/阴影规范
- 组件 token 映射
- 设计哲学和禁止事项

**注意**：`DESIGN.md` 是描述层，不是 token 的 SSOT。token 的唯一真理源仍是 `src/styles/design-tokens/`。
```

### 4.2 .claude/rules/design-tokens.md 更新

**新增章节**（文件末尾）：

```markdown
## AI 可读设计系统描述

`docs/DESIGN.md` 是设计系统的结构化描述文件，供所有 AI agent 消费。

### 与 Token SSOT 的关系

| 文件 | 角色 | 消费者 |
|------|------|--------|
| `src/styles/design-tokens/*.css` | SSOT（值的权威来源） | Prototype HTML + React |
| `docs/DESIGN.md` | 描述层（为什么 + 怎么用） | AI agent（设计/编码/review） |

### 同步规则

- Token 值变更时：更新 CSS → 同步 DESIGN.md 的 YAML front matter
- 新增 token 时：更新 CSS → 同步 DESIGN.md 的 YAML + Markdown body
- 设计原则变更时：更新 DESIGN.md → 同步 Visual Constitution spec
```

### 4.3 .claude/rules/tailwind.md 更新

**新增章节**（@theme inline 铁律之后）：

```markdown
## DESIGN.md 与 Tailwind 的关系

`docs/DESIGN.md` 的 YAML front matter 中的 token 值应与 `src/styles/design-tokens/` 中的值保持一致。
Tailwind utility class 的使用应遵循 DESIGN.md 中 Components 章节的 token 映射。
```

### 4.4 Prompt Pack 更新

**文件**：`design/specs/05_prompt_pack_for_ai_design_and_coding.md`

**修改**：在 Section 9 (One-Line Usage) 中新增 DESIGN.md 引用：

```markdown
### Before any AI participates in Ditto design or coding, provide:
1. docs/DESIGN.md (design system description — read this first)
2. Visual Constitution (00_ditto_visual_constitution.md)
3. Shell/Page/Data/Component/Token specs
4. This Prompt Pack (input constraints)
5. Target page blueprint
```

### 4.5 Pipeline Skills 改造

#### 4.5.1 ditto-design-cycle 改造

**问题**：create-mode.md 引用了过时的 `tokens-style.css`。

**修改**：
1. **create-mode.md**：将 `tokens-style.css` 引用更新为 `src/styles/design-tokens/tokens-*.css`
2. **Phase 0.5**：新增步骤 — 读取 `docs/DESIGN.md` 作为设计参考输入
3. **Review scoring**：新增 "DESIGN.md 一致性" 维度 — prototype 的组件 token 使用是否与 DESIGN.md Components 章节一致

#### 4.5.2 ditto-page-contract 改造

**修改**：
1. **Create flow Phase R**（读取阶段）：新增读取 `docs/DESIGN.md` 的 components 章节作为 token 映射参考
2. **Validation**：15 项 checklist 中新增可选检查 — contract 中的组件 token 引用是否存在于 DESIGN.md

#### 4.5.3 ditto-app-dev 改造

**修改**：
1. **SKILL.md**：在 Design System Priority 中新增 P0 — `docs/DESIGN.md` 作为最高优先级的设计系统参考
   - P0: `docs/DESIGN.md`（设计系统描述）
   - P1: `src/styles/design-tokens/`（token SSOT）
   - P2: page contract selector/threshold
   - P3: prototype literal values
2. **Phase 11 ARCHITECT**：`impeccable:normalize` 之前先检查 DESIGN.md Components 章节中的 token 映射
3. **Phase 13 POLISH**：Step 1 Design System alignment 中新增 DESIGN.md 一致性检查

#### 4.5.4 ditto-product-discovery 改造

**修改**：无需改动。Product discovery 不涉及视觉 token 细节。

### 4.6 新增 Hook（可选）

**Git pre-commit hook**：当 `src/styles/design-tokens/*.css` 文件变更时，提示开发者同步 `docs/DESIGN.md`。

```json
// .claude/settings.json
{
  "hooks": {
    "post-commit": [
      {
        "matcher": "src/styles/design-tokens/.*\\.css$",
        "command": "echo '⚠️ Design token files changed. Remember to sync docs/DESIGN.md if values were added/modified.'"
      }
    ]
  }
}
```

---

## 5. P1 方案：验证工具链增强

### 5.1 WCAG 对比度检查脚本

**实现方式**：解析 `src/styles/design-tokens/tokens-semantic.css` 中所有 `--*-bg` / `--*-text` / `--surface-*` / `--text-*` 的 OKLCH 值，计算对比度。

**流程**：
1. 解析 CSS 提取 OKLCH 值
2. OKLCH → sRGB 转换
3. WCAG 2.1 对比度计算
4. 输出不符合 AA 标准（< 4.5:1）的 token 对

**集成**：可选 CI step 或 `bun run check` 子命令。

### 5.2 Token 断链检测脚本

**实现方式**：扫描所有 CSS 文件中的 `var(--xxx)` 引用，确认每个引用都有对应的 `:root` 定义。

**关键检查**：
- `globals.css` 中的 `@theme inline` 引用的变量是否存在于 `:root`
- Prototype HTML 中的 `var(--xxx)` 是否存在于 `tokens-base.css`
- React 组件中通过 Tailwind 间接引用的 token 是否存在于设计 token 文件

### 5.3 Token 版本 Diff

**实现方式**：git diff 对 `tokens-*.css` 的变更生成摘要报告。

**报告格式**：
```
## Token Changes (main → feat/xxx)
### Added
- --brand-new-accent: oklch(0.600 0.150 235)

### Modified
- --surface-app: oklch(0.176 0.004 253) → oklch(0.180 0.004 253)

### Removed
- --legacy-color: oklch(0.500 0.100 200)
```

**不采用 `@google/design.md lint` 的原因**：需要先将 tokens 转成 DESIGN.md YAML 格式，引入成本高。自写脚本直接解析 CSS 更高效。

---

## 6. P2 方案：Token 格式标准化（DTCG 互通）

### 6.1 架构

```
src/styles/design-tokens/    ← SSOT（当前已有，不动）
└── export.ts                ← 新增：导出脚本
    └── 输出 → tokens.json  ← DTCG 格式
              │
              ├→ Tailwind theme（已有 @theme inline）
              ├→ Style Dictionary（可选）
              └→ Figma Token Studio（可选）
```

### 6.2 推迟原因

| 因素 | 分析 |
|------|------|
| 当前痛点 | 无。CSS SSOT 工作正常 |
| 多平台需求 | 无。不需要 iOS/Android/Flutter |
| 设计工具 | 不用 Figma |
| OKLCH 支持 | DTCG 对 OKLCH 的支持仍在发展 |
| 维护成本 | 多一层导出 = 多一个同步点 |

**结论**：在 DESIGN.md 中预留 `export` 命令的说明文档，等有多平台需求时再实施。

---

## 7. 视觉风格评估（已完成 — 维持 Graphite Studio）

### 7.1 当前：Graphite Studio（基准线）

- **参考**：Linear / Vercel / Raycast
- **调性**：现代 SaaS 清爽风，balanced density
- **问题**：对标产品是 SaaS 工具，不是专业量化工作站

### 7.2 候选 A：Deep Control（深空控制台）

- **参考**：Bloomberg Terminal 现代重设计 + Raycast + Datadog
- **调性**：终端控制台，cool-neutral，high-density compact
- **核心变化**：warm limestone → cool charcoal, balanced → high-density, Lapis 更锐利, flat → thin borders
- **适合**：高频交易员、实时监控场景

### 7.3 候选 B：Warm Atelier（暖调工坊）

- **参考**：Obsidian app + 高端制表工具 + 建筑事务所
- **调性**：精密仪器感，有机材质，warm brown undertone
- **核心变化**：limestone → walnut brown, Brass 更突出, serif labels, 材质纹理
- **适合**：量化研究员、深度分析场景

### 7.4 候选 C：Fintech Edge（金融科技前沿）

- **参考**：Ramp + Mercury + Exponent
- **调性**：现代金融科技，true black base，电光点缀
- **核心变化**：limestone → true black, Lapis → electric blue, glassmorphism, 更大的留白
- **适合**：年轻化团队、对外展示场景

### 7.5 候选 D & E：讨论后关闭

经 2026-04-24 深度讨论 + 4 方案并排 demo 对比，结论：**维持 Graphite Studio 不变**。

**对比结论**：
- Graphite Studio 在可读性、舒适度、专业感上已达良好平衡，并排对比后仍然最优
- Cinematic Data：光晕/动画酷但高频使用易疲劳，适合展示不适合日常
- Operational Blueprint：军事指挥美学辨识度最高但牺牲日常可读性（全 mono、零圆角、网格背景）
- Precision Instrument：衬线数字 + gauge 环有品质感但偏展示模式

**可选微增强**（不改变整体方向，仅组件级调味）：
| 元素 | 来源 | 改动量 |
|------|------|--------|
| 信号点加微型 gauge 环 | Precision Instrument | 仅组件级 |
| Banner shimmer 光效 | Cinematic Data | 仅 1 组件 |
| 关键数值用衬线数字 | Precision Instrument | 仅 metric-value |
| 优先级用左侧色条 | Operational Blueprint | 仅组件级 |

**Demo 文件**（归档参考）：
- `prototype/style-comparison-00-baseline-graphite-studio.html`
- `prototype/style-comparison-A-cinematic-data.html`
- `prototype/style-comparison-B-operational-blueprint.html`
- `prototype/style-comparison-C-precision-instrument.html`

### 7.6 评估标准

每个候选方案应通过以下评估：

| 维度 | 权重 | 说明 |
|------|:---:|------|
| 判断力支持 | 30% | 信息是否清晰可读，状态一目了然 |
| 长期使用舒适度 | 25% | 3h 连续使用不疲劳，30d 持续使用不厌倦 |
| 专业气质 | 20% | 是否像专业工作站，而非消费级 SaaS |
| 与现有 token 兼容性 | 15% | 改动成本（138 tokens + 29 prototypes） |
| 差异化 | 10% | 与市面产品（Bloomberg, TradingView, 同类工具）的区分度 |

### 7.7 落地方式

对每个候选方案：
1. 制作 1-2 个代表性页面的 prototype mockup
2. 提取关键 CSS 变量值作为 token 对比
3. 与当前 Graphite Studio 做并排对比

---

## 8. 实施路径

### Phase 1: DESIGN.md 创建（P0）

1. 从现有 CSS token 文件提取所有 token 值到 YAML front matter
2. 从 Visual Constitution / Prompt Pack / 各 spec 文件整合 Markdown body
3. 创建 `docs/DESIGN.md`
4. 验证 YAML front matter 与 CSS token 值一致

### Phase 2: 规则更新（P0）

1. 更新 CLAUDE.md — 新增 DESIGN.md 引用
2. 更新 design-tokens.md — 新增 AI 可读描述章节
3. 更新 tailwind.md — 新增 DESIGN.md 关系说明
4. 更新 Prompt Pack — 新增 DESIGN.md 为必读输入
5. 提交规则更新

### Phase 3: Pipeline Skills 改造（P0）

1. 修复 ditto-design-cycle 中的过时 token 引用
2. 在 3 个 skill 中新增 DESIGN.md 消费点
3. 更新 Design System Priority 层级
4. 测试 pipeline 端到端流程

### Phase 4: 验证工具链（P1）

1. 实现 WCAG 对比度检查脚本
2. 实现 token 断链检测脚本
3. 实现 token 版本 diff 脚本
4. 集成到 `bun run check` 或 CI

### Phase 5: 视觉风格评估（独立讨论）

1. 确定 5 个候选方案
2. 为每个方案制作 prototype mockup
3. 按评估标准打分
4. 决策是否切换风格方向
5. 如切换：制定 token 迁移计划

### Phase 6: Token 格式标准化（P2，按需）

1. 等多平台需求出现时启动
2. 实现 CSS → DTCG tokens.json 导出脚本
3. 与 Style Dictionary 集成（可选）

---

## 附录 A: 参考资源

- Google DESIGN.md 规范：https://github.com/google-labs-code/design.md
- W3C Design Tokens Community Group：https://design-tokens.github.io/community-group/format/
- Style Dictionary (Amazon)：https://amzn.github.io/style-dictionary/
- Token Studio (Figma)：https://www.figma.com/community/plugin/927164123917636582/Token-Studio

## 附录 B: 相关项目文件

| 文件 | 用途 |
|------|------|
| `docs/DESIGN.md` | 待创建：AI 设计系统描述 |
| `design/specs/00_ditto_visual_constitution.md` | 视觉宪法 |
| `design/specs/05_prompt_pack_for_ai_design_and_coding.md` | AI Prompt Pack |
| `src/styles/design-tokens/tokens-base.css` | L1 基础 token |
| `src/styles/design-tokens/tokens-semantic.css` | L2 语义 token |
| `.claude/rules/design-tokens.md` | Token 架构规范 |
| `.claude/rules/tailwind.md` | Tailwind CSS 规范 |
| `.claude/rules/visual-verification.md` | 视觉验证规范 |
| `.claude/skills/ditto-design-cycle/` | Pipeline 1 skill |
| `.claude/skills/ditto-page-contract/` | Pipeline 2 skill |
| `.claude/skills/ditto-app-dev/` | Pipeline 3 skill |

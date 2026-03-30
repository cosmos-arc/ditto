---
name: ditto-design-review
description: 多角色设计审查编排 — UI 视觉 / UX 交互 / 功能可用性 / 界面语言 / 品牌气质五维度审查，协商优化达成一致
---

# /ditto-design-review

多角色设计审查编排 Skill。聚焦设计交付物质量——UI 视觉、交互体验、功能可用性、界面语言、品牌气质，通过五角色并行审查识别冲突与共识，协商优化达成一致。

## 规范参考

- **设计规范**: [docs/designs/specs/](../../docs/designs/specs/)（参考起点，非刚性约束）
- **Design Token**: [docs/designs/specs/prototypes/shared/tokens-base.css](../../docs/designs/specs/prototypes/shared/tokens-base.css) 及其 9 层体系
- **设计决策**: [docs/designs/decisions/](../../docs/designs/decisions/)（**Art Director 刚性锚点** — 9 项关键决策定义了 Graphite Studio 的审美方向）
- **品牌 DNA**: Style B Graphite Studio — Linear/Vercel/Raycast 的克制感 + Bloomberg/quant desk 的专业终端感
- **架构规范**: [architecture.md](../rules/architecture.md)

## 输入

`$ARGUMENTS` — 审查目标 + 可选参数

```bash
# 全流程审查
/ditto-design-review docs/designs/specs/prototypes/style-b-graphite-studio/page-cross-market.html

# 指定质量等级（默认 polished）
/ditto-design-review page-cross-market.html --level best

# 仅运行特定角色
/ditto-design-review page-cross-market.html --ui
/ditto-design-review page-cross-market.html --ux
/ditto-design-review page-cross-market.html --product
/ditto-design-review page-cross-market.html --copy
/ditto-design-review page-cross-market.html --ad

# 仅精修（跳过审查，直接应用 impeccable skills）
/ditto-design-review page-cross-market.html --polish

# 指定审查基准（对照某个原型版本）
/ditto-design-review page-cross-market.html --baseline prototype-v2.html

# 反向同步（验收后，将 review 变更写回设计文档）
/ditto-design-review page-cross-market.html --sync
```

## 原型版本管理（git tag）

> **每次 review 前，通过 git tag 快照当前状态。回退和对比均依赖 git 原生能力。**

### 工作流

```
Phase 0: VERSION（在所有审查之前）

  1. 确定目标文件（如 page-cross-market.html）
  2. 检查已有 tag（git tag -l 'review/round-*'）确定下一个轮次号
  3. git add 目标文件 → git commit -m "docs(review): round-{N} pre-review snapshot"
  4. git tag review/round-{N}
  5. 后续所有修改直接在原文件上进行
```

### 回退操作

```bash
# 回退到 round-2 的状态
git checkout review/round-2 -- page-cross-market.html
```

### 版本对比

```bash
# 查看 HTML 变更
git diff review/round-1..review/round-2 -- page-cross-market.html

# 查看变更摘要
git log review/round-1..review/round-2 --oneline -- page-cross-market.html
```

### 约束

- Tag 命名：`review/round-{N}`（全局递增，不按页面分段）
- 活跃文件是唯一被 review 修改的文件
- 审查报告标注对应 tag，如 `Tag: review/round-2`
- 不保存 HTML 副本、不自动截图到磁盘

---

## 核心理念

> **不是"对照 spec 打分"，而是"多角色专家讨论，共同优化设计"。**

- Design Spec 是**参考起点**，不是刚性约束
- 各角色可能给出**相互冲突的建议**（如 UI 想加大间距 vs 产品想增加信息密度）
- Claude 负责呈现冲突 + 分析权衡 + 推荐折中方案
- **用户是最终决策者**，选择采纳哪些建议
- 审查可能产生**新的设计决策**，自动记录到 `docs/designs/decisions/`
- 如果信息架构或交互流程有重大调整，同步更新 spec 文档

---

## 五个审查角色

### 1. UI Designer（视觉设计审查）

**关注维度：** 视觉品质、Token 一致性、布局节奏、色彩运用、字体排版

**审查清单：**

| 检查项 | 说明 |
|--------|------|
| Design Token 一致性 | 颜色/间距/字号是否使用 CSS 变量，是否有硬编码值 |
| 视觉层次 | 标题/正文/辅助文本的层次是否清晰 |
| 色彩运用 | 主色/强调色/功能色使用是否恰当，对比度是否足够 |
| 字体排版 | 字号/字重/行高的节奏是否和谐 |
| 间距节奏 | 组件间/内容间的间距是否一致且合理 |
| 布局平衡 | 对齐方式、留白比例、视觉重心 |
| 响应式 | 不同断点下的布局表现 |
| 风格一致性 | 与其他页面的视觉风格是否统一 |

**使用工具：**
- Chrome DevTools MCP: `take_screenshot` + `evaluate_script` 提取 computed styles
- 对比 token 定义：`tokens-style.css` / `tokens-base.css`
- impeccable skills: `normalize`, `colorize`, `typeset`, `arrange`

### 2. UX Reviewer（交互体验审查）

**关注维度：** 可用性、可访问性、交互流程、信息架构、响应式体验

**审查清单：**

| 检查项 | 说明 |
|--------|------|
| 信息架构 | 内容组织是否合理，用户能否快速找到目标 |
| 交互流程 | 核心用户路径是否顺畅，有无断裂点 |
| 可访问性 | WCAG 合规（颜色对比度、键盘导航、aria 标签） |
| 反馈机制 | 操作反馈是否及时明确（loading、success、error） |
| 错误处理 | 错误状态是否有清晰提示和恢复路径 |
| 空状态 | 列表/数据为空时的展示是否友好 |
| 响应式交互 | 移动端触摸目标大小、手势交互 |
| 认知负荷 | 单屏信息量是否适中，是否需要渐进展示 |

**使用工具：**
- Chrome DevTools MCP: 交互测试、tab 导航、`lighthouse_audit`
- impeccable skills: `critique`, `audit`, `harden`

### 3. Product Manager（产品功能审查）

**关注维度：** 功能完整性、用户场景覆盖、优先级、信息密度

**审查清单：**

| 检查项 | 说明 |
|--------|------|
| 功能完整性 | spec 定义的功能是否全部实现 |
| 用户场景 | 关键用户场景是否覆盖（新增/查看/编辑/删除等） |
| 信息密度 | 信息量是否匹配用户期望（专业用户 vs 普通用户） |
| 优先级 | 最重要的信息是否在第一视觉层级 |
| 数据展示 | 数据格式/精度/单位是否合理 |
| 状态管理 | 各种状态（加载/空/错误/边界）是否处理 |
| 与其他页面的关系 | 页面间的导航/数据流是否合理 |

**使用工具：**
- 对比 spec 文档：信息架构、页面蓝图、组件规范
- ui-ux-pro-max skill

### 4. Copy Editor（界面语言审查）

**关注维度：** 文案清晰度、语气一致性、标签准确性、中文表达质量

**审查清单：**

| 检查项 | 说明 |
|--------|------|
| 标签准确性 | 按钮/菜单/字段的标签是否准确描述功能 |
| 文案清晰度 | 用户能否理解每段文案的含义 |
| 语气一致性 | 整体语气是否统一（专业但不冷漠） |
| 中英文混排 | 混排规则是否一致（间距、标点） |
| 数字/单位 | 格式是否统一（百分比/小数/千分位） |
| 空间效率 | 文案是否简洁，不浪费屏幕空间 |

**使用工具：**
- impeccable skills: `clarify`

### 5. Art Director（艺术总监审查）

**关注维度：** 高级感、克制度、跨页一致性、品牌方向锚定

> **不看功能，不看文案，只看气质。** 确保 Graphite Studio 的审美方向（Linear/Vercel/Raycast 的克制感 + Bloomberg/quant desk 的专业终端感）不被功能性改进侵蚀。

**审查清单：**

| 检查项 | 量化方法 | 阈值/标准 |
|--------|---------|-----------|
| 高亮描边密度 | 统计页面中 `border`/`outline`/`box-shadow` 用作高亮的元素数量 | 单页 ≤ 5 处品牌色描边 |
| 强调色面积比 | `--brand-accent` 覆盖的视觉面积占总面积比例 | ≤ 3% |
| 视觉元素层级数 | 不同装饰元素类型数（badge/标签/状态点/编号/箭头/分隔线/图标） | ≤ 6 种 |
| 留白节奏比 | 内容区占比 vs 留白区占比（不含 shell） | 留白 ≥ 35% |
| 色彩种类数 | 页面中使用的不同语义色彩种类（不含 neutral） | ≤ 4 种功能色 |
| 跨页语言一致性 | 对比其他页面的视觉指纹差异度 | ≥ 7/10 |
| 品牌方向评分 | 整体气质偏向 Bloomberg/quant desk 还是 SaaS dashboard | ≥ 8/10 Bloomberg 方向 |

**气质评分卡（输出到报告中）：**

```
气质评分卡：
├─ 克制度:    ████████░░ 8.2/10
├─ 一致性:    ███████░░░ 7.5/10
├─ 高级感:    ████████░░ 8.0/10
├─ 品牌方向:  ████████░░ 8.3/10
└─ 综合气质:  ████████░░ 8.0/10
```

**否决权规则：**
- 可**降级**某项 polish 变更（如把 `bolder` 降为 `normalize`）
- 可**移除**过度的 `delight`/`overdrive` 效果
- **不可否决**：功能性修复（P0）和可访问性修复

**使用工具：**
- Chrome DevTools MCP: `evaluate_script` 批量提取 computed styles → 统计高亮/描边/色彩面积
- Chrome MCP: `take_screenshot` 对比上一版本截图 + 跨页截图
- impeccable skills: `critique`（审美评价）、`quieter`（降级过度装饰）
- WebSearch: 查找标杆产品（Bloomberg Terminal / Linear / Vercel / Raycast）截图做气质参考

---

## 质量等级

| 等级 | 标准 | 对应 impeccable skills |
|------|------|----------------------|
| **functional** | 正确渲染、可交互、无明显 bug、基本可访问 | — |
| **good** | Token 一致、响应式、布局合理、文案准确 | `normalize`, `arrange`, `clarify` |
| **polished** | 视觉层次清晰、节奏感、微交互、令人舒适 | + `colorize`, `typeset`, `animate` |
| **best** | 高级感、令人印象深刻、记忆点、业界领先 | + `bolder`, `delight`, `overdrive` |

默认等级：`polished`

---

## 执行流程

### 全流程（默认）

```
┌─────────────────────────────────────────────────────────┐
│ Phase 0: VERSION（git tag 快照）                          │
│                                                         │
│   1. 检查已有 tag（review/round-*）确定轮次号              │
│   2. git add 目标文件 → git commit                      │
│   3. git tag review/round-{N}                           │
│   4. 后续修改直接在原文件上进行                           │
├─────────────────────────────────────────────────────────┤
│ Phase 1: BASELINE（基线采集 + 跨页视觉指纹）              │
│                                                         │
│   1. 读取目标文件（HTML 原型或 React 组件）               │
│   2. 读取相关 spec 文档（作为参考）                        │
│   3. 读取 Design Token 定义                              │
│   4. 读取设计决策文档（Art Director 刚性锚点）            │
│   5. Chrome MCP: evaluate_script（提取关键元素 styles）    │
│   6. [新增] 跨页视觉指纹采集：                            │
│      ├─ evaluate_script 提取各页面的视觉指纹：             │
│      │   高亮描边密度 / 强调色面积比 / 视觉元素层级数     │
│      │   留白节奏比 / 色彩种类数                          │
│      └─ 生成「跨页一致性基线」                            │
├─────────────────────────────────────────────────────────┤
│ Phase 2: PARALLEL REVIEW（并行审查）                      │
│                                                         │
│   启动 5 个并行 Agent，每个扮演一个角色：                   │
│   ├─ UI Designer Agent   → 输出: UI 问题清单              │
│   ├─ UX Reviewer Agent   → 输出: UX 问题清单              │
│   ├─ Product Mgr Agent   → 输出: 产品问题清单             │
│   ├─ Copy Editor Agent   → 输出: 文案问题清单             │
│   └─ Art Director Agent  → 输出: 气质问题清单 + 评分卡    │
│                                                         │
│   每个角色的输出格式：                                    │
│   - 🔴 P0: 必须修复（阻断性问题）                         │
│   - 🟡 P1: 建议修复（影响体验）                           │
│   - 🟢 P2: 可选优化（锦上添花）                           │
│   - 💡 建议：对设计/信息架构的调整建议                     │
├─────────────────────────────────────────────────────────┤
│ Phase 3: CONFLICT RESOLUTION（冲突协调）                  │
│                                                         │
│   1. 汇总 5 个角色的问题清单                              │
│   2. 去重合并相似问题                                     │
│   3. 识别角色间的冲突点                                   │
│   4. 为每个冲突提供分析 + 折中方案                        │
│   5. 识别所有角色的共识点                                 │
│                                                         │
│   Art Director 冲突优先级规则：                            │
│   ├─ AD vs UI（装饰 vs Token）→ AD 优先                  │
│   ├─ AD vs PM（功能标签 vs 克制）→ 协商，AD 可要求更     │
│   │  安静的实现方式                                      │
│   ├─ AD vs UX（affordance vs 高级感）→ UX 优先           │
│   │  （可访问性不妥协）                                  │
│   └─ AD vs 所有（整体气质 vs 局部优化）→ AD 整体视角     │
│     优先
├─────────────────────────────────────────────────────────┤
│ Phase 4: USER DECISION（用户决策）                        │
│                                                         │
│   使用 AskUserQuestion 呈现：                             │
│   - 共识点（所有角色一致认同，建议直接采纳）               │
│   - 冲突点（角色意见不一致，附分析 + 折中方案）            │
│   - 各角色独立建议（可选择性采纳）                         │
│   - 信息架构/交互流程的重大调整建议                        │
│                                                         │
│   用户选择：采纳 / 否决 / 替代方案                         │
├─────────────────────────────────────────────────────────┤
│ Phase 5: FIX（执行修改）                                  │
│                                                         │
│   1. 按优先级执行采纳的修改                               │
│   2. 需要验证时用 evaluate_script 提取关键 computed styles│
│      或直接在浏览器肉眼确认（不保存截图到磁盘）            │
│   3. 如有信息架构调整，更新 spec 文档                     │
│   4. 如有新的设计决策，记录到 decisions/                   │
├─────────────────────────────────────────────────────────┤
│ Phase 6: POLISH（质量提升 + Art Director 审批）           │
│                                                         │
│   Step 1: Art Director 预审 FIX 结果                      │
│   ├─ 气质评分 ≥ 7.5 → 允许进入 POLISH                   │
│   └─ 气质评分 < 7.5 → 先修正气质问题，再进入 POLISH      │
│                                                         │
│   Step 2: 根据目标质量等级应用 impeccable skills：         │
│   - good:     normalize → arrange → clarify              │
│   - polished: + colorize → typeset → animate             │
│   - best:     + bolder → delight → overdrive             │
│                                                         │
│   Step 3: Art Director 复审 POLISH 结果                   │
│   ├─ 可降级过度的 bolder/delight/overdrive 效果          │
│   ├─ 可移除违反克制度的装饰元素                           │
│   ├─ 使用 impeccable: quieter 处理过度装饰                │
│   └─ 输出最终气质评分卡                                  │
├─────────────────────────────────────────────────────────┤
│ Phase 7: FINAL（最终验证 + 气质评分）                     │
│                                                         │
│   1. Chrome MCP: lighthouse_audit（质量评分）             │
│   2. Chrome MCP: evaluate_script（最终 Token 审计）       │
│   3. Art Director 最终气质评估：                          │
│      ├─ 重新提取视觉指纹，对比 Phase 1 基线               │
│      ├─ 输出气质评分卡（克制度/一致性/高级感/品牌方向）   │
│      └─ 跨页一致性验证（对比其他页面视觉指纹）            │
│   4. git commit 最终状态                                 │
│   5. 生成审查报告 → docs/reviews/（含 tag 引用）          │
│   6. 更新 design decisions（如有架构调整）                 │
│   7. 生成待同步清单（嵌入报告末尾）                       │
├─────────────────────────────────────────────────────────┤
│ Phase 8: SYNC（反向同步，独立触发）                       │
│                                                         │
│   触发: /ditto-design-review <file> --sync              │
│   前置: review report 存在且包含待同步清单                │
│                                                         │
│   1. 读取最新 review report 中的待同步清单               │
│   2. 按变更类型分组：                                    │
│      ├─ 修正型 → 逐条展示 diff，用户逐条确认             │
│      └─ 新增/补充型 → 批量展示，用户一次性确认           │
│   3. 执行文档更新：                                     │
│      ├─ 修正型 → 直接编辑 spec 正文                     │
│      ├─ 新增/补充型 → 追加到文档末尾 ## Changelog        │
│      └─ 新增 ADR → 生成文件到 docs/designs/decisions/   │
│   4. 验证文档内部引用一致性                              │
│   5. 产出同步摘要                                       │
└─────────────────────────────────────────────────────────┘
```

### 单角色审查

使用 `--ui` / `--ux` / `--product` / `--copy` / `--ad` 参数时，只运行对应角色的审查，跳过冲突协调和全流程。

```
BASELINE → 单角色审查 → 输出问题清单 → 用户决策 → FIX → VERIFY
```

### 仅精修模式

使用 `--polish` 参数时，跳过审查，直接按质量等级应用 impeccable skills。

```
BASELINE → POLISH → VERIFY → FINAL
```

---

## Agent 输出格式

每个审查角色的输出必须遵循以下结构：

```markdown
## [角色名] 审查报告

### P0 — 必须修复

#### [P0] UI-001: 主标题字号偏小

**现状**: `.hero h1` 字号为 24px，与 spec 定义的 `text-display-lg`（28px）不一致。
**影响**: 首屏视觉层次偏弱，标题不够突出。

**方案对比**:
| 方案 | 业界参考 | 优势 | 劣势 |
|------|---------|------|------|
| A: 改为 28px | Linear / Vercel | 与 spec 一致，视觉层次清晰 | 需调整下方内容间距 |
| B: 保持 24px | — | 不影响现有布局 | 与 spec 不符，跨页不一致 |

**推荐**: 方案 A，与 spec 对齐是最高优先级，间距可通过 grid 调整吸收。

#### [P0] ...

### P1 — 建议修复

#### [P1] UI-002: 卡片间距不统一

**现状**: `.card-grid` 的 gap 为 16px，但其他页面同类布局使用 20px。
**影响**: 跨页面视觉节奏不一致。

**方案对比**:
| 方案 | 业界参考 | 优势 | 劣势 |
|------|---------|------|------|
| A: gap → 20px | Raycast / shadcn | 与项目其他页面一致 | 略减少可显示卡片数 |
| B: 保持 16px | — | 信息密度更高 | 跨页不一致 |

**推荐**: 方案 A，一致性优先于单页信息密度。

#### [P1] ...

### P2 — 可选优化
| ID | 问题 | 位置 | 建议 | 理由 |
|----|------|------|------|------|

### 💡 设计建议（可能涉及信息架构/交互流程调整）
- 建议将"市场脉搏"从数据表格改为卡片式展示，理由是...
- 建议增加"快速操作"入口，理由是...
```

> **业界调研规则**: 仅 P0、P1 问题附带方案对比。通过 WebSearch 查找 2-3 个业界参考（如 Linear、Raycast、Bloomberg 等），形成轻量对比表格。P2 和纯建议不附带调研。

---

## 冲突协调格式

```markdown
## 冲突协调

### 🔀 冲突 1: 间距 vs 信息密度
- **UI Designer**: 增大卡片间距到 24px，提升呼吸感
- **Product Manager**: 保持 16px 间距，在有限空间展示更多数据
- **分析**: 当前页面面向专业交易用户，信息密度优先级高于呼吸感
- **推荐方案**: 保持 16px 间距，但增加卡片内部分区的视觉分隔（细线或背景色差）
- **用户决策**: [待选择]

### ✅ 共识点
- 所有人认为导航栏需要增加"快捷操作"入口
- 所有人认为空状态需要优化
```

---

## 最终报告模板

输出到 `docs/reviews/YYYY-MM-DD-product-review-{page}.md`

```markdown
# Product Review: {page}

**日期**: YYYY-MM-DD
**目标**: {file path}
**质量等级**: {functional | good | polished | best}
**审查角色**: UI / UX / Product / Copy / Art Director

## 版本信息
- **Tag**: review/round-{N}
- **变更查看**: `git diff review/round-{N-1}..review/round-{N}`

## Summary
- P0 问题: X 个（已修复 X 个）
- P1 问题: X 个（采纳 X 个）
- P2 建议: X 个（采纳 X 个）
- 设计决策变更: X 个
- Lighthouse 评分: {before} → {after}

## 气质评分卡（Art Director）

| 维度 | 评分 | 说明 |
|------|------|------|
| 克制度 | X.X/10 | {高亮描边密度、视觉元素层级数是否在阈值内} |
| 一致性 | X.X/10 | {跨页视觉语言是否统一，有无方言分裂} |
| 高级感 | X.X/10 | {整体气质偏向 Bloomberg/quant desk 的程度} |
| 品牌方向 | X.X/10 | {是否符合 Graphite Studio 审美方向} |
| **综合气质** | **X.X/10** | |

**视觉指纹对比**（Phase 1 基线 → Phase 7 最终）:
| 指标 | 基线 | 最终 | 变化 |
|------|------|------|------|
| 高亮描边密度 | X | X | +/-X |
| 强调色面积比 | X% | X% | +/-X% |
| 视觉元素层级数 | X | X | +/-X |
| 留白节奏比 | X% | X% | +/-X% |
| 色彩种类数 | X | X | +/-X |

**Art Director 裁决记录**:
- {描述降级/移除的 polish 变更及理由}

## Key Decisions
- 决策 1: {描述} → {最终方案} → 理由
- 决策 2: ...

## Changes Made
- [UI-001] 修改了...
- [UX-003] 调整了...

## Updated Specs
- {spec file}: {变更描述}

## 待同步清单

> 以下变更已通过验收，可使用 `/ditto-design-review {file} --sync` 同步到设计文档。

### {spec 文档路径}
| # | 变更类型 | 描述 | 来源 |
|---|---------|------|------|
| 1 | 修正/新增/补充 | {变更描述} | {P0/P1 ID 或 Conflict ID} |

### docs/designs/decisions/
| # | 变更类型 | 描述 | 来源 |
|---|---------|------|------|
| 1 | 新增 | ADR: {决策标题} | {来源} |

## Screenshots
- 无自动截图（需要时在浏览器手动截取）
```

---

## 使用示例

```bash
# 审查跨市场概览页面（全流程，polished 等级）
# 自动 git tag review/round-{N}，修改直接在原文件上进行
/ditto-design-review page-cross-market.html

# 审查首页，只看 UI 和 UX
/ditto-design-review page-home.html --ui --ux

# 仅气质审查（高级感/一致性/品牌方向）
/ditto-design-review page-cross-market.html --ad

# 对当前页面做精修（跳过审查）
/ditto-design-review page-trading.html --polish

# 以业界最佳标准审查
/ditto-design-review page-research.html --level best

# 回退到 round-2
git checkout review/round-2 -- page-cross-market.html

# 对比 round-1 和 round-2 的差异
git diff review/round-1..review/round-2 -- page-cross-market.html

# 验收后，将 review 变更同步回设计文档
/ditto-design-review page-cross-market.html --sync
```

---

## Phase 8: SYNC（反向同步设计文档）

> 将 review 过程中确认采纳的变更写回设计文档，保持 spec 与实现/决策的一致性。

### 触发

```bash
/ditto-design-review <file> --sync
```

### 前置条件

- 对应的 review report 存在于 `docs/reviews/`
- report 中包含「待同步清单」章节
- 如果没有，提示用户先完成一次 review 流程

### 执行流程

```
1. 定位最新的 review report（按文件名日期排序）
2. 提取「待同步清单」中的所有条目
3. 按变更类型分组处理：

   ┌─ 修正型（改正文）────────────────────────┐
   │ 逐条展示 diff 预览                        │
   │ 用户逐条确认（AskUserQuestion）            │
   │ 确认后直接 Edit 目标文档正文               │
   └──────────────────────────────────────────┘

   ┌─ 新增/补充型（写 changelog）──────────────┐
   │ 批量展示所有 changelog 条目               │
   │ 用户一次性确认（AskUserQuestion）          │
   │ 确认后追加到目标文档末尾 ## Changelog      │
   └──────────────────────────────────────────┘

   ┌─ 新增 ADR ───────────────────────────────┐
   │ 展示 ADR 内容预览                        │
   │ 用户确认后生成独立文件                     │
   │ → docs/designs/decisions/YYYY-MM-DD-<topic>.md │
   └──────────────────────────────────────────┘

4. 验证：检查文档内部引用一致性
   - 如 01_ia 中的页面是否在 02_blueprints 中有对应
   - 组件规范变更是否与 14_token_spec 冲突
5. 产出同步摘要
```

### 混合模式更新规则

| 变更类型 | 更新方式 | 确认方式 |
|---------|---------|---------|
| **修正** | 直接编辑 spec 正文，修正错误值/描述 | 逐条展示 diff + 确认 |
| **新增** | 追加到文档末尾 `## Changelog` | 批量展示 + 一次性确认 |
| **补充** | 追加到文档末尾 `## Changelog` | 批量展示 + 一次性确认 |
| **新增 ADR** | 生成独立文件到 `docs/designs/decisions/` | 展示内容 + 确认 |

### Changelog 格式

追加到目标 spec 文档末尾（如文档尚无 Changelog 章节，创建之）：

```markdown
## Changelog

### 2026-03-29 — Product Review: page-cross-market

- **[修正]** Home Banner 优先事项配比从 3:2:1 改为 4:2:1（来源: P0-UI-03）
- **[新增]** StatCard 组件新增紧凑模式：宽 120px，字号 12px，仅显示主指标（来源: P1-UX-02）
- **[补充]** StatCard 空状态规则：无数据时显示「暂无数据」+ 灰色占位图形（来源: P1-Product-01）
```

### ADR 生成格式

当待同步清单中目标目录为 `docs/designs/decisions/` 的「新增」条目，生成独立 ADR 文件：

```markdown
# {决策标题}

**日期**: YYYY-MM-DD
**来源**: Product Review — {page}（{P0/P1 ID 或 Conflict ID}）
**状态**: 已采纳

## 背景

{为什么需要这个决策，review 中发现了什么问题}

## 决策

{最终采纳的方案}

## 理由

{为什么选择这个方案，基于什么调研或分析}

## 影响

- {受影响的 spec 文档列表}
- {受影响的组件/页面}
```

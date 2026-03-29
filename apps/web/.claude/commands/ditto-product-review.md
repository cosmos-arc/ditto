---
name: ditto-product-review
description: 多角色产品级审查编排 — UI 设计 / UX 交互 / 产品功能 / 界面语言多维度审查，协商优化达成一致
---

# /ditto-product-review

多角色产品级审查编排 Skill。从设计原型到最终交付，通过 UI / UX / 产品 / 文案四角色并行审查，识别冲突与共识，协商优化达成一致。

## 规范参考

- **设计规范**: [docs/designs/specs/](../../docs/designs/specs/)（参考起点，非刚性约束）
- **Design Token**: [docs/designs/specs/prototypes/shared/tokens-base.css](../../docs/designs/specs/prototypes/shared/tokens-base.css) 及其 6 层体系
- **设计决策**: [docs/designs/decisions/](../../docs/designs/decisions/)
- **架构规范**: [architecture.md](../rules/architecture.md)

## 输入

`$ARGUMENTS` — 审查目标 + 可选参数

```bash
# 全流程审查
/ditto-product-review docs/designs/specs/prototypes/style-b-graphite-studio/page-cross-market.html

# 指定质量等级（默认 polished）
/ditto-product-review page-cross-market.html --level best

# 仅运行特定角色
/ditto-product-review page-cross-market.html --ui
/ditto-product-review page-cross-market.html --ux
/ditto-product-review page-cross-market.html --product
/ditto-product-review page-cross-market.html --copy

# 仅精修（跳过审查，直接应用 impeccable skills）
/ditto-product-review page-cross-market.html --polish

# 指定审查基准（对照某个原型版本）
/ditto-product-review page-cross-market.html --baseline prototype-v2.html
```

## 原型版本管理

> **每次 review 前，必须快照当前版本。修改在新版本上进行，老版本保留可回退和对比。**

### 版本目录结构

```
docs/designs/specs/prototypes/style-b-graphite-studio/
├── page-cross-market.html              # 当前活跃版本（总是最新）
├── prototype-compact.html
├── ...
└── .versions/                          # 版本快照（.gitignore 不忽略）
    ├── page-cross-market/
    │   ├── v1.html                     # 初始版本
    │   ├── v1.png                      # 截图
    │   ├── v1.md                       # 版本说明
    │   ├── v2.html                     # 第二轮 review 后
    │   ├── v2.png
    │   ├── v2.md
    │   └── CHANGELOG.md                # 该页面的版本变更记录
    └── prototype-compact/
        ├── v1.html
        ├── v1.png
        ├── v1.md
        └── CHANGELOG.md
```

### 版本号规则

- **v1**: 原始创建的版本（首次 review 前）
- **v2, v3, ...**: 每次 `/ditto-product-review` 完成后递增
- 版本号是**全局递增**的（不按质量等级分段）

### 自动版本管理流程

```
Phase 0: VERSION（在所有审查之前）

  1. 确定目标文件名（如 page-cross-market.html）
  2. 确定 .versions/ 下的子目录（如 page-cross-market/）
  3. 检查当前最高版本号（如已有 v1, v2 → 下一个是 v3）
  4. 复制当前文件为快照：
     cp page-cross-market.html .versions/page-cross-market/v3.html
  5. Chrome MCP: take_screenshot → 保存为 v3.png
  6. 生成版本说明 v3.md：
     ```
     # page-cross-market v3
     - **日期**: YYYY-MM-DD
     - **触发**: /ditto-product-review
     - **质量等级**: polished
     - **说明**: review 前快照，保留当前状态
     ```
  7. 后续所有修改在 page-cross-market.html（活跃版本）上进行
```

### 回退操作

```bash
# 回退到 v2
/ditto-product-review page-cross-market.html --rollback v2

# 会执行：
# 1. cp .versions/page-cross-market/v2.html page-cross-market.html（覆盖活跃版本）
# 2. 提示用户确认
# 3. 在 CHANGELOG.md 中记录回退操作
```

### 版本对比

```bash
# 对比两个版本的截图差异
/ditto-product-review page-cross-market.html --diff v2..v3

# 会执行：
# 1. 并排展示 v2.png 和 v3.png
# 2. 列出两个版本之间的具体变更
# 3. 读取 v2.md 和 v3.md 中的说明
```

### CHANGELOG.md 格式

```markdown
# page-cross-market 版本记录

| 版本 | 日期 | 触发 | 变更摘要 |
|------|------|------|---------|
| v3 | 2026-03-29 | /ditto-product-review polished | 优化间距节奏，增加 Hero Banner 动画 |
| v2 | 2026-03-28 | /ditto-product-review good | 修复 Token 一致性问题，调整信息层级 |
| v1 | 2026-03-27 | 初始创建 | 初始原型 |

## 回退记录
| 日期 | 从 | 到 | 原因 |
|------|----|----|------|
| 2026-03-29 | v3 | v2 | 动画效果不符合预期 |
```

### 约束

- `.versions/` 目录下的文件**不可删除**（保留完整历史）
- 活跃版本文件（如 `page-cross-market.html`）是唯一被 review 修改的文件
- 每次review结束时，在活跃版本上继续工作，不创建新快照（新快照在**下次** review 开始时创建）
- 如果用户手动修改了原型文件但没有经过 review，版本号不变

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

## 四个审查角色

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
│ Phase 0: VERSION（版本快照）                              │
│                                                         │
│   1. 确定目标文件名和版本目录                              │
│   2. 检查当前最高版本号                                   │
│   3. 复制当前文件为版本快照（.versions/{page}/v{n}.html） │
│   4. Chrome MCP: take_screenshot → 保存 v{n}.png         │
│   5. 生成版本说明 v{n}.md                                │
│   6. 后续所有修改在活跃版本上进行                         │
├─────────────────────────────────────────────────────────┤
│ Phase 1: BASELINE（基线采集）                             │
│                                                         │
│   1. 读取目标文件（HTML 原型或 React 组件）               │
│   2. 读取相关 spec 文档（作为参考）                        │
│   3. 读取 Design Token 定义                              │
│   4. Chrome MCP: take_screenshot（当前状态截图）           │
│   5. Chrome MCP: evaluate_script（提取关键元素 styles）    │
├─────────────────────────────────────────────────────────┤
│ Phase 2: PARALLEL REVIEW（并行审查）                      │
│                                                         │
│   启动 4 个并行 Agent，每个扮演一个角色：                   │
│   ├─ UI Designer Agent   → 输出: UI 问题清单              │
│   ├─ UX Reviewer Agent   → 输出: UX 问题清单              │
│   ├─ Product Mgr Agent   → 输出: 产品问题清单             │
│   └─ Copy Editor Agent   → 输出: 文案问题清单             │
│                                                         │
│   每个角色的输出格式：                                    │
│   - 🔴 P0: 必须修复（阻断性问题）                         │
│   - 🟡 P1: 建议修复（影响体验）                           │
│   - 🟢 P2: 可选优化（锦上添花）                           │
│   - 💡 建议：对设计/信息架构的调整建议                     │
├─────────────────────────────────────────────────────────┤
│ Phase 3: CONFLICT RESOLUTION（冲突协调）                  │
│                                                         │
│   1. 汇总 4 个角色的问题清单                              │
│   2. 去重合并相似问题                                     │
│   3. 识别角色间的冲突点                                   │
│   4. 为每个冲突提供分析 + 折中方案                        │
│   5. 识别所有角色的共识点                                 │
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
│   2. 每次修改后 Chrome MCP 截图验证                       │
│   3. 如有信息架构调整，更新 spec 文档                     │
│   4. 如有新的设计决策，记录到 decisions/                   │
├─────────────────────────────────────────────────────────┤
│ Phase 6: POLISH（质量提升）                               │
│                                                         │
│   根据目标质量等级应用 impeccable skills：                 │
│   - good:     normalize → arrange → clarify              │
│   - polished: + colorize → typeset → animate             │
│   - best:     + bolder → delight → overdrive             │
├─────────────────────────────────────────────────────────┤
│ Phase 7: FINAL（最终验证 + 版本记录）                     │
│                                                         │
│   1. Chrome MCP: take_screenshot（最终截图）              │
│   2. Chrome MCP: lighthouse_audit（质量评分）             │
│   3. Chrome MCP: evaluate_script（最终 Token 审计）       │
│   4. 更新 .versions/{page}/CHANGELOG.md（记录本次变更）   │
│   5. 生成审查报告 → docs/reviews/                        │
│   6. 更新 design decisions（如有架构调整）                 │
│   7. 输出版本摘要（v{n} 快照 → 活跃版本已更新）          │
└─────────────────────────────────────────────────────────┘
```

### 单角色审查

使用 `--ui` / `--ux` / `--product` / `--copy` 参数时，只运行对应角色的审查，跳过冲突协调和全流程。

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
| ID | 问题 | 位置 | 建议 | 理由 |
|----|------|------|------|------|
| UI-001 | 主标题字号偏小 | .hero h1 | 从 24px → 28px | 与 spec 定义 text-display-lg 不符 |

### P1 — 建议修复
| ID | 问题 | 位置 | 建议 | 理由 |
|----|------|------|------|------|
| UI-002 | 卡片间距不统一 | .card-grid | gap 从 16px → 20px | 与其他页面保持一致 |

### P2 — 可选优化
| ID | 问题 | 位置 | 建议 | 理由 |
|----|------|------|------|------|

### 💡 设计建议（可能涉及信息架构/交互流程调整）
- 建议将"市场脉搏"从数据表格改为卡片式展示，理由是...
- 建议增加"快速操作"入口，理由是...
```

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
**审查角色**: UI / UX / Product / Copy

## 版本信息
- **Review 前快照**: .versions/{page}/v{n}.html + v{n}.png
- **Review 后状态**: 活跃版本已更新（下次 review 将快照为 v{n+1}）
- **版本变更**: v{n} → 活跃版本

## Summary
- P0 问题: X 个（已修复 X 个）
- P1 问题: X 个（采纳 X 个）
- P2 建议: X 个（采纳 X 个）
- 设计决策变更: X 个
- Lighthouse 评分: {before} → {after}

## Key Decisions
- 决策 1: {描述} → {最终方案} → 理由
- 决策 2: ...

## Changes Made
- [UI-001] 修改了...
- [UX-003] 调整了...

## Updated Specs
- {spec file}: {变更描述}

## Screenshots
- Before: {screenshot path}
- After: {screenshot path}
```

---

## 使用示例

```bash
# 审查跨市场概览页面（全流程，polished 等级）
# 自动快照当前版本为 v1，修改在活跃版本上进行
/ditto-product-review page-cross-market.html

# 审查首页，只看 UI 和 UX
/ditto-product-review page-home.html --ui --ux

# 对当前页面做精修（跳过审查）
/ditto-product-review page-trading.html --polish

# 以业界最佳标准审查
/ditto-product-review page-research.html --level best

# 回退到 v2
/ditto-product-review page-cross-market.html --rollback v2

# 对比 v2 和 v3 的差异
/ditto-product-review page-cross-market.html --diff v2..v3
```

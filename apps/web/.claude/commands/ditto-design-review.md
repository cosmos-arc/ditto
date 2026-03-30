---
name: ditto-design-review
description: Use when reviewing HTML prototypes or UI pages for visual quality, UX interaction, feature completeness, copy clarity, or brand temperament. Supports 5-role parallel review, autonomous iteration, and doc sync.
disable-model-invocation: true
---

# /ditto-design-review

多角色设计审查编排。聚焦设计交付物质量——UI 视觉、交互体验、功能可用性、界面语言、品牌气质、**信息效率**，通过五角色并行审查识别冲突与共识，协商优化达成一致。支持 `--iterate` 自主迭代模式，设定评分目标后自动循环优化直到达标。

> **审查标准必须与产品定位匹配**，不使用通用 UI 准则。详见 [product-criteria.md](../design-review/product-criteria.md)。
> 评分从 4 维度扩展为 5 维度（克制度/一致性/高级感/品牌方向/**信息效率**）。

## 核心理念

> **不是"对照 spec 打分"，而是"多角色专家讨论，共同优化设计"。**

- Design Spec 是**参考起点**，不是刚性约束
- 各角色可能给出**相互冲突的建议**（如 UI 想加大间距 vs 产品想增加信息密度）
- Claude 负责呈现冲突 + 分析权衡 + 推荐折中方案
- **用户是最终决策者**，选择采纳哪些建议
- 审查可能产生**新的设计决策**，自动记录到 `docs/designs/decisions/`
- 如果信息架构或交互流程有重大调整，同步更新 spec 文档

---

## 规范参考

- **设计规范**: [docs/designs/specs/](../../docs/designs/specs/)（参考起点，非刚性约束）
- **Design Token**: [docs/designs/specs/prototypes/shared/tokens-base.css](../../docs/designs/specs/prototypes/shared/tokens-base.css) 及其 9 层体系
- **设计决策**: [docs/designs/decisions/](../../docs/designs/decisions/)（**Art Director 刚性锚点** — 9 项关键决策定义了 Graphite Studio 的审美方向）
- **品牌 DNA**: Style B Graphite Studio — Linear/Vercel/Raycast 的克制感 + Bloomberg/quant desk 的专业终端感
- **架构规范**: [architecture.md](../rules/architecture.md)

---

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

# 自主迭代优化（目标气质 8.5，最多 3 轮，无需人工介入）
/ditto-design-review page-cross-market.html --iterate --goal 8.5 --max-rounds 3

# 自主迭代优化（使用默认值：目标 8.0，最多 3 轮）
/ditto-design-review page-cross-market.html --iterate
```

---

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

## 多视口检测

> **所有涉及 HTML 原型的 review 必须在目标视口下验证内容完整性。** 默认审查视口 VP-STANDARD (1536x1080)，最小支持 VP-COMPACT (1366x768)。
>
> 详细视口矩阵、检测脚本、UX P0 规则见 [viewport.md](../design-review/viewport.md)。

---

## 五个审查角色

| 角色 | model | 核心关注 | 详情 |
|------|-------|---------|------|
| UI Designer | opus | Token 一致性、视觉层次、色彩排版 | [roles.md](../design-review/roles.md#ui-designer) |
| UX Reviewer | sonnet | 可用性、可访问性、交互流程 | [roles.md](../design-review/roles.md#ux-reviewer) |
| Product Mgr | sonnet | 功能完整性、用户场景、信息密度 | [roles.md](../design-review/roles.md#product-manager) |
| Copy Editor | sonnet | 文案清晰度、语气一致、中文表达 | [roles.md](../design-review/roles.md#copy-editor) |
| Art Director | opus | 克制度、高级感、品牌方向锚定 | [roles.md](../design-review/roles.md#art-director) |

---

## 模型路由策略

> **质量优先**：审美判断和创意综合使用 Opus，结构化分析和机械操作使用 Sonnet。

| 阶段 | 模型 | 理由 |
|------|------|------|
| Phase 0: VERSION | sonnet | git 操作，纯机械 |
| Phase 1: BASELINE | sonnet | 数据采集 + 脚本执行 |
| Phase 2: CREATIVE DIRECTION | **opus** | 创意方向判断，策略选择和蓝图定义 |
| Phase 3: Art Director | **opus** | 审美判断核心，气质评分 |
| Phase 3: UI Designer | **opus** | 视觉品质需要审美理解 |
| Phase 3: UX Reviewer | sonnet | 交互分析偏结构化 |
| Phase 3: Product Mgr | sonnet | 功能可用性偏结构化 |
| Phase 3: Copy Editor | sonnet | 文案审查最结构化 |
| Phase 4: CONFLICT RES. | **opus** | 多角色冲突权衡取舍 |
| Phase 5: DECISION | sonnet | 呈现选项，不涉及判断 |
| Phase 6: FIX | sonnet | 按已定方案执行 |
| Phase 7: AD 预审/复审 | **opus** | 审美把关 |
| Phase 7: impeccable skills | sonnet | 按规范执行 |
| Phase 7: REFLECT [--iterate] | **opus** | 定性反思，洞察提取 |
| Phase 8: 自动化检测 | sonnet | Lighthouse/Token/视口 |
| Phase 8: 最终气质评分 | **opus** | 最终审美裁决 |
| Phase 9: SYNC | sonnet | 文档同步 |

**实现方式**：Agent 工具调用时传入 `model` 参数，如 `Agent(prompt="...", model="opus")`。

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

## 自主迭代模式（`--iterate`）

> 自动循环**创意方向→审查→修复→评分→反思**，直到达标或达到上限。参数：`--goal`（默认 8.0）、`--max-rounds`（默认 3）。
> 每轮开始前 Art Director 定义创意蓝图（CREATIVE DIRECTION），每轮结束后输出结构化反思（REFLECT）。
> 循环架构、退出条件、AUTO-DECISION 规则、防震荡机制、**突破机制**详见 [iterate.md](../design-review/iterate.md)。
> **创意流程借鉴**：CREATIVE DIRECTION 从 [CREA 框架](https://crea-diffusion.github.io/)借鉴、REFLECT 从 [Reflexion 模式](https://arxiv.org/abs/2303.11366)借鉴、常态化标杆调研从 Design Harness 的 [Inspiration 层](https://agenticux.substack.com/p/between-uicrit-and-autoresearch-what)借鉴。

> **突破机制**: 当连续多轮收益递减（diminishing returns）时，不直接退出，而是触发「瓶颈诊断 → 策略转向 → 标杆调研 → 突破执行」流程。核心原则：**分数卡住的根源往往是优化维度本身已耗尽，需要换一个维度思考**。详见 [iterate.md §突破机制](../design-review/iterate.md#突破机制breakthrough-protocol)。

---

## 执行流程

### 全流程（默认，人工模式）

```
┌─────────────────────────────────────────────────────────┐
│ Phase 0: VERSION（git tag 快照）                    [sonnet] │
│                                                         │
│   1. 检查已有 tag（review/round-*）确定轮次号              │
│   2. git add 目标文件 → git commit                      │
│   3. git tag review/round-{N}                           │
│   4. 后续修改直接在原文件上进行                           │
├─────────────────────────────────────────────────────────┤
│ Phase 1: BASELINE（基线采集 + 跨页视觉指纹）        [sonnet] │
│                                                         │
│   1. 读取目标文件（HTML 原型或 React 组件）               │
│   2. 读取相关 spec 文档（作为参考）                        │
│   3. 读取 Design Token 定义                              │
│   4. 读取设计决策文档（Art Director 刚性锚点）            │
│   5. Chrome MCP: emulate(VP-STANDARD 1536x1080)          │
│   6. Chrome MCP: evaluate_script（提取关键元素 styles）    │
│   7. [多视口] VP-STANDARD 内容溢出检测（详见 viewport.md） │
│   8. [多视口] VP-COMPACT (1366x768) 抽检                 │
│   9. [多视口] 恢复 VP-STANDARD，记录基线视口报告          │
│  10. [跨页] 视觉指纹采集：                                │
│      ├─ evaluate_script 提取各页面的视觉指纹：             │
│      │   高亮描边密度 / 强调色面积比 / 视觉元素层级数     │
│      │   留白节奏比 / 色彩种类数                          │
│      └─ 生成「跨页一致性基线」                            │
├─────────────────────────────────────────────────────────┤
│ Phase 2: CREATIVE DIRECTION（创意蓝图）              [opus]  │
│                                                         │
│   1. 读取前轮评分快照和反思记录（首轮跳过）              │
│   2. 识别当前最低分维度和天花板维度                     │
│   3. 从策略矩阵选择本轮创意策略                        │
│   4. 轻量标杆调研（WebSearch 1-2 个参考）              │
│   5. 输出本轮创意蓝图（策略/区域/参考/预期/约束）      │
├─────────────────────────────────────────────────────────┤
│ Phase 3: PARALLEL REVIEW（并行审查）                      │
│                                                         │
│   启动 5 个并行 Agent，每个扮演一个角色：                   │
│   ├─ Art Director Agent  → opus  → 气质问题清单 + 评分卡 │
│   ├─ UI Designer Agent   → opus  → UI 问题清单           │
│   ├─ UX Reviewer Agent   → sonnet → UX 问题清单          │
│   ├─ Product Mgr Agent   → sonnet → 产品问题清单         │
│   └─ Copy Editor Agent   → sonnet → 文案问题清单         │
│                                                         │
│   每个角色的输出格式：                                    │
│   - 🔴 P0: 必须修复（阻断性问题）                         │
│   - 🟡 P1: 建议修复（影响体验）                           │
│   - 🟢 P2: 可选优化（锦上添花）                           │
│   - 💡 建议：对设计/信息架构的调整建议                     │
├─────────────────────────────────────────────────────────┤
│ Phase 4: CONFLICT RESOLUTION（冲突协调）            [opus]  │
│                                                         │
│   1. 汇总 5 个角色的问题清单                              │
│   2. 去重合并相似问题                                     │
│   3. 识别角色间的冲突点                                   │
│   4. 为每个冲突提供分析 + 折中方案                        │
│   5. 识别所有角色的共识点                                 │
│   6. [--iterate] Art Director 为每个 P1 标注「预期提分」  │
│      用于后续 AUTO-DECISION 阶段的优先级排序              │
│   7. [--iterate] 标注每个变更与创意蓝图的方向对齐度      │
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
│ Phase 5: DECISION（用户决策 / AUTO-DECISION）      [sonnet] │
│                                                         │
│   使用 AskUserQuestion 呈现：                             │
│   - 共识点（所有角色一致认同，建议直接采纳）               │
│   - 冲突点（角色意见不一致，附分析 + 折中方案）            │
│   - 各角色独立建议（可选择性采纳）                         │
│   - 信息架构/交互流程的重大调整建议                        │
│                                                         │
│   [--iterate] AUTO-DECISION 自动裁决，不阻塞用户          │
│   [--人工] 用户选择：采纳 / 否决 / 替代方案               │
├─────────────────────────────────────────────────────────┤
│ Phase 6: FIX（执行修改）                            [sonnet] │
│                                                         │
│   1. 按优先级执行采纳的修改                               │
│   2. 需要验证时用 evaluate_script 提取关键 computed styles│
│      或直接在浏览器肉眼确认（不保存截图到磁盘）            │
│   3. 如有信息架构调整，更新 spec 文档                     │
│   4. 如有新的设计决策，记录到 decisions/                   │
├─────────────────────────────────────────────────────────┤
│ Phase 7: POLISH（质量提升 + Art Director 审批）     [混合]   │
│                                                         │
│   Step 1: Art Director 预审 FIX 结果              [opus]  │
│   ├─ 气质评分 ≥ 7.5 → 允许进入 POLISH                   │
│   └─ 气质评分 < 7.5 → 先修正气质问题，再进入 POLISH      │
│                                                         │
│   Step 2: 应用 impeccable skills                  [sonnet] │
│   - good:     normalize → arrange → clarify              │
│   - polished: + colorize → typeset → animate             │
│   - best:     + bolder → delight → overdrive             │
│                                                         │
│   Step 3: Art Director 复审 POLISH 结果           [opus]  │
│   ├─ 可降级过度的 bolder/delight/overdrive 效果          │
│   ├─ 可移除违反克制度的装饰元素                           │
│   ├─ 使用 impeccable: quieter 处理过度装饰                │
│   └─ 输出气质评分卡                                     │
│                                                         │
│   [--iterate] Step 4: REFLECT 反思记录            [opus]  │
│   ├─ 记录本轮创意策略与实际执行的偏差                    │
│   ├─ 记录关键洞察（什么起作用/什么没起作用）             │
│   └─ 标记死胡同 + 可探索方向                            │
├─────────────────────────────────────────────────────────┤
│ Phase 8: FINAL（最终验证 + 气质评分）               [混合]   │
│                                                         │
│   1. Chrome MCP: lighthouse_audit（质量评分）    [sonnet] │
│   2. Chrome MCP: evaluate_script（最终 Token 审计）[sonnet]│
│   3. [多视口] VP-STANDARD 完整性验证              [sonnet] │
│      ├─ 内容无截断，底部元素完全可见                     │
│      └─ sticky 元素（rail/header/context-bar）正常工作    │
│   4. [多视口] VP-COMPACT (1366x768) 完整性验证   [sonnet] │
│      ├─ 可滚动到底部，底部内容完全可见                   │
│      └─ 布局无破坏                                       │
│   5. [多视口] 输出视口验证报告                   [sonnet] │
│   6. Art Director 最终气质评估：                   [opus]  │
│      ├─ 重新提取视觉指纹，对比 Phase 1 基线               │
│      ├─ 输出气质评分卡（克制度/一致性/高级感/品牌方向/信息效率）│
│      └─ 跨页一致性验证（对比其他页面视觉指纹）            │
│  11. [--iterate] 汇总所有轮次反思记录到最终报告          │
│   7. git commit 最终状态                                 │
│   8. 生成审查报告 → docs/reviews/（含 tag 引用）          │
│   9. 更新 design decisions（如有架构调整）                 │
│  10. 生成待同步清单（嵌入报告末尾）                       │
├─────────────────────────────────────────────────────────┤
│ Phase 9: SYNC（反向同步，独立触发）                 [sonnet] │
│                                                         │
│   触发: /ditto-design-review <file> --sync              │
│   详情见 [sync.md](../design-review/sync.md)             │
└─────────────────────────────────────────────────────────┘
```

### 单角色审查

使用 `--ui` / `--ux` / `--product` / `--copy` / `--ad` 参数时，只运行对应角色的审查，跳过冲突协调和全流程。

```
BASELINE [sonnet] → 单角色审查 [按角色分配] → DECISION [sonnet] → FIX [sonnet] → VERIFY [sonnet]
```

**单角色模型分配：**
| 参数 | 角色 | model | 理由 |
|------|------|-------|------|
| `--ui` | UI Designer | opus | 视觉品质需要审美判断 |
| `--ux` | UX Reviewer | sonnet | 交互分析偏结构化 |
| `--product` | Product Mgr | sonnet | 功能可用性偏结构化 |
| `--copy` | Copy Editor | sonnet | 文案审查最结构化 |
| `--ad` | Art Director | opus | 审美判断核心 |

### 仅精修模式

使用 `--polish` 参数时，跳过审查，直接按质量等级应用 impeccable skills。

```
BASELINE [sonnet] → POLISH [混合] → VERIFY [sonnet] → FINAL [混合]
```

---

## 输出模板

> Agent 输出格式、冲突协调格式、最终报告模板见 [templates.md](../design-review/templates.md)。

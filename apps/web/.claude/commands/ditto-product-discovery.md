---
name: ditto-product-discovery
description: 结构化产品发现——5 Phase LLM 深度提问，从模糊想法到 Product Brief + Research Repository。填补"idea → spec"缺口。
disable-model-invocation: true
---

# /ditto-product-discovery

结构化产品发现命令。通过 LLM 深度提问引导用户从模糊想法到完整的 **Product Brief + Research Repository**，填补"idea → spec"之间的缺口。

> **定位**：Pipeline -1——所有新功能/新页面的产品定义应先经过此 skill。
> **下游衔接**：`/ditto-product-arch --create` 消费 Brief + Research → 产出 spec。

---

## 核心理念

> **不是"替用户写 PRD"，而是"通过结构化提问帮助用户自己想清楚"。**

- 一问一答，每轮只问一个问题，多选优先
- AI 辅助调研但不替代判断——调研结论由用户确认
- 渐进聚焦：宏观（定位/用户）→ 中观（竞品/系统）→ 微观（约束/细节）
- 可中断可续接：每 Phase 独立 checkpoint + git commit
- 产出物是结构化文档，不是代码

## 与 /brainstorming 的区别

| 维度 | /brainstorming | /ditto-product-discovery |
|------|---------------|------------------------|
| 目标 | 创意发散/方案探索 | 产品发现/定义落盘 |
| 结构 | 自由对话 | 5 Phase 确定性引导 |
| 产出 | 对话记录 | Brief + Research artifact |
| 提问策略 | 开放式 | Zachman 六维度确定性提问 |
| 下游 | 无固定衔接 | → /ditto-product-arch → spec |

---

## 输入

`$ARGUMENTS` — 命令 + 可选参数

```bash
# 全流程 5 Phase 发现
/ditto-product-discovery
/ditto-product-discovery "A 股多因子策略回测平台"

# 从指定 Phase 恢复/重跑
/ditto-product-discovery --phase 2
/ditto-product-discovery --phase 3 "只跑系统描述"

# 只跑完整性检查
/ditto-product-discovery --validate

# 下游 spec 变更，反向更新 Brief/Research
/ditto-product-discovery --sync

# 从现有 spec 反推生成 Brief+Research（补救路径）
/ditto-product-discovery --from-existing
```

---

## 产出物结构

```
docs/brief/
├── product-brief.md          # Product Brief（Vision + System + Constraints 合并文档）
├── constitution.md           # 非谈判约束（≤ 1 页条目式）
└── system-description.md     # Zachman 六维度系统描述（YAML frontmatter + Markdown）

docs/research/
├── competitive/
│   └── landscape.md          # 竞品分析
└── domain/
    └── knowledge-gaps.md     # 领域知识缺口 + 数据源约束

.discovery-manifest.json      # Phase 进度追踪（项目根目录）
```

---

## 执行流程

### 全流程（默认）

```
┌─────────────────────────────────────────────────────────┐
│ Phase 0: INIT（初始化）                           [sonnet] │
│                                                         │
│   1. 检查 .discovery-manifest.json 是否存在             │
│      ├─ 存在 → 读取进度，确定恢复点                     │
│      │   ├─ 有 --phase N → 从 Phase N 恢复              │
│      │   ├─ 全部完成 → 提示已结束，建议 --validate       │
│      │   └─ 部分完成 → 从下一个未完成 Phase 继续         │
│      └─ 不存在 → 初始化 manifest，从 Phase 1 开始       │
│   2. 解析 $ARGUMENTS 中的主题描述（如有）                │
│   3. 创建 docs/brief/ 和 docs/research/ 目录结构         │
│   4. git init commit（如有新文件）                      │
├─────────────────────────────────────────────────────────┤
│ Phase 1: VISION（产品身份定义）                    [opus]  │
│                                                         │
│   回答"我们是谁、为谁、解决什么问题"                      │
│   ──────────────────────────────────────────             │
│                                                         │
│   提问策略：5 个核心问题，逐个推进                       │
│                                                         │
│   Q1. 产品定位                                           │
│   "这个产品的核心定位是什么？"                            │
│   选项示例：                                             │
│   ├─ 面向专业用户的效率工具                               │
│   ├─ 面向大众的消费品                                    │
│   ├─ 企业内部 B2B 工具                                  │
│   └─ 开发者工具/平台                                     │
│                                                         │
│   Q2. 目标用户                                           │
│   "主要服务哪类用户？他们的核心特征是什么？"               │
│   （基于 Q1 回答追问具体画像）                            │
│                                                         │
│   Q3. 核心痛点                                           │
│   "目标用户目前最大的痛点是什么？他们现在怎么解决的？"     │
│   （引导用户描述现状和不满）                              │
│                                                         │
│   Q4. 差异化价值                                         │
│   "市面上已有的解决方案有哪些不足？我们凭什么更好？"       │
│   （引导用户思考竞争壁垒）                                │
│                                                         │
│   Q5. 成功标准                                           │
│   "如果这个产品成功了，会用什么指标衡量？"                 │
│   选项示例：                                             │
│   ├─ 效率指标（速度/自动化率）                            │
│   ├─ 决策质量（准确率/收益率）                            │
│   ├─ 用户留存（DAU/留存率）                              │
│   └─ 其他（请描述）                                      │
│                                                         │
│   产出：写入 docs/brief/product-brief.md Vision 章节     │
│   更新：.discovery-manifest.json phase1.status = "done"  │
│   检查点：git commit                                     │
├─────────────────────────────────────────────────────────┤
│ Phase 2: LANDSCAPE（竞品与领域调研）               [混合]  │
│                                                         │
│   AI 先 WebSearch 调研，再基于结果提问                    │
│   ──────────────────────────────────────────             │
│                                                         │
│   Step 1: AI 自动调研                              [sonnet] │
│   ├─ 基于 Phase 1 的定位关键词进行 WebSearch              │
│   ├─ 搜索维度：                                           │
│   │   ├─ 竞品产品（直接竞品 + 间接竞品）                  │
│   │   ├─ 领域最佳实践（业界方法论/工具链）                │
│   │   └─ 技术约束（数据源/API/合规）                      │
│   ├─ 产出：调研摘要（结构化 Markdown）                   │
│   └─ 时间限制：每个维度最多 3 次搜索                      │
│                                                         │
│   Step 2: 基于调研结果的 4 个核心问题              [opus]  │
│                                                         │
│   Q1. 竞品确认                                           │
│   "基于调研，以下竞品中哪些是你的直接对标？"               │
│   （展示调研发现的竞品列表，用户选择 + 补充）              │
│                                                         │
│   Q2. 功能边界对标                                       │
│   "你希望与竞品相比，哪些功能必须有、哪些不需要、         │
│    哪些是独特创新？"                                      │
│   （Must-Have / Nice-to-Have / Differentiator 三栏引导） │
│                                                         │
│   Q3. 领域知识缺口                                       │
│   "以下领域知识中，哪些是团队需要补强的？"                 │
│   （基于调研发现的领域专业术语/方法论列出）                │
│                                                         │
│   Q4. 数据源与约束                                       │
│   "核心功能依赖哪些数据源？有哪些获取限制？"               │
│   （API 可用性/成本/合规/延迟）                           │
│                                                         │
│   产出：                                                 │
│   ├─ docs/research/competitive/landscape.md               │
│   └─ docs/research/domain/knowledge-gaps.md              │
│   更新：.discovery-manifest.json phase2.status = "done"  │
│   检查点：git commit                                     │
├─────────────────────────────────────────────────────────┤
│ Phase 3: SYSTEM（系统描述 — Zachman 六维度）       [opus]  │
│                                                         │
│   最关键 Phase——从定性发现转为 AI 可消费的结构化描述       │
│   ──────────────────────────────────────────             │
│                                                         │
│   6 个维度逐个提问，每个维度 2-3 个问题                  │
│   基于 Phase 1-2 的回答推导，不重复问已回答的内容         │
│                                                         │
│   D1. ENTITIES（What — 核心实体）                        │
│   "系统需要管理哪些核心实体？每个实体的关键属性是什么？"   │
│   （引导用户列出数据模型，AI 辅助推导属性）               │
│                                                         │
│   D2. CAPABILITIES（How — 核心能力）                     │
│   "系统必须具备哪些核心能力？用户能执行哪些关键操作？"     │
│   （引导用户列出功能模块和操作流程）                      │
│                                                         │
│   D3. ACTORS（Who — 角色与权限）                         │
│   "系统有哪些用户角色？不同角色的权限边界在哪里？"         │
│   （角色/权限/视图隔离）                                  │
│                                                         │
│   D4. EVENTS（When — 事件与触发）                        │
│   "系统中有哪些关键事件？什么触发状态变更？"               │
│   （实时/定时/用户触发/外部事件）                         │
│                                                         │
│   D5. CONSTRAINTS（Where — 技术与部署约束）              │
│   "系统部署在哪里？有哪些技术栈/平台约束？"               │
│   （云/本地/混合、浏览器/桌面/移动端、性能要求）          │
│                                                         │
│   D6. INTEGRATIONS（Why + 外部系统）                     │
│   "系统需要与哪些外部系统对接？数据流向是什么？"           │
│   （上游数据源/下游消费者/第三方服务）                    │
│                                                         │
│   产出格式（YAML frontmatter + Markdown）：               │
│   ┌──────────────────────────────────────────────┐       │
│   │ ---                                          │       │
│   │ entities:                                    │       │
│   │   - name: Instrument                         │       │
│   │     attributes: [code, name, price, volume]  │       │
│   │   - name: Strategy                           │       │
│   │     attributes: [...]                        │       │
│   │ capabilities:                                │       │
│   │   - name: backtest                           │       │
│   │     description: ...                         │       │
│   │ actors: [...]                                │       │
│   │ events: [...]                                │       │
│   │ constraints: [...]                           │       │
│   │ integrations: [...]                          │       │
│   │ ---                                          │       │
│   │ # System Description                         │       │
│   │ ## Entities                                  │       │
│   │ ...                                          │       │
│   └──────────────────────────────────────────────┘       │
│                                                         │
│   产出：docs/brief/system-description.md                 │
│   更新：.discovery-manifest.json phase3.status = "done"  │
│   检查点：git commit                                     │
├─────────────────────────────────────────────────────────┤
│ Phase 4: CONSTRAINTS（宪法与非谈判约束）            [opus]  │
│                                                         │
│   对标 ProductBuilder constitution.md 概念               │
│   ──────────────────────────────────────────             │
│                                                         │
│   4 类约束逐个确认，每个 1-2 个问题                      │
│                                                         │
│   C1. 技术约束                                           │
│   "哪些技术选择是锁死的、不能变的？"                      │
│   （框架/语言/数据库/部署环境）                           │
│                                                         │
│   C2. 产品边界                                           │
│   "有哪些功能是明确不做/永远不会做的？"                    │
│   （反功能列表——比"做什么"更能定义产品）                  │
│                                                         │
│   C3. UX 约束                                            │
│   "有哪些用户体验原则是不可妥协的？"                      │
│   （性能/响应时间/可访问性/设计语言）                     │
│                                                         │
│   C4. 合规与安全                                         │
│   "有哪些合规/安全/隐私要求？"                            │
│   （数据保护/监管/审计/许可证）                           │
│                                                         │
│   产出格式（条目式，≤ 1 页）：                            │
│   ┌──────────────────────────────────────────────┐       │
│   │ # Constitution                                │       │
│   │ ## 技术约束                                   │       │
│   │ - [T1] 必须使用 TypeScript strict mode        │       │
│   │ - [T2] 包管理必须使用 bun                    │       │
│   │ ## 产品边界                                   │       │
│   │ - [P1] 不做社交功能                           │       │
│   │ - [P2] 不做多租户 SaaS                        │       │
│   │ ## UX 约束                                    │       │
│   │ - [U1] 首屏加载 < 2s                          │       │
│   │ ## 合规                                       │       │
│   │ - [C1] 用户数据不出境                          │       │
│   └──────────────────────────────────────────────┘       │
│                                                         │
│   产出：docs/brief/constitution.md                       │
│   更新：.discovery-manifest.json phase4.status = "done"  │
│   检查点：git commit                                     │
├─────────────────────────────────────────────────────────┤
│ Phase 5: SYNTHESIS（验证 + 落盘 + 衔接）           [opus]  │
│                                                         │
│   最终整合与质量门禁                                     │
│   ──────────────────────────────────────────             │
│                                                         │
│   Step 1: Zachman 6 维度覆盖度检查                  [sonnet] │
│   ├─ 每个维度是否有至少 1 个实体/能力/角色/事件          │
│   ├─ 维度间是否有逻辑矛盾                               │
│   └─ 产出：覆盖度评分（N/6 维度已覆盖）                  │
│                                                         │
│   Step 2: Brief ↔ Research ↔ Constitution 一致性检查 [sonnet] │
│   ├─ Brief 中的实体是否与 System Description 匹配        │
│   ├─ Brief 中的竞品定位是否与 Research 一致               │
│   ├─ Constitution 约束是否与 Brief 的成功标准兼容         │
│   └─ 产出：一致性报告（pass/warning/fail 项）            │
│                                                         │
│   Step 3: 下游衔接检查                             [sonnet] │
│   ├─ 确认产出物格式可被 /ditto-product-arch 消费          │
│   ├─ 检查 docs/brief/ 和 docs/research/ 文件完整性       │
│   └─ 产出：衔接清单                                      │
│                                                         │
│   Step 4: 最终落盘                                [sonnet] │
│   ├─ 合并 Brief 各章节到 product-brief.md                │
│   │   ├─ §1 Vision（Phase 1）                           │
│   │   ├─ §2 System（Phase 3 摘要）                      │
│   │   ├─ §3 Constraints（Phase 4 摘要）                  │
│   │   └─ §4 Research Index（Phase 2 索引链接）           │
│   ├─ 确认 constitution.md 和 system-description.md 独立 │
│   ├─ 更新 .discovery-manifest.json                      │
│   │   ├─ status: "completed"                            │
│   │   └─ completedAt: <ISO timestamp>                   │
│   └─ git commit                                         │
│                                                         │
│   Step 5: 下游衔接提示                             [sonnet] │
│   输出：                                                 │
│   "Product Discovery 完成。下一步建议：                   │
│    /ditto-product-arch --create                          │
│    （消费 docs/brief/ + docs/research/ → 产出 spec）     │
│    可选：先运行 /ditto-product-discovery --validate       │
│    确认产出物完整性。"                                    │
└─────────────────────────────────────────────────────────┘
```

---

## 特殊模式

### --validate（完整性检查）

只跑 Phase 5 的 Step 1-3 检查，不修改任何文件。

```
INIT [sonnet]
→ Zachman 覆盖度检查 [sonnet]
→ Brief/Research/Constitution 一致性检查 [sonnet]
→ 下游衔接检查 [sonnet]
→ 输出检查报告（pass/warning/fail）
```

**通过标准**：
- Zachman 6 维度覆盖 ≥ 5/6
- 一致性检查 0 个 fail 项
- 所有产出文件存在且非空

### --sync（反向同步）

当下游 spec 变更时，反向更新 Brief/Research 保持一致。

```
INIT [sonnet]
→ 读取当前 spec 文档（docs/designs/specs/00-18）
→ Diff Brief/Research vs Spec
→ 识别不一致项
→ AskUserQuestion 确认每个变更
→ 更新 Brief/Research
→ git commit
```

### --from-existing（补救路径）

从现有 spec 反推生成 Brief + Research（适用于历史 spec 缺少上游文档的情况）。

```
INIT [sonnet]
→ 读取所有 spec 文档
→ AI 提取：定位/用户/痛点/竞品/系统描述/约束
→ 反向填充 Brief + Research 结构
→ 标注置信度（高/中/低）——AI 推导的内容需要用户确认
→ AskUserQuestion 逐项确认
→ 落盘 + git commit
```

### --phase `<N>`（恢复/重跑）

从指定 Phase 恢复或重跑。Phase 1-4 的已产出文件保留，只重新执行指定 Phase 的提问和落盘。

```
--phase 1  → 重跑 VISION
--phase 2  → 重跑 LANDSCAPE（重新调研）
--phase 3  → 重跑 SYSTEM（重新提问）
--phase 4  → 重跑 CONSTRAINTS
--phase 5  → 重跑 SYNTHESIS
```

---

## Manifest 格式

```jsonc
{
  "version": 1,
  "status": "in-progress", // in-progress | completed
  "topic": "A 股多因子策略回测平台",
  "startedAt": "2026-04-17T10:00:00Z",
  "completedAt": null,
  "phases": {
    "1": { "name": "VISION", "status": "done", "completedAt": "..." },
    "2": { "name": "LANDSCAPE", "status": "in-progress" },
    "3": { "name": "SYSTEM", "status": "pending" },
    "4": { "name": "CONSTRAINTS", "status": "pending" },
    "5": { "name": "SYNTHESIS", "status": "pending" }
  },
  "artifacts": {
    "brief": "docs/brief/product-brief.md",
    "constitution": "docs/brief/constitution.md",
    "systemDescription": "docs/brief/system-description.md",
    "competitiveLandscape": "docs/research/competitive/landscape.md",
    "knowledgeGaps": "docs/research/domain/knowledge-gaps.md"
  }
}
```

---

## 提问规范

### 原则

1. **每轮一个问题**：不要一次问多个，避免用户选择困难
2. **多选优先**：提供 3-4 个选项 + "其他（自定义）"
3. **基于上下文**：后续问题引用前面回答的内容，不要重复问
4. **AI 先做功课**：Phase 2 先调研再提问，不问用户本可以通过搜索得到的信息
5. **允许跳过**：如果用户说"不确定"或"跳过"，标记为待定，Phase 5 汇总
6. **使用 AskUserQuestion 工具**：结构化呈现选项，而非纯文本提问

### 问题格式模板

```
## Phase {N}: {PHASE_NAME} — Q{n}/{total}

{背景句：基于前面回答的上下文}

{核心问题}

选项：
- A. {选项 1}
- B. {选项 2}
- C. {选项 3}
- D. {选项 4}

提示：{可选的补充说明/参考信息}
```

### 跳过处理

| 用户回复 | 行为 |
|---------|------|
| "跳过" / "不确定" | 标记为 `[待定]`，Phase 5 汇总时再次确认 |
| "回到上一步" | 回退到上一个问题，清除当前回答 |
| "这个 Phase 先这样" | 跳过本 Phase 剩余问题，进入下一个 Phase |
| "暂停" | 保存当前进度到 manifest，git commit，提示恢复命令 |

---

## 模型路由策略

| 阶段 | 模型 | 理由 |
|------|------|------|
| Phase 0: INIT | sonnet | 文件读取 + manifest 操作，纯机械 |
| Phase 1: VISION | opus | 产品定位需要深度理解和判断 |
| Phase 2: LANDSCAPE 调研 | sonnet | WebSearch + 信息整理，偏结构化 |
| Phase 2: LANDSCAPE 提问 | opus | 基于调研结果的追问需要洞察力 |
| Phase 3: SYSTEM | opus | Zachman 六维度需要系统思维 |
| Phase 4: CONSTRAINTS | opus | 约束定义需要权衡判断 |
| Phase 5: SYNTHESIS 检查 | sonnet | 结构化一致性检查 |
| Phase 5: SYNTHESIS 整合 | opus | 最终判断和决策建议 |

---

## 与下游命令的关系

```
/ditto-product-discovery              /ditto-product-arch          /ditto-design-cycle
（Pipeline -1：产品发现）               （Pipeline 0：产品架构）      （Pipeline 1：UI 创建+审查）
        │                                      │                            │
        ├─ 产出 Product Brief                   ├─ 消费 Brief + Research     ├─ 消费 spec
        ├─ 产出 Research Repository             ├─ 产出 spec（IA/蓝图/流程）  ├─ 产出 HTML 原型
        ├─ 产出 Constitution                   └─ 产出用户流程/术语表        └─ 产出审查报告
        └─ 产出 System Description                                            │
                                                    /ditto-page-contract      │
                                                    （Pipeline 2：合同）      │
                                                         │                    │
                                                         ├─ 消费原型+蓝图      │
                                                         └─ 产出合同 JSON     │
                                                                              │
                                                    /ditto-app-dev            │
                                                    （Pipeline 3：实现）──────┘
                                                         ├─ 消费合同
                                                         └─ 产出 React
```

**关键衔接**：
- `/ditto-product-discovery` 产出 → `/ditto-product-arch` 的输入
- `/ditto-product-arch` Phase 0: CONTEXT 新增读取 `docs/brief/` + `docs/research/`
- Brief 中的 Vision 定义 product-arch 的设计目标
- System Description 直接输入 product-arch 的 IA/蓝图设计
- Constitution 约束 product-arch 的设计边界

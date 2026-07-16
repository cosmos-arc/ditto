---
name: ditto-product-discovery
description: 结构化产品发现——5 Phase LLM 深度提问，从模糊想法到 Product Brief + Research Repository + Assumption Registry。当用户需要定义新功能/新页面的产品定位、竞品分析、系统描述时使用。
disable-model-invocation: true
---

# /ditto-product-discovery

结构化产品发现。通过 LLM 深度提问引导用户从模糊想法到完整的 **Product Brief + Research Repository + Assumption Registry**。

> **定位**: Pipeline -1。所有新功能/新页面的产品定义应先经过此 skill。
> **下游**: `/ditto-product-arch --create` 消费 Brief + Research → 产出 spec。

---

## 核心约束

1. **每轮一个问题**，使用 AskUserQuestion 工具，多选优先（3-4 选项 + "其他"）
2. **AI 先做功课**: Phase 2 先调研再提问，不问用户本可通过搜索得到的信息
3. **假设追踪**: 每个回答都可能产生未验证假设，Phase 结束前回顾提取到 assumptions.md
4. **渐进聚焦**: 宏观（定位/用户）→ 中观（竞品/系统）→ 微观（约束/细节）
5. **可中断可续接**: 每 Phase 独立 checkpoint + git commit
6. **盲点探测**: 每个 Phase 固定 2 个触发点（中间问题后 + 最后问题后），主动揭示"未知未知"
7. **模型路由**: 主对话使用当前会话模型。子代理 dispatch 点按标注切换模型。

> 详细的提问规范、跳过处理、假设提取规则见 `references/questioning-protocol.md`。

---

## 产出物

```
docs/brief/
├── product-brief.md          # Vision + System + Constraints 合并
├── constitution.md           # 非谈判约束（≤ 1 页条目式）
├── system-description.md     # Spec-grade YAML + Markdown
└── assumptions.md            # 假设注册表（风险 + 验证状态）

docs/research/
├── competitive/landscape.md  # 竞品分析（功能矩阵 + 定位象限 + 差异化）
└── domain/knowledge-gaps.md  # 领域知识缺口 + 数据源约束

.discovery-manifest.json      # Phase 进度追踪（v2）
```

> 所有产出物的详细格式规范见 `references/templates.md`。
> Manifest JSON 格式见 `references/manifest-schema.md`。

---

## 执行流程

### 输入

`$ARGUMENTS` — 命令 + 可选参数。无参数时运行全流程。特殊模式见 `references/special-modes.md`。

```
/ditto-product-discovery                    # 全流程
/ditto-product-discovery "A 股回测平台"     # 带初始主题
/ditto-product-discovery --phase 2          # 从 Phase 2 恢复
/ditto-product-discovery --validate         # 只跑完整性检查
```

### Phase 0: INIT

1. 检查 `.discovery-manifest.json` 是否存在
   - 存在 → 读取进度，确定恢复点（有 `--phase N` 则从 Phase N 恢复）
   - 不存在 → 初始化 manifest v2
2. 解析 `$ARGUMENTS` 中的主题描述（如有）
3. 创建 `docs/brief/` 和 `docs/research/` 目录结构
4. git init commit

### Phase 1: VISION — 产品身份定义

回答"我们是谁、为谁、解决什么问题"。6 个问题逐个推进。

**Q1. 产品定位**: "这个产品的核心定位是什么？"（选项: 专业工具/消费品/B2B 内部工具/开发者平台）

**Q2. 目标用户**: "主要服务哪类用户？核心特征？"（基于 Q1 追问画像）

**Q3. 核心痛点**: "用户目前最大的痛点？现在怎么解决的？"（引导描述现状和不满）

**Q4. 差异化价值**: "已有方案的不足？我们凭什么更好？"（引导思考竞争壁垒）

**Q5. 成功标准**: "产品成功用什么指标衡量？"（选项: 效率/决策质量/留存/其他）

**Q6. 盲点扫描**: 基于用户 Q1-Q5 回答执行盲点检查，输出 1-2 条盲点提示。

**→ 提取假设到 assumptions.md → 写入 product-brief.md Vision 章节 → git commit**

### [Gate 1→2]

展示 Phase 1 摘要（定位/用户/痛点/差异化/成功标准/盲点/假设数），用户确认后进入 Phase 2。

### Phase 2: LANDSCAPE — 竞品与领域调研

渐进式调研 + 渐进式披露。

**Step 0. 调研范围确认** (1 问): 基于 Phase 1 定位提出 2-3 个调研维度关键词，用户确认/补充。

**Step 1. 并行调研** (3 个 sonnet sub-agent):
- Agent A: 竞品调研 → 竞品列表 + 功能矩阵初稿
- Agent B: 领域调研 → 领域知识清单 + 工作流参考
- Agent C: 技术调研 → 技术约束清单 + 可选数据源
- 每个 Agent 限制: 最多 3 次 WebSearch

**Step 2. 渐进式提问** (3 轮，每轮 1 问):

- **Round A. 竞品确认**: "调研发现以下竞品，哪些是你的直接对标？" → 写入 landscape.md → 注册假设
- **Round B. 功能边界**: "对比 {竞品}，你的功能边界？"（Must-Have / Nice-to-Have / Differentiator / Not-Doing） → 更新功能矩阵 → 注册假设
- **Round C. 约束与缺口**: "以下领域知识和技术约束中，哪些是关键瓶颈？" → 写入 knowledge-gaps.md → 注册假设

**→ 更新 assumptions.md → 写入 landscape.md + knowledge-gaps.md → git commit**

### [Gate 2→3]

展示调研摘要（竞品/功能边界/关键约束/假设数），用户确认后进入 Phase 3。

### Phase 3: SYSTEM — 系统描述（Zachman 六维度）

最关键 Phase——从定性发现转为 AI 可消费的结构化描述。

**访谈 4 个合并维度 + 1 个优先级（输出覆盖 Zachman 6 维度）**:

| 维度 | 覆盖 Zachman | 问题数 | 写入 YAML |
|------|-------------|--------|----------|
| D1 DOMAIN MODEL | ENTITIES + CAPABILITIES | 3 | `entities[]` + `capabilities[]` |
| D2 ROLES & ACCESS | ACTORS | 2 | `actors[]` |
| D3 EVENT FLOWS | EVENTS + INTEGRATIONS | 2 | `events[]` + `integrations[]` |
| D4 PLATFORM | CONSTRAINTS | 1 | `constraints[]` |
| D5 PRIORITY | 新增 | 2 | `priorities[]` |

**D1. DOMAIN MODEL** (What + How 合并 — 实体与能力)

- **Q1. 核心领域**: "最核心的 3-5 个领域概念？主要属性和行为？"（AI 基于 Phase 1-2 推导初始列表，用户确认/补充）
- **Q2. 实体关系**: "这些概念之间的关系？"（AI 生成关系图草案，用户确认）
- **Q3. 关键操作流程**: "最重要的领域概念，用户核心操作流程？"（每个核心实体 1 个主流程）
- 💡 盲点扫描 (固定触发: Q3 之后)

**D2. ROLES & ACCESS** (Who)

- **Q4. 角色定义**: "系统有哪几类用户？核心职责？"
- **Q5. 权限边界**: "不同角色能做什么、不能做什么？"

**D3. EVENT FLOWS** (When + Why 合并 — 事件与数据流)

- **Q6. 核心事件**: "最重要的 3-5 个状态变更事件？触发条件和后续效果？"
- **Q7. 数据流入与流出**: "系统依赖哪些外部数据？产生哪些数据给外部？"
- 💡 盲点扫描 (固定触发: Q7 之后)

**D4. PLATFORM** (Where)

- **Q8. 技术栈与部署**: "必须使用什么技术栈？部署在哪里？性能要求？"

**D5. PRIORITY** (Impact × Feasibility)

- **Q9. 优先级确认**: AI 基于实体重要性和约束复杂度推导 Impact × Feasibility 四象限（Quick Wins / Must-Have / Nice-to-Have / Defer），展示给用户确认/调整
- **Q10. MVP 覆盖**: "有没有 MVP 必须有但 AI 标记为低优先级的？"

**→ 更新 assumptions.md → 写入 system-description.md（Spec-grade YAML） → git commit**

> system-description.md 的完整 YAML schema 见 `references/templates.md`。

### [Gate 3→4]

展示系统描述概览（实体数/能力数/角色数/事件数/集成数/Zachman 覆盖/优先级分布/假设数），用户确认后进入 Phase 4。

### Phase 4: CONSTRAINTS — 宪法与非谈判约束

4 类约束逐个确认，每类 1-2 个问题。

- **C1. 技术约束**: "哪些技术选择是锁死的？"（框架/语言/数据库/部署）
- **C2. 产品边界**: "有哪些功能是明确不做的？"（反功能列表）
- **C3. UX 约束**: "哪些 UX 原则不可妥协？"（性能/响应/可访问性/设计语言）
- **C4. 合规与安全**: "有哪些合规/安全/隐私要求？"
- 💡 盲点扫描 (固定触发: C2 和 C4 之后各 1 次)

Constitution 格式: 条目式，≤ 1 页，带编号（T1, P1, U1, C1）。

**→ 更新 assumptions.md → 写入 constitution.md → git commit**

### [Gate 4→5]

展示约束摘要（技术/产品边界/UX/合规各 N 条 + 高风险未验证假设），如有高风险未验证假设建议先处理。

### Phase 5: SYNTHESIS — 验证 + 落盘 + 衔接

**Step 1. Zachman 覆盖度检查**: 6 维度是否至少各 1 个条目。YAML 字段完整性（entities 带 typed attributes、capabilities 带 steps + actors、actors 带 permissions、events 带 payload + effects、constraints 有 deployment 定义、integrations 有 dataFlow）。

**Step 2. 一致性检查**: Brief 实体 vs System Description、Brief 竞品定位 vs Research、Constitution 约束 vs Brief 成功标准、landscape 功能矩阵 vs system-description 能力。

**Step 3. 假设盘点**: 列出所有 unvalidated High risk 假设，检查 Phase 2 调研是否提供了部分证据，对仍为 unvalidated 的建议验证路径或标记为"已知风险"。

**Step 4. 下游衔接检查**: 确认产出物格式可被 `/ditto-product-arch` 消费，检查文件完整性。

**Step 5. 最终落盘**:
- 合并 Brief 各章节到 `product-brief.md`（§1 Vision + §2 System 摘要 + §3 Constraints 摘要 + §4 Research Index + §5 Assumption Summary）
- 确认 constitution.md、system-description.md、assumptions.md 独立保留
- 更新 manifest: `status: "completed"` + `completedAt`
- git commit

**Step 6. 下游衔接提示**: 建议运行 `/ditto-product-arch --create`。

---

## Phase Gate 机制

每个 Phase 结束后执行 Phase Gate review。展示本 Phase 答案摘要 + 未验证假设数，用户选择:

| 用户选择 | 行为 |
|---------|------|
| 确认 | 通过 Gate，进入下一 Phase |
| 修改某个回答 | 回退到指定问题，清除后续回答，重新推进 |
| 暂停 | 保存进度到 manifest + assumptions.md，git commit，输出恢复命令 |
| 补充内容 | 用户补充信息，更新对应 artifact，继续 |

---

## 与下游命令的关系

```
/ditto-product-discovery  (Pipeline -1)  →  /ditto-product-arch  (Pipeline 0)
       │                                           │
       ├─ Product Brief                            ├─ 消费 Brief + Research
       ├─ Research Repository                       ├─ 产出 spec（IA/蓝图/流程）
       ├─ Constitution                              └─ 产出用户流程/术语表
       ├─ System Description (Spec YAML)                    │
       └─ Assumption Registry                              │
                                               /ditto-design-cycle (Pipeline 1)
                                               /ditto-page-contract (Pipeline 2)
                                               /ditto-app-dev (Pipeline 3)
```

**关键衔接**: System Description（Spec-grade YAML）直接输入 product-arch 的 IA/蓝图设计。Assumption Registry 辅助 product-arch 识别高风险假设。Constitution 约束 product-arch 的设计边界。

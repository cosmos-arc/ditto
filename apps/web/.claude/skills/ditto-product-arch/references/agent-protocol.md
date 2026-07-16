# Agent 协议

> 定义 `/ditto-product-arch` 的模型路由、Agent dispatch、冲突协调和 Phase Gate 规范。

---

## 模型路由策略

| 阶段 | 模型 | 理由 |
|------|------|------|
| Phase 0: CONTEXT | sonnet | 文件读取 + 上游校验 |
| Phase 1: RESEARCH | 混合 | Domain Expert/IA 用 sonnet，策略判断用 opus |
| Phase 2: DESIGN | 按角色 | Strategist/IA=opus，UX/Domain=sonnet |
| Phase 3: SYNTHESIS | opus | 多角色冲突权衡取舍 |
| Phase 4: DOCUMENT | sonnet | 文档写入 |
| Phase 5: VALIDATE | sonnet | 一致性检查 |

---

## Agent Dispatch 协议

### Phase 1: RESEARCH（2 个 Agent 并行）

**IA + Domain Expert Agent [sonnet]**
- 输入: 现有 spec + discovery entities/capabilities + discovery landscape
- 任务: 竞品 IA 对比 + A 股量化工作流 + 全资产平台最佳实践
- 输出: 调研摘要 + 参考架构草案

**Strategist Agent [opus]**
- 输入: 现有 spec + discovery product brief + discovery landscape
- 任务: 竞品差异化分析 + 用户需求趋势
- 输出: 差异化建议 + 功能边界提案

### Phase 2: DESIGN（4 个 Agent 并行）

**每个 Agent 的通用 prompt 结构**:

```
你是 {角色名}（{model}）。

## 上下文
- 产品定位: {从 discovery brief 提取}
- Constitution 约束: {注入相关约束条目}
- 领域实体: {从 discovery system-description 注入}
- 竞品参考: {从 discovery landscape 注入}

## 你的职责
{角色定义，见 roles.md}

## 产出要求
📋 设计草案（结构化 Markdown）
🔍 发现的问题/风险
💡 创新建议（超越竞品的差异化设计）
```

**角色→模型→产出**:

| Agent | 模型 | 核心产出 |
|-------|------|---------|
| Product Strategist | opus | 产品范围 + 用户场景 + 功能边界 |
| Information Architect | opus | IA 结构 + 蓝图框架 + 导航模型 |
| UX Strategist | sonnet | 用户流程 + 交互模式 + 4 项状态定义（见下方） |
| Domain Expert | sonnet | 领域约束 + 术语验证 + 工作流验证 |

### UX Strategist 状态定义职责

UX Strategist MUST 为每个页面产出以下 4 项（`ditto-design-cycle --create` 的直接输入）：

**A. Tab Content Sections**
- 每个 tab MUST 定义: 子模块清单、数据字段、交互说明
- 数据字段优先引用 01 IA 文档已定义字段
- 不允许只写标签名

**B. Overlay Registry**
- 每项 MUST 包含: 触发条件、内容结构、关闭行为
- 破坏性操作 MUST 有 Confirm Dialog

**C. Component × State Matrix**
- 行 = 组件名，列 = 状态（见 enums.md 通用状态清单）
- 数据组件 MUST 定义 loading/empty/failed 三态
- 映射 04_interaction_state_spec.md 的通用状态到本页具体组件

**D. Page Contract Mapping**
- route: 从 IA 文档路由定义提取
- shellFamily: 从页面角色推导（见 enums.md 7 枚举值）
- pagePattern: 从页面角色推导（见 enums.md 8 枚举值）
- 模块→Slot 映射表: shell 级→SHELL_SLOT_MAP，页面级→kebab-case

---

## 冲突协调规则

Phase 3 SYNTHESIS 中，opus 负责识别和解决冲突。

### 冲突类型与解决策略

| 冲突 | 策略 | 优先级 |
|------|------|--------|
| Strategist vs IA（功能多 vs 结构简） | 协商：评估功能优先级，低优先级延后 | IA 优先 |
| IA vs UX（信息分组 vs 交互路径） | 先定结构，交互适配结构 | IA 优先 |
| Domain vs All（专业正确性 vs 易用性） | 专业正确性为底线，易用性在正确基础上优化 | Domain 优先 |

### 协调流程

1. 汇总 4 角色设计草案
2. 识别冲突点（自动检测 + 高风险假设标记）
3. 按优先级策略解决冲突
4. Domain Expert 验证领域合理性
5. 使用 AskUserQuestion 呈现**关键决策点**（非所有决策）
6. 输出统一设计方案

---

## Phase Gate 规范

### Gate 位置

```
Phase 0 → [Gate 0→1] → Phase 1 → Phase 2 → [Gate 2→3] → Phase 3 → Phase 4 → [Gate 4→5] → Phase 5
```

### Gate 执行协议

**每个 Gate MUST**:
1. 展示本阶段产出摘要
2. 展示关键指标（假设数/违规数/覆盖率）
3. 使用 AskUserQuestion 呈现给用户
4. 根据用户选择执行对应行为

### Gate 内容

**Gate 0→1（CONTEXT → RESEARCH）**:
- 上游校验结果（YAML 完整性 / 缺失字段列表）
- 上游 digest（实体数/约束数/高风险假设数/竞品数）
- 本次设计范围
- 现有 spec 完整性评分

### Phase 0: UPSTREAM VALIDATION（新增）

当 `.discovery-manifest.json` 存在且 `status === "completed"` 时，在 CONTEXT 阶段执行上游产出物校验：

```
1. 读取 system-description.md，提取 YAML block
2. 校验顶层 key 存在: entities, capabilities, actors, events, constraints, integrations
3. 校验 entities[] 每个实体有 attributes 字段（至少 1 个属性）
4. 校验 capabilities[] 每个能力有 steps 和 actors 字段
5. 校验 actors[] 每个角色有 permissions 字段
6. 校验 events[] 每个事件有 payload 字段
7. 校验 constraints[] 至少有 1 条 deployment 定义
8. 校验 integrations[] 每项有 dataFlow 字段
9. 校验 constitution.md 存在且包含 C1-C4 分类
10. 校验 landscape.md 存在且包含竞品功能矩阵

缺失项 → BLOCK，输出具体缺失字段列表，建议运行 /ditto-product-discovery --phase N 补全。
```

**Gate 2→3（DESIGN → SYNTHESIS）**:
- 4 角色设计草案摘要
- 冲突清单
- Constitution 违规预警

**Gate 4→5（DOCUMENT → VALIDATE）**:
- 文档变更摘要
- **跨文档契约验证结果**（C1-C6，见 validation-rules.md §一致性）
- 状态覆盖率报告
- Constitution 合规报告

### 用户选项

| 选项 | 行为 |
|------|------|
| 确认 | 通过 Gate，进入下一 Phase |
| 修改 | 回退到指定 Phase，清除后续产出，重新执行 |
| 暂停 | 保存进度到 `.arch-manifest.json` + git commit，输出恢复命令 |

### 暂停恢复

暂停时输出恢复命令：

```bash
/ditto-product-arch --phase N
```

恢复时从 manifest 读取进度，跳过已完成的 Phase。

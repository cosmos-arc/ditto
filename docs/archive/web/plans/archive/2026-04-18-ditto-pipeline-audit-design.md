# Ditto Pipeline 审阅 — 优化项设计

> 日期：2026-04-18
> 状态：draft
> 范围：5 个 ditto skill 的衔接优化 + 缺失环节补全

---

## 审阅范围

对 ditto-product-discovery、ditto-product-arch、ditto-design-cycle、ditto-page-contract、ditto-app-dev 五个 skill 的端到端工作流及互相衔接进行全面审阅。

---

## 发现与决策

### P0-1：product-arch 产出范围扩展（补 00/04 spec）

**问题**：`00_ditto_product_criteria.md`（审查标准）和 `04_interaction_state_spec.md`（通用状态定义）是 design-cycle 和 page-contract 的硬依赖，但无 skill 产出。

**决策**：扩展 product-arch Phase 4 DOCUMENT，将 00 和 04 纳入产出物。

**改动**：

| 文件 | 改动 |
|------|------|
| `.claude/skills/ditto-product-arch/SKILL.md` | Phase 4 新增产出 `00_ditto_product_criteria.md` 和 `04_interaction_state_spec.md`；产出物表格增加两行 |
| `.claude/skills/ditto-product-arch/references/output-structure.md` | 增加 00 和 04 的文档模板 |
| `.claude/skills/ditto-product-arch/references/roles.md` | 各角色审查清单增加 00/04 相关检查项 |

**00_ditto_product_criteria.md 内容**（从 product-arch Phase 2 DESIGN 提取）：
- 密度准则（信息密度标准）
- 字号映射表
- 间距梯度规范
- 色彩使用原则
- 品牌气质锚定

**04_interaction_state_spec.md 内容**（从 product-arch Phase 2 UX Strategist 提取）：
- 通用状态定义（loading / empty / error / stale / success）
- 页面状态映射
- 状态转换规则
- Skeleton / Toast / Error boundary 规范

---

### P0-2：discovery → product-arch 上游校验

**问题**：discovery 产出的 YAML 结构化数据被拆成自然语言注入 Agent prompt，格式漂移不会被捕获。

**决策**：在 product-arch Phase 0 CONTEXT 中增加 YAML 结构完整性校验，不合格 BLOCK。

**改动**：

| 文件 | 改动 |
|------|------|
| `.claude/skills/ditto-product-arch/references/agent-protocol.md` | Phase 0 步骤增加校验逻辑描述 |

**校验逻辑**（写入 Phase 0）：
```
Phase 0 新增: UPSTREAM VALIDATION
  if .discovery-manifest.json exists and status === "completed":
    1. 读取 system-description.md，提取 YAML block
    2. 校验顶层 key 存在: entities, capabilities, actors, events, constraints, integrations
    3. 校验每个实体有 attributes 字段
    4. 校验每个能力有 steps + actors 字段
    5. 缺失项 → BLOCK，列出具体缺失
  else:
    输出警告（现有行为不变）
```

不需要 ajv 或中间 schema，简单的 key 存在性 + 非空检查。

---

### P0-3：app-dev → design-cycle 反馈回路

**问题**：app-dev 记录的 `[proto-deviation]` 没有消费者，实现中发现的设计问题无法回流到 design-cycle。

**决策**：app-dev Phase 15 聚合反馈到结构化文件；design-cycle 增加 `--review-feedback` 模式。

**app-dev 侧改动**：

| 文件 | 改动 |
|------|------|
| `.claude/skills/ditto-app-dev/references/ship.md` | 新增 FEEDBACK AGGREGATION 步骤 |

```
Phase 15 新增: FEEDBACK AGGREGATION [sonnet]
  1. 扫描当前页面所有 [proto-deviation] doc comments
  2. 扫描 Phase 14 Gap 分析中分类为"原型缺陷"的项
  3. 如果反馈项 > 0:
     → 写入 docs/contracts/feedback/<page>.md
     → 输出建议: "发现 N 项实现反馈，建议运行 /ditto-design-cycle <prototype> --review-feedback <page>"
  4. 如果反馈项 = 0: 跳过
```

**反馈文件格式**：`docs/contracts/feedback/<page>.md`
```markdown
# Implementation Feedback: <page>

## 原型缺陷 (proto-deviation)
- [<模块>] <描述> → 建议: <修改方向>

## 设计改进建议
- [<模块>] <描述> → 建议: <改进方向>
```

**design-cycle 侧改动**：

| 文件 | 改动 |
|------|------|
| `.claude/skills/ditto-design-cycle/SKILL.md` | 输入参数表增加 `--review-feedback` |
| `.claude/skills/ditto-design-cycle/references/execution-flow.md` | 增加模式变体说明 |

```
--review-feedback <page>
  前置: docs/contracts/feedback/<page>.md 存在
  流程: BASELINE → 读取反馈文件 → 针对性 FIX（只处理反馈中列出的区域）→ VERIFY → FINAL
  范围: 局部审查，不做全页 7 角色并行
```

---

### P1-4：Design Token Requirements 纳入 product-arch 产出

**问题**：Token 创建无流程依据，靠 CLAUDE.md 人工审批。

**决策**：product-arch Phase 2 DESIGN 中 UX Strategist 提取"Design Token Requirements"，Phase 4 写入独立章节。

**改动**：

| 文件 | 改动 |
|------|------|
| `.claude/skills/ditto-product-arch/references/output-structure.md` | Blueprint 模板增加 Token Requirements 章节 |

**Token Requirements 章节**（嵌入 Blueprint 或独立）：
```markdown
## Design Token Requirements

### 需新增的 Token
| Token 名称 | 类型 | 用途 | 来源页面/模块 |
|-----------|------|------|--------------|
| --spacing-panel-gap | spacing | 面板内间距 | Markets / Queue Section |

### 需废弃的 Token
| Token 名称 | 替代 | 原因 |
|-----------|------|------|

### 需修改的 Token
| Token 名称 | 旧值 | 新值 | 原因 |
|-----------|------|------|------|
```

不新建 skill，只在 product-arch 产出中增加结构化提取。

---

### P1-5：合同创建入口职责边界明确化

**问题**：design-cycle Phase 0.5 和 page-contract `--create` 都能创建合同，用户不清楚该用哪个。

**决策**：文档层面明确边界 — design-cycle `--create` 只做快速建档（draft），app-dev 消费前必须显式 promote。

**改动**：

| 文件 | 改动 |
|------|------|
| `.claude/skills/ditto-design-cycle/references/create-mode.md` | Step 8.16a-c 说明改为"快速建档，不替代完整 promote 流程" |
| `.claude/skills/ditto-app-dev/SKILL.md` | 衔接图增加 promote 步骤的显式提示 |

**design-cycle Phase 8 FINAL 输出增加**：
```
合同状态提示:
  ✅ 合同已建档（draft）
  ⚠️ 如需 app-dev 消费，请先执行:
     /ditto-page-contract --validate <page> --promote
```

---

### P2-6（记录）：快速修复路径

**现状**：小改动（颜色、间距、文案）需要走完整 pipeline 或绕过 pipeline。

**记录但不实施**：在 app-dev SKILL.md 中记录一个 "Quick Fix Checklist" 作为人工操作指引，不做自动化模式。当需求积累到一定量时再评估是否增加 `--hotfix` 模式。

---

## 实施计划

| 步骤 | 内容 | 依赖 |
|:---:|------|:---:|
| 1 | P0-1: 扩展 product-arch Phase 4 产出（00/04 模板 + SKILL.md） | — |
| 2 | P0-2: product-arch Phase 0 上游校验逻辑 | — |
| 3 | P0-3: app-dev ship.md 反馈聚合 + design-cycle --review-feedback | — |
| 4 | P1-4: product-arch Blueprint 模板增加 Token Requirements | — |
| 5 | P1-5: 合同创建边界文档明确化 | — |
| 6 | 验证：确认所有引用路径正确、无断裂 | 步骤 1-5 |

步骤 1-5 相互独立，可并行实施。

# ditto-page-contract V2 优化设计

> 基于业界 skill 最佳实践 + UI/UX 设计合同最佳实践，对 ditto-page-contract 系统做三层优化。

---

## 决策摘要

| 层面 | 决策 | 理由 |
|------|------|------|
| **L1: Skill 文件质量** | 渐进式披露 + 错误恢复 + 示例 | Anthropic 最佳实践：context window 是公共资源 |
| **L2: 设计合同覆盖度** | +a11yRole/a11yLabel + responsiveBehavior | 精简方案，ROI 最高 |
| **L3: Pipeline 集成** | +--update + --promote --all + 移除 disable-model-invocation | 消除上下游衔接断裂 |

---

## 第一层：Skill 文件质量优化

### 1.1 渐进式披露重构

**当前问题**：210 行 skill 文件内嵌 bash one-liner（107-123 行）和详细 AI 执行步骤（Phase R/B/S/T/W），每次加载都消耗 context。

**目标结构**：

```
ditto-page-contract.md          ← 主文件（~80 行）：流程图 + 子命令语义 + reference link
├── contract-cli.md             ← CLI 命令参考：validate/promote/refresh-metrics 的具体命令
├── contract-create-phases.md   ← AI 执行 phases 详情：R/B/S/T/W 每步具体操作
└── contract-error-recovery.md  ← 错误恢复：每个 BLOCK 检查的修复指引
```

**主文件只保留**：
- 生命周期流程图
- 5 个子命令的语义描述（一行一句）
- Reference 文件链接表
- 输入参数 + 产出物

**抽取到 reference 的内容**：
- `contract-cli.md`：validate/promote/refresh-metrics 的完整 bash 命令
- `contract-create-phases.md`：Phase R（如何读 manifest）、Phase B（如何解析 blueprint section）、Phase S（如何映射 selector）、Phase T（如何分配阈值）、Phase W（如何组装 JSON）
- `contract-error-recovery.md`：13 项 BLOCK 检查的逐条修复指引

### 1.2 错误恢复指引

为 validator 的 13 项 BLOCK 检查添加修复指引：

| 检查 | 失败时修复步骤 |
|------|---------------|
| #1 JSON Schema | 读 schema 错误提示，补缺字段或修正类型 |
| #2 Prototype 文件 | 确认 `prototypeRef` 路径正确，文件在 `docs/designs/specs/prototypes/` 下 |
| #3 Blueprint refs | 确认 `blueprintRefs` 中的文件存在于 `docs/designs/specs/` |
| #4 prototypeSelector 缺失 | 重新运行 `create.mjs --prototype <path>` 或手动填写 |
| #5 reactSelector 格式 | 修正为 `[data-slot='xxx']` 或 `[data-testid='xxx']` |
| #6 metrics baseline 空 | 运行 `--refresh-metrics <page>` |
| #7 universal states 缺失 | 补全 loading/empty/error/stale |
| #8 零容忍阈值不为 0 | 设为 0（consoleErrors/pageErrors/missingSelectors/targetMismatch） |
| #9 shellFamily 不在枚举 | 对照 spec §10 修正 |
| #10 pagePattern 不在枚举 | 对照 spec §11 修正 |
| #11 subSlots selector 无效 | 同 #4/#5，修正格式 |
| #12 generated artifacts 语法 | 运行 `bun run generate-contracts` 重新生成 |
| #13 状态 gate | draft 是 WARNING（不阻断），unknown 是 BLOCK（检查 status 值） |

### 1.3 真实示例引用

在 skill 文件的 "合同 JSON 结构" 部分替换注释版为真实示例引用：

```markdown
### 合同示例

参考 `docs/contracts/pages/home.contract.json`（唯一已创建的合同）。
```

### 1.4 Token 预算

| 文件 | 当前行数 | 目标行数 | 说明 |
|------|---------|---------|------|
| ditto-page-contract.md | 210 | ~80 | 主文件精简为索引 |
| contract-cli.md | 0 | ~40 | 抽取的 CLI 命令 |
| contract-create-phases.md | 0 | ~60 | 抽取的 AI 执行细节 |
| contract-error-recovery.md | 0 | ~30 | 新增的错误恢复 |

**总 token 预算**：从单文件 210 行 → 主文件 80 行 + 3 个 reference（按需加载）。常驻 context 减少约 60%。

---

## 第二层：设计合同覆盖度优化

### 2.1 精简 A11Y Contract

在 `slotMapping` definition 中添加两个 optional 字段：

```jsonc
// slotMapping 新增
"a11yRole": {
  "type": "string",
  "description": "ARIA role，如 'complementary', 'navigation', 'main', 'region'"
},
"a11yLabel": {
  "type": "string",
  "description": "aria-label 或 aria-labelledby 引用"
}
```

**填写规则**：
- Shell 级 slot（rail/header/main）→ 必填 `a11yRole`
- Content subSlot → 按需填写
- AI 在 Phase S（Selector Map）时从 prototype 的语义结构推断

**validator 新增检查**：
- Shell 级 required slot 必须有 `a11yRole`（WARN 级，不阻断）

### 2.2 Responsive Behavior

在 `slotMapping` definition 中添加可选字段：

```jsonc
// slotMapping 新增
"responsiveBehavior": {
  "type": "object",
  "properties": {
    "compact": {
      "type": "string",
      "enum": ["hidden", "collapsed", "overlay", "reflow", "unchanged"]
    }
  },
  "description": "compact viewport（< 1024px）下的行为变化"
}
```

**填写规则**：
- 只对 compact viewport 下有行为变化的 slot 填写
- 默认 `unchanged`（不填即不变）
- AI 在 Phase S 时从 prototype viewport 验证结果推断

**validator 新增检查**：
- 如果 `viewports` 包含 `compact` role，建议检查是否有 slot 标注了 `responsiveBehavior`（WARN 级）

### 2.3 Motion 预留（不实现）

schema 顶层预留 `motion` optional 字段：

```jsonc
"motion": {
  "type": "object",
  "description": "预留：页面级运动规范（暂不实现）",
  "properties": {}
}
```

### 2.4 Interaction Micro-states（不实现）

hover/focus/active/disabled 是组件库（shadcn）层面的责任，不纳入页面合同。

---

## 第三层：Pipeline 集成健壮性

### 3.1 `--update` 子命令

从 app-dev 反馈中更新合同字段：

```bash
/ditto-page-contract --update home --selector sidebar '[data-slot="sidebar-rail"]'
/ditto-page-contract --update home --threshold sidebar heightRatio=0.08
/ditto-page-contract --update home --add-subslot risk-matrix
```

**执行流程**：

```
Phase READ: 读取当前合同 JSON
Phase DIFF: 比较请求变更与当前值
Phase APPLY: 应用变更
Phase BUMP: version++，updatedAt = today
Phase REGEN: 运行 generate.mjs
Phase VALIDATE: 运行 validateContract() → 全绿才写入
```

**约束**：
- 只允许更新 selector、threshold、subSlot 相关字段
- 不允许修改 id、status、route、shellFamily、pagePattern（这些需要重新 --create）
- validate 失败 → 回滚变更，不写入

### 3.2 `--promote --all`

批量提升所有 draft 合同：

```bash
/ditto-page-contract --promote --all
```

**执行流程**：

```
1. 运行 validateAllContracts() → 全绿才继续
2. 遍历所有 status === "draft" 的合同
3. 对每个合同执行 promote 流程（检查 manifest + console errors）
4. 输出批量提升报告
5. 任一失败 → 跳过该合同，继续其余
```

### 3.3 移除 `disable-model-invocation: true`

**当前矛盾**：
- skill 设了 `disable-model-invocation: true`
- 但 design-cycle Phase 8.16 明确要求 AI 调用 `/ditto-page-contract --create`

**决策**：移除该限制，允许 AI 在 design-cycle 流程中主动调用。

**风险缓解**：
- `--create` 有前置条件检查（manifest status），不会意外创建
- `--promote` 有验证门禁，不会意外提升
- AI 不会凭空调用，只在 design-cycle 明确要求时触发

---

## 实施优先级

| 优先级 | 任务 | 影响范围 | 依赖 |
|:------:|------|---------|------|
| P0 | 移除 `disable-model-invocation` | 1 行 | 无 |
| P0 | Skill 文件渐进式披露重构 | 4 文件 | 无 |
| P1 | Schema 添加 a11y + responsive 字段 | schema + validator + generator | 无 |
| P1 | 错误恢复指引 | 1 reference 文件 | 无 |
| P2 | `--update` 子命令 | skill + validator | P1 |
| P2 | `--promote --all` | skill + validator | 无 |
| P3 | Motion 预留字段 | schema 1 行 | 无 |
| P3 | 生成文件 .gitignore 规则 | .gitignore | 无 |

---

## 变更清单

### 新增文件

| 文件 | 内容 |
|------|------|
| `.claude/commands/contract-cli.md` | CLI 命令参考 |
| `.claude/commands/contract-create-phases.md` | AI 执行 phases 详情 |
| `.claude/commands/contract-error-recovery.md` | 错误恢复指引 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `.claude/commands/ditto-page-contract.md` | 精简为 ~80 行索引文件 |
| `scripts/contract-generator/schema/contract.schema.json` | +a11yRole, +a11yLabel, +responsiveBehavior, +motion |
| `scripts/contract-generator/validators/contract-validator.mjs` | +a11y WARN 检查, +responsive WARN 检查 |
| `scripts/contract-generator/generate.mjs` | 生成文件适配新字段 |
| `scripts/contract-generator/templates/threshold-policy.ts.mjs` | 无变更 |

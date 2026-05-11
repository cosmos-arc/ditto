# ditto-app-dev Skill 重构设计

> 日期：2026-04-18
> 状态：draft
> 目标：将 ditto-app-dev.md 从单体文件拆分为 SKILL.md + reference 文件结构，精简参数，消除重复，与上游 skill 对齐

---

## 背景

`ditto-design-cycle.md` 和 `ditto-page-contract.md` 已完成成熟化拆分：
- design-cycle：SKILL.md ~150 行 + 12 个 reference 文件
- page-contract：SKILL.md ~120 行 + 3 个 reference 文件

`ditto-app-dev.md` 仍为 ~600 行单体文件，与上游 skill 结构不一致，且存在参数膨胀、规则重复等问题。

---

## 优化项

### P0-1：文件拆分

#### 目标结构

```
.claude/commands/
├── ditto-app-dev.md                    # SKILL.md（~200 行）
└── app-dev/
    ├── phases/
    │   ├── metric.md                   # Phase 10 度量提取
    │   ├── architect.md                # Phase 11 组件架构
    │   ├── implement.md                # Phase 12 TDD 实现
    │   ├── polish.md                   # Phase 13 交互打磨
    │   ├── verify.md                   # Phase 14 三层验证
    │   └── ship.md                     # Phase 15 收尾
    └── iteration-protocol.md           # 迭代协议 + 突破机制
```

#### SKILL.md 保留内容

SKILL.md 只保留 agent 需要快速决策的信息：

1. **Frontmatter**（name + description）
2. **参数定义**（精简后的 4 个核心参数）
3. **Agent 分工与 Model Routing 表**
4. **执行流程概览图**（ASCII，Phase 10→15）
5. **Phase 依赖关系图**
6. **与 ditto-design-cycle 的衔接图**
7. **禁止事项**（仅 app-dev 专属规则，不含 CLAUDE.md 重复项）
8. **Reference 文件索引表**

#### 各 Phase 文件职责

| 文件 | 内容 | 引用 |
|------|------|------|
| `metric.md` | Playwright 启动配置、标准化 CSS 注入、度量提取脚本、布局策略推导规则、contract 更新流程、禁止项 | `visual-verification.md`（浏览器配置） |
| `architect.md` | 原型结构分析步骤、组件树输出格式、shadcn 映射方法、状态管理策略、复用策略、交互式确认流程 | contract JSON（slots/subSlots/states） |
| `implement.md` | 组件粒度拆分规则、TDD 循环（RED→GREEN→CHECK→SIMPLIFY→REFACTOR）、布局实现铁律、状态覆盖实现、Slot 一致性验证、**Phase 12.5 布局 smoke test**、并行规则 | Phase 10 度量数据、Phase 11 架构文档 |
| `polish.md` | 交互状态审计表（8 种元素类型 × 必需状态）、CSS Transitions 基线规则、Motion 引入判断标准、Micro-interactions 清单、交互状态测试要求 | `impeccable:animate`、`impeccable:polish`、`impeccable:colorize` |
| `verify.md` | 0 容忍预检、L1 Token 合规命令、L2 Layout 执行步骤（selector 来源、阈值来源）、L3 Pixel 执行步骤（脚本命令、分数解读引用）、Gap 分析分类、综合评分公式、失败回退路由 | `visual-verification.md`（陷阱 10 分数解读） |
| `ship.md` | 前置条件检查、代码简化、bun run check、文档更新、manifest 推进、实现报告格式 | `code-simplifier:code-simplifier` |
| `iteration-protocol.md` | 触发条件、循环体步骤、终止条件表、突破协议（opus 升级）、停滞判断标准 | — |

---

### P0-2：参数精简

#### 精简前后对比

| 原参数 | 处置 | 理由 |
|--------|------|------|
| `--implement <page>` | **保留** | 核心模式 |
| `--implement-batch <pages>` | **重命名为 `--batch`** | 更简洁，语义不变 |
| `--iterate` | **保留** | 有独立价值 |
| `--iterate-goal <score>` | **移至默认值** | 默认 8.5 足够，极端场景通过环境变量 `DITTO_ITERATE_GOAL` |
| `--iterate-max <N>` | **移至默认值** | 默认 3 轮足够，极端场景通过环境变量 `DITTO_ITERATE_MAX` |
| `--polish-only <page>` | **移除**，用 `--phase 13` 替代 | 语义重复 |
| `--verify-only <page>` | **移除**，用 `--phase 14` 替代 | 语义重复 |
| `--phase <N>` | **保留** | 调试/恢复场景需要 |
| `--from-prototype <path>` | **移除** | contract.create 时已记录 prototypePath |
| `--viewport <WxH>` | **移除** | contract.visualThresholds.viewport 已覆盖 |
| `--max-diff-pixel-ratio <0-1>` | **移除** | contract.visualThresholds.maxDiffPixelRatio 已覆盖 |
| `--force-metric` | **移除** | 用 `/ditto-page-contract --refresh-metrics` 替代 |
| 旧模式（无参数） | **移除** | 强制要求明确参数，降低歧义 |

#### 精简后参数

```bash
# 核心模式（4 个）
/ditto-app-dev --implement <page>          # 全流程实现
/ditto-app-dev --batch <pages>             # 批量实现
/ditto-app-dev --implement <page> --iterate # 迭代模式
/ditto-app-dev --phase <10|11|12|13|14|15>  # 跳转指定 Phase
```

#### 参数说明表（精简后）

| 参数 | 说明 | 示例 |
|------|------|------|
| `--implement <page>` | 实现单个页面（度量→TDD→打磨→验证→完成） | `--implement home` |
| `--batch <pages>` | 批量实现，逗号分隔 | `--batch home,markets,trading` |
| `--iterate` | 自主迭代（实现→验证→分析→优化，直到达标或 max-rounds） | `--implement home --iterate` |
| `--phase <N>` | 跳转到指定 Phase（需前置数据已存在） | `--phase 14` |

#### 环境变量配置项（替代移除的 CLI 参数）

| 环境变量 | 默认值 | 替代的 CLI 参数 |
|---------|--------|----------------|
| `DITTO_ITERATE_GOAL` | 8.5 | `--iterate-goal` |
| `DITTO_ITERATE_MAX` | 3 | `--iterate-max` |

---

### P1-3：移除与 CLAUDE.md 重复的禁止项

从 ditto-app-dev 禁止事项中移除以下 3 条（CLAUDE.md 已覆盖）：

| 移除项 | CLAUDE.md 来源 |
|--------|---------------|
| Phase 12 跳过 RED 直接 GREEN | "TDD: RED→GREEN→REFACTOR" |
| 连续 Edit（Read/Edit 比 < 2.0） | "Read ≥ 2x Edit" |
| 不调用 systematic-debugging 就重试 | Skills 优先级表 |
| 跳过 verification-before-completion | Skills 优先级表 |

保留的禁止事项（app-dev 专属）：

| 保留项 | 理由 |
|--------|------|
| 跳过 Phase 10 直接实现 | 专属流程约束 |
| 跳过 Phase 11 直接写代码 | 专属流程约束 |
| 使用 Chrome DevTools 提取度量 | 专属工具约束 |
| 无 prototype 依据的百分比高度 | 专属实现约束 |
| 原型缺陷时不记录直接修改实现 | 专属文档约束 |
| L3 截图使用默认 old headless | 专属工具约束 |
| Phase 13 盲目引入 Motion | 专属审美约束 |
| `transition-all` 滥用 | 专属 CSS 约束 |
| 迭代循环中跳过 Gap 分析直接重试 | 专属流程约束 |

---

### P1-4：Phase 12.5 布局 Smoke Test

#### 设计目标

在 Phase 12 实现完成后、Phase 13 打磨之前，插入一个 **30 秒快速验证**，捕获结构性布局错误。

这不是完整的 Phase 14——只检查关键区域的 bounding rect，不做 L1 Token 检查和 L3 像素对比。

#### 触发条件

Phase 12 所有组件的 TDD 循环完成后自动触发。

#### 执行步骤

```
Phase 12.5: LAYOUT SMOKE TEST [sonnet]
│
├─ 1. 启动 React dev server（如果未运行）
│
├─ 2. Playwright 启动 + 加载 React 页面
│     chromium.launch({ channel: 'chromium' })
│
├─ 3. 提取关键区域 bounding rect
│     selector 来源：contract shell slots（required=true）
│     每个 shell slot：x, y, width, height
│
├─ 4. 与 Phase 10 度量数据对比
│     通过标准：宽度偏差 < 5%，高度偏差 < 8%
│     （比 Phase 14 宽松，因为只做结构性检查）
│
├─ 5. 结果
│     ├─ 全部通过 → 输出摘要，继续 Phase 13
│     └─ 存在失败 → 输出偏差报告 + 定向修复建议
│          ├─ 偏差 < 15% → 内联修复（调整 CSS）
│          ├─ 偏差 15-30% → 回退对应组件的 TDD 循环
│          └─ 偏差 > 30% → 回退 Phase 11 重新评估
```

#### 与 Phase 14 的区别

| 维度 | Phase 12.5 Smoke | Phase 14 Verify |
|------|:---:|:---:|
| 检查范围 | shell slots only | shell slots + content subSlots |
| L1 Token | ❌ | ✅ |
| L2 Layout | 粗粒度（shell only） | 细粒度（全部 selector） |
| L3 Pixel | ❌ | ✅ |
| 阈值 | 宽松（5%/8%） | 严格（3%/5%） |
| 耗时 | ~30s | ~3min |
| 失败处理 | 定向修复 | Gap 分析 + 回退路由 |

---

### P1-5：设计系统优先级规则

在 SKILL.md 的"确定性约束"中增加：

```markdown
### 设计系统优先级

当合同值与项目 design system 冲突时，按以下优先级处理：

1. **project design system tokens**（`src/styles/design-tokens/`）— 最高优先级
2. **page contract selector/threshold** — 中优先级
3. **prototype literal values** — 最低优先级

处理方式：
- 以 design system 为准实现
- 通过 `/ditto-page-contract --update` 将修正后的值反馈到合同
- 记录 `[contract-override]` rationale
```

---

### P2-6：消除 L3 分数解读重复

当前 Phase 14 VERIFY 内嵌了 L3 分数解读表（< 2% 优秀、2-4% 良好…），与 `visual-verification.md` 陷阱 10 完全重复。

**处理方式**：Phase 14 的 verify.md 中改为引用：

```markdown
L3 分数解读：详见 [visual-verification.md 陷阱 10](../rules/visual-verification.md)
```

---

## 设计系统优先级冲突处理规则

新增到 SKILL.md 确定性约束：

```
冲突处理优先级（高→低）：
1. project design system tokens（src/styles/design-tokens/）
2. page contract selector/threshold
3. prototype literal values

当 contract 值与 design system 冲突时：
→ 以 design system 为准
→ 通过 /ditto-page-contract --update 反馈到合同
→ 记录 [contract-override] rationale
```

---

## 文件拆分方案

### SKILL.md 结构（~200 行）

```
---
frontmatter（name + description）
---

# /ditto-app-dev

## 参数（4 个）
## Agent 分工与 Model Routing
## 执行流程概览图
## Phase 依赖关系
## 确定性约束（含设计系统优先级）
## 与 ditto-design-cycle 的衔接
## 禁止事项（仅 app-dev 专属，~9 条）
## Reference 文件索引
```

### Reference 文件清单

```
app-dev/
├── phases/
│   ├── metric.md       ← Phase 10: Playwright 配置 + 标准化 CSS + 度量提取 + 布局策略推导
│   ├── architect.md    ← Phase 11: 结构分析 + 组件树 + shadcn 映射 + 状态管理 + 复用
│   ├── implement.md    ← Phase 12: TDD 循环 + 布局铁律 + 状态覆盖 + Slot 验证 + Phase 12.5
│   ├── polish.md       ← Phase 13: 交互审计表 + CSS 基线 + Motion 标准 + Micro-interactions
│   ├── verify.md       ← Phase 14: 0 容忍预检 + L1/L2/L3 + Gap 分析 + 评分 + 回退路由
│   └── ship.md         ← Phase 15: 前置检查 + 代码简化 + 文档 + manifest + 报告
└── iteration-protocol.md ← 迭代循环 + 终止条件 + 突破协议
```

---

## 实施计划

| 步骤 | 内容 | 前置 |
|:---:|------|:---:|
| 1 | 创建 `app-dev/` 目录结构 | — |
| 2 | 拆分 Phase 文件（metric→ship），从 ditto-app-dev.md 提取对应内容 | 步骤 1 |
| 3 | 拆分 iteration-protocol.md | 步骤 1 |
| 4 | 重写 SKILL.md（参数精简 + Agent 表 + 流程图 + 约束 + 禁止项精简） | 步骤 2-3 |
| 5 | 新增 Phase 12.5 到 implement.md | 步骤 2 |
| 6 | 新增设计系统优先级到 SKILL.md 确定性约束 | 步骤 4 |
| 7 | verify.md 中 L3 分数解读改为引用 | 步骤 2 |
| 8 | 验证：确认所有 reference 路径正确、无断裂引用 | 步骤 4-7 |

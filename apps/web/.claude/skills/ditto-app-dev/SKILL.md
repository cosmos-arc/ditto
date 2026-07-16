---
name: ditto-app-dev
description: >
  原型落地 + 交互打磨 + 三层验证。从 design-cycle 的 done 状态接手，
  通过 page contract 驱动实现，到 Ship 完成。支持 --implement（单页面）、
  --batch（批量）、--iterate（自主迭代）、--phase（跳转）。
disable-model-invocation: true
---

# /ditto-app-dev

从 Prototype 到 Production 的完整实现管线。
与 ditto-design-cycle 通过 page contract + edition manifest 衔接。

---

## 输入参数

`$ARGUMENTS` — 页面名 + 模式

```bash
/ditto-app-dev --implement home                  # 全流程实现（度量→TDD→打磨→验证→完成）
/ditto-app-dev --implement home --iterate        # 迭代模式（默认目标 8.5，最多 3 轮）
/ditto-app-dev --batch home,markets,trading      # 批量实现，按 shell family 并行
/ditto-app-dev --phase 14                        # 跳转到指定 Phase 执行
```

| 参数 | 说明 |
|------|------|
| `--implement <page>` | 实现单个页面（度量→TDD→打磨→验证→完成） |
| `--batch <pages>` | 批量实现，逗号分隔，可按 shell family 并行 |
| `--iterate` | 自主迭代模式（实现→验证→分析→优化，直到达标或 max-rounds） |
| `--phase <10\|11\|12\|13\|14\|15>` | 跳转到指定 Phase（需前置数据已存在） |

迭代配置通过环境变量调整：`DITTO_ITERATE_GOAL`（默认 8.5）、`DITTO_ITERATE_MAX`（默认 3）。

---

## Agent 分工与 Model Routing

| Phase | Agent | Model | 职责 | 可用 Skills |
|-------|-------|-------|------|------------|
| 10 METRIC | Metric Reader | sonnet | 读取 contract.metrics.baseline | 无 |
| 11 ARCHITECT | Component Architect | opus | 组件树、状态管理、shadcn 映射、复用策略 | brainstorming |
| 12 IMPLEMENT | TDD Developer | sonnet × N | RED→GREEN→REFACTOR，按组件并行 | test-driven-development, subagent-driven-development |
| 12.5 SMOKE | Layout QA | sonnet | 结构性布局快速验证 | 无 |
| 13 POLISH | Interaction Polisher | opus | Design system 对齐 + 排版 + 交互 + Motion + 色彩 + 边界加固 | impeccable:normalize, impeccable:typeset, impeccable:animate, impeccable:colorize, impeccable:harden, impeccable:polish |
| 14 VERIFY | Visual QA | sonnet | Audit 5 维 + L1 Token + L2 Layout + L3 Pixel | impeccable:audit, verification-before-completion, systematic-debugging |
| 15 SHIP | Final Review | sonnet | 最终质量 pass + 代码简化 + 文档 + manifest | impeccable:polish, code-simplifier:code-simplifier |

| 场景 | Model | 理由 |
|------|-------|------|
| 组件架构决策、交互打磨审美判断 | opus | 需要创意/审美/深度推理 |
| TDD 编码、度量提取、验证对比、文档 | sonnet | 结构化操作，效率优先 |
| 迭代循环中的突破判断（连续 2 轮无进展） | opus | 需要跳出局部最优 |

---

## 执行流程

```
/ditto-app-dev --implement <page>
│
▼
Phase 10: METRIC [sonnet]
│  读取 contract.metrics.baseline → 推导布局策略
│
▼
Phase 11: ARCHITECT [opus]
│  组件树 + 状态管理 + shadcn 映射 → 用户确认
│
▼
Phase 12: IMPLEMENT [sonnet × N]
│  RED → GREEN → CHECK → SIMPLIFY → REFACTOR
│  └─ Phase 12.5: LAYOUT SMOKE TEST（shell slots 快速验证）
│
▼
Phase 13: POLISH [opus]
│  normalize → typeset → 交互审计 → transitions → animate → colorize → harden → micro
│
▼
Phase 14: VERIFY [sonnet]
│  Audit 5 维 → L1 Token → L2 Layout → L3 Pixel → Gap 分析 + 评分
│  └─ 失败 → 定向回退对应 Phase
│
▼
Phase 15: SHIP [sonnet]
│  polish → code-simplifier → bun run check → 文档更新 → manifest 推进
│
▼
完成（--iterate 未指定）
│
└─ 或进入迭代循环（--iterate）→ Phase 12/13/14 循环直到达标
```

### Phase 依赖关系

```
Phase 10 ← Phase 11（度量数据是架构设计的输入）
Phase 10 ← Phase 14（同一 Playwright 配置，同一度量基准）
Phase 11 ← Phase 12（架构文档是实现的输入）
Phase 12 ← Phase 12.5（实现的组件是 smoke test 的输入）
Phase 12.5 ← Phase 13（smoke 通过后进入打磨）
Phase 12 ← Phase 14（实现的组件是验证的输入）
```

---

## 确定性约束

### 设计系统优先级

当合同值与项目 design system 冲突时，按以下优先级处理：

1. **`DESIGN.md`**（设计系统描述）— P0：最高优先级，AI 可读的结构化描述
2. **project design system tokens**（`src/styles/design-tokens/`）— P1：token SSOT
3. **page contract selector/threshold** — P2：中优先级
4. **prototype literal values** — P3：最低优先级

处理方式：以 design system 为准实现，通过 `/ditto-page-contract --update` 反馈到合同，记录 `[contract-override]` rationale。

### 原型缺陷处理

在 Phase 14 VERIFY 中发现差距时，必须先判断根因：

| 根因类型 | 处理 |
|---------|------|
| **实现问题** | 回退 Phase 12/13 修复 |
| **原型缺陷** | 实现层优化（记录 rationale），不回退修改原型 |
| **架构问题** | 回退 Phase 11 重新设计 |
| **Token 缺失** | 先补充 token，再修复实现 |

原型缺陷记录格式（写入实现页面的 doc comment）：
```
/* [proto-deviation] 原型使用固定高度 200px，但内容驱动更合理。
   原因：原型未考虑动态数据长度。
   决策：使用 min-h + content-driven，日期：2026-04-12 */
```

---

## 与 ditto-design-cycle 的衔接

```
ditto-design-cycle Phase 8 FINAL（标记 done）
    │  edition manifest: page.state = "done"
    │  git tag: review/<task>/done
    ▼
ditto-page-contract --create <page>
    │  产出: docs/contracts/pages/<page>.contract.json (status: draft)
    │  自动生成: .generated.ts + .generated.mjs
    ▼
ditto-page-contract --validate <page>
    │  15 项检查（13 BLOCK + 2 WARN）
    ▼
ditto-page-contract --promote <page>
    │  status: draft → contract-ready
    ▼
ditto-app-dev --implement <page>
    │  Phase 10: 读取 contract.metrics.baseline
    │  Phase 11: 读取 contract slots/subSlots/states/metrics/interactions
    │  Phase 12: 从 contract 读取 states + 验证 subSlots
    │  Phase 12.5: shell slots 结构性布局快速验证
    │  Phase 14: 从 contract 读取 selector + threshold → 精确验证
    │  Phase 15: 检查 contract.status === "contract-ready"
    ▼
Phase 15 SHIP
    │  edition manifest: page.state = "implemented"
    │  如有 [proto-deviation] → 写入原型反馈清单
    ▼
ditto-design-cycle --edition-review（可选，跨页审计时参考）
```

---

## --batch 批量模式

批量实现多个页面，按 shell family 分组并行。

- 同一 shell family 的页面共享 Phase 11 架构方案
- Phase 12 按页面并行，Phase 14 按页面并行验证
- 每个页面独立评分，全部通过后统一 SHIP

---

## 禁止事项

| ❌ 禁止 | 原因 |
|---------|------|
| 跳过 Phase 10 直接实现 | 无度量数据 = 猜测布局，偏差必然 > 20% |
| 跳过 Phase 11 直接写代码 | 无架构方案 = 组件混乱，返工成本 3-5x |
| 使用 Chrome DevTools 提取度量 | 已统一到 Playwright，混合环境产生虚假偏差 |
| 无 prototype 依据的百分比高度 | 必须从度量数据推导布局策略 |
| 原型缺陷时不记录直接修改实现 | 所有 proto-deviation 必须有 rationale 记录 |
| L3 截图使用默认 old headless | 必须使用 `channel: 'chromium'` 确保像素准确 |
| Phase 13 盲目引入 Motion | 必须满足判断标准（退出动画/布局补间/stagger/手势） |
| `transition-all` 滥用 | 仅在多属性过渡时使用，默认 `transition-colors` |
| 迭代循环中跳过 Gap 分析直接重试 | 每次失败必须分类根因，定向修复 |

---

## Reference 文件

### Phase 详情

| 文件 | Phase | 内容 |
|------|-------|------|
| [references/metric.md](references/metric.md) | 10 | Playwright 配置、标准化 CSS、度量提取、布局策略推导 |
| [references/architect.md](references/architect.md) | 11 | 原型结构分析、组件树、shadcn 映射、状态管理、复用策略 |
| [references/implement.md](references/implement.md) | 12 + 12.5 | TDD 循环、布局铁律、状态覆盖、Slot 验证、Layout Smoke Test |
| [references/polish.md](references/polish.md) | 13 | 交互审计表、CSS 基线、Motion 标准、Micro-interactions |
| [references/verify.md](references/verify.md) | 14 | 0 容忍预检、L1/L2/L3、Gap 分析、评分、回退路由 |
| [references/ship.md](references/ship.md) | 15 | 前置检查、代码简化、文档更新、manifest 推进 |

### 协议

| 文件 | 内容 |
|------|------|
| [references/iteration-protocol.md](references/iteration-protocol.md) | 迭代循环、终止条件、突破协议 |

### 规范参考

| 文件 | 内容 |
|------|------|
| [workflow.md](../../rules/workflow.md) | 流程规范 |
| [architecture.md](../../rules/architecture.md) | 架构规范 |
| [visual-verification.md](../../rules/visual-verification.md) | 视觉验证四层模型 |
| [page-contracts.generated.ts](../../../src/features/shell/page-contracts.generated.ts) | 自动生成的页面合同（源文件在 `docs/contracts/pages/`） |
| `/ditto-page-contract` | 创建/验证/提升/更新页面合同 |

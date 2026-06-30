# Wave 1 实现计划（主索引 · 通往"首次真实使用"）

> **For Claude:** 本文档是 Wave 1 的**索引与横切规范**。各工作流的 bite-sized TDD 任务在独立详细计划中，执行时用 `superpowers:executing-plans`。

**Goal:** 交付 Wave 1 五条工作流，使系统到达"首次真实使用"汇合点——打开 ditto-app 看到基于 promotion-ready 真实数据的选股信号、由真实组合优化器构建组合、可记录决策并复盘。

**Architecture:** 双路径并行收敛。路径 A（产品接入）：A1 eod 自动 publish、A0 前端接真实后端。路径 B（后端功能完整度）：B0 组合优化器（cvxpy）、B1 成交量约束 fill、B3 真实数据 promotion。单人顺序执行，每条工作流独立分支/PR。

**Tech Stack:** Python 3.12 / polars / cvxpy（新增）/ basedpyright strict / pytest / ruff / inline-snapshot；前端 React 19 + TanStack + Vite + Biome + bun。

**战略索引:** [战略定位与功能差距分析](2026-06-24-strategic-positioning-and-functional-gap-analysis.md)（§5.2 分阶段、§6.4 golden 策略、§6.3 cvxpy 选型）

---

## 0. 执行顺序、依赖 与 ⚠️ 分支基线问题

### 顺序（单人 → 顺序，可调整）

```
A1 eod 自动 publish-signals   ──┐  最小最快，先暖手 + 立即让 /trade/signals 不空
B0 组合优化器 (cvxpy)          ──┤  后端能力核心，新依赖
B1 成交量约束 fill             ──┼──► B3 真实数据 promotion（治理，并行推进，到达 RC1）
A0 前端接真实后端 (capstone)   ──┘  后端完整可信后接线
```

### ⚠️ 分支基线问题（执行前必须决策）

**实测发现：** `main` 落后当前 dev 分支（`dev/architecture-remediation-batch2-6`）**53 个 commit**，且 `signal_package.py`（A1 核心依赖）**不在 main 上**。

→ CLAUDE.md "从 main 拉开发分支"的规则**对 Wave 1 直接行不通**：A1/B0/B1 依赖的代码（signal_package、template_builders 等）只在 dev 分支。

**三个选项（需你拍板）：**
1. **先把 dev 合入 main**（经 PR），再从 main 拉 Wave 1 各分支 —— 最干净、符合 CLAUDE.md，但需先完成 dev→main 合并。
2. **Wave 1 各分支基于 dev 分支拉** —— 立即可做，但偏离"从 main 拉"规则，且 PR 目标需调整为 dev 或 main。
3. **先理清 dev 分支 53 commit 的归宿**（是否已通过其他 PR 合入 main、是否可清理）—— 可能 dev 已是过时分支，main 才是最新。

> **当前不拉分支、不开开发**（按你的指示）。这条留待执行前决策。

---

## 1. 横切关注点（所有工作流通用）

### 1.1 cvxpy 新依赖（B0 触发）

- **用 pixi**（禁 pip/poetry/conda）；`dev` 与 `default` 环境都加。
- cvxpy 接口是 numpy/稀疏矩阵，**不绑 pandas**（选它的硬理由，符合 polars-only）。
- 边界：`pl.DataFrame` → `.to_numpy()` → cvxpy → weights → 回填 `weight` 列；cvxpy 类型不泄漏出 Allocator。
- 详见 [B0 计划](2026-06-24-wave1-b0-portfolio-optimizer.md) Task B0.0。

### 1.2 golden 快照重录策略（B0/B1 必读，详见战略文档 §6.4）

- B0/B1 会让 golden 变红（数值变了）→ **预期改进，不是回归**。
- `pixi run -e dev test --snapshot` 重录；**禁止**调参掰回旧值。
- 每次重录单独 commit，message 记录差异证据。

### 1.3 质量门禁（每条工作流完成前）

```bash
pixi run -e dev check        # lint + fmt + type + test --fast
pixi run -e dev arch-check   # 架构契约（37 条）
```
- basedpyright strict 零 error、源码零 `# type: ignore`、ruff 全过、新代码有单测（分支覆盖 ≥80%）。
- **每条工作流独立分支 + 独立 PR**（回应 quality-eval 点名的 PR 超标问题）。
- A0 在 ditto-app 仓库：用 `bun run check`（biome + tsc + vitest）。

---

## 2. 工作流索引（详细计划链接）

| 工作流 | 仓库 | 估时（单人） | 依赖 | 详细计划 |
|---|---|---|---|---|
| **A1** eod 自动 publish-signals | ditto | ~2 天 | signal_package.py（dev 分支） | [wave1-a1-eod-publish-signals](2026-06-24-wave1-a1-eod-publish-signals.md) |
| **B0** 组合优化器（cvxpy） | ditto | ~1.5–2 周 | cvxpy 新增（须批准） | [wave1-b0-portfolio-optimizer](2026-06-24-wave1-b0-portfolio-optimizer.md) |
| **B1** 成交量约束 fill | ditto | ~1 周 | golden 重录 | [wave1-b1-volume-constrained-fills](2026-06-24-wave1-b1-volume-constrained-fills.md) |
| **A0** 前端接真实后端 | ditto-app | ~1–1.5 周 | A1 + B3（联调前置） | [wave1-a0-frontend-backend-wiring](2026-06-24-wave1-a0-frontend-backend-wiring.md) |
| **B3** 真实数据 promotion | ditto（真实环境） | ~1 周（并行） | 真实 API + governance | [wave1-b3-real-data-promotion](2026-06-24-wave1-b3-real-data-promotion.md) |

---

## 3. 汇合点验收（Wave 1 Definition of Done）

> 在一个真实交易日：打开 ditto-app → 看到**当天基于 promotion-ready 真实数据**的选股信号（A1+B3）→ 组合由**真实 MVO 优化器**构建（B0）→ 记录决策（A0 写路径）→ 事后看 deviation 复盘（A0）。回测数值已含**成交量约束**真实成本（B1）。

**全局门禁：**
- [ ] `pixi run -e dev ci` 全绿；37 架构契约全绿；源码零 `# type: ignore`。
- [ ] ditto-app `bun run check` 全绿；零 `any`/`@ts-ignore`/inline style。
- [ ] 5 条工作流各为独立 PR、规模可控。
- [ ] golden 重录 commit 带前后差异证据（B0/B1）。
- [ ] RC1 hard-gate 通过（B3）。

---

## 4. 风险登记（跨工作流）

| 风险 | 影响 | 缓解 |
|---|---|---|
| **分支基线**（main 落后 53 commit） | 阻塞所有 ditto 代码工作流拉分支 | §0 三选项，执行前决策 |
| cvxpy 病态 Σ 不收敛 | B0 阻塞 | 收敛失败 fallback InverseVolAllocator + warning |
| B1 fill 合约重构波及面大 | B1 超期 | `fill_mode` 开关保留旧行为；先单测后集成 |
| A0 跨仓库联调 | A0 阻塞 | 后端先固定 OpenAPI 契约；A0.4 联调待 A1+B3 |
| B3 治理依赖真实环境/人工 | 阻塞"真实数据"里程碑 | 尽早并行；不阻塞代码工作流 |
| golden 重录误判（真回归当改进） | 掩盖 bug | 重录前逐策略核对数值方向；差异入 commit |

---

## 5. 与战略文档的关系

本计划是 [战略定位与功能差距分析](2026-06-24-strategic-positioning-and-functional-gap-analysis.md) §6 路线图的**可执行展开**。战略文档定义"为什么 + 做什么 + 分阶段"；本计划组定义"怎么做（bite-sized TDD）"。两者保持同步：战略文档 §5.2 分阶段优先级变更时，本索引 §0 顺序相应调整。

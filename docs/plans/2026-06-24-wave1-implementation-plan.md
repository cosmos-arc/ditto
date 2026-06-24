# Wave 1 实现计划（通往"首次真实使用"）

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 交付 Wave 1 五条工作流，使系统到达"首次真实使用"汇合点——打开 ditto-app 看到基于 promotion-ready 真实数据的选股信号、由真实组合优化器构建组合、可记录决策并复盘。

**Architecture:** 双路径并行收敛。路径 A（产品接入）：A1 eod 自动 publish、A0 前端接真实后端。路径 B（后端功能完整度）：B0 组合优化器（cvxpy）、B1 成交量约束 fill、B3 真实数据 promotion。单人顺序执行，每条工作流独立分支/PR。

**Tech Stack:** Python 3.12 / polars / cvxpy（新增）/ basedpyright strict / pytest / ruff / inline-snapshot；前端 React 19 + TanStack + Vite；pixi 包管理。

**战略索引:** [2026-06-24-strategic-positioning-and-functional-gap-analysis.md](2026-06-24-strategic-positioning-and-functional-gap-analysis.md)（§5.2 分阶段、§6.4 golden 策略）

---

## 0. 执行顺序与依赖（单人 → 顺序）

```
A1 eod 自动 publish-signals   ──┐  (最小、最快，先暖手 + 立即让 /trade/signals 不再空)
B0 组合优化器 (cvxpy)          ──┤  (后端能力核心，新依赖)
B1 成交量约束 fill             ──┼──► B3 真实数据 promotion (治理，进行中，并行推进)
                                  │     到达 RC1 hard-gate
A0 前端接真实后端 (capstone)   ──┘  (后端已完整可信后，接线让能力被用起来)
```

**顺序理由（可调整）：**
1. **A1 先**：2 天、风险最低、立即产生价值（日常信号出现），暖手并验证 publish 链路。
2. **B0 再**：组合优化器是后端能力最大缺口、用户感知最强（组合质量），且 cvxpy 是新依赖需尽早落地验证。
3. **B1 接着**：fill 真实性会大面积改变 golden 快照，风险更高，放在 B0 后（此时已熟悉 golden 重录流程）。
4. **A0 收尾**：前端是 capstone——此时后端已完整可信，接线后"首次真实使用"建立在扎实基础上，而非给半成品镀金。
5. **B3 并行**：数据 promotion 是治理工作（真实环境 + governance），与代码工作流解耦，全程推进，须在 A0 的"真实数据"里程碑前到达 RC1。

> **每条工作流 = 独立分支（从 main 拉）+ 独立 PR。** 这是对 quality-eval 点名的"PR 超标"问题的直接回应。不要把多条工作流塞进一个 PR。

---

## 1. 横切关注点（所有工作流通用）

### 1.1 新增 cvxpy 依赖（B0 触发，全局影响）

- **用 pixi，禁止 pip/poetry/conda**（CLAUDE.md 铁律）。
- 在 `pixi.toml` 的 dev/default 环境加 `cvxpy`（含开源求解器 ECOS/Clarabel/SCS/OSQP，cvxpy 安装时自带）。
- 验证：`pixi install -e dev` 成功；`pixi run -e dev python -c "import cvxpy; print(cvxpy.__version__)"` 输出版本。
- 提交：单独 commit `chore: add cvxpy dependency for portfolio optimization`。

### 1.2 polars 纪律 + cvxpy 边界

- cvxpy 接口是 numpy / 稀疏矩阵，**不绑 pandas**（这是选它的硬理由）。
- 在 portfolio Allocator 内部：`pl.DataFrame` → 取列 `.to_numpy()` → cvxpy 求解 → 权重 numpy → `frame.with_columns(pl.Series("weight", w))` 回填。**边界隔离，不泄漏 cvxpy 类型到 frame。**

### 1.3 golden 快照重录策略（B0/B1 必读）

详见战略文档 §6.4。要点：
- B0/B1 会让 golden 测试变红（数值变了）→ **这是预期改进，不是回归**。
- 用 `pixi run -e dev test --snapshot` 更新快照；**禁止**调参把数值掰回旧值。
- 每次重录单独 commit，message 记录差异证据，例：`test: re-record golden after volume-constrained fills (Sharpe 1.82→1.45, liquidity cost surfaced)`。

### 1.4 质量门禁（每条工作流完成前）

```
pixi run -e dev check        # lint + fmt + type + test --fast
pixi run -e dev arch-check   # 架构契约
```
- basedpyright strict 零 error、源码零 `# type: ignore`、ruff 全过、新代码有单测（分支覆盖 ≥80%）、37 架构契约全绿。

---

## 2. 工作流 A1：eod 自动 publish-signals（首个，最小）

**目标：** EOD pipeline 每天自动产出可交易信号包（持久化 TradeIntent），让 `/trade/signals/latest` 不再恒空。

**根因回顾：** [eod.py](packages/apps/src/ditto_apps/jobs/flows/eod.py) `_run_strategies`（L75-138）用 `StrategyRunMode.RESEARCH` 跑策略、且不调 `signal_package_publisher`；正确范式见 [publish-signals 命令](packages/apps/src/ditto_apps/cli/commands/strategy.py#L113)：RECOMMENDATION 模式 + `publisher.publish(target=result.target, ...)`。

**Files:**
- Modify: `packages/apps/src/ditto_apps/jobs/flows/eod.py`（`_run_strategies` 函数）
- Modify: `packages/apps/src/ditto_apps/registry/contexts/strategy.py`（确认 bundle 暴露 `signal_package_publisher`；若 eod 上下文与 CLI bundle 不同，需补 publisher 注入）
- Test: `packages/apps/tests/integration/test_eod_flow*.py`（若不存在则新建，镜像现有 flow 测试 fixture）

### Task A1.1：写失败测试 —— eod 产出持久化 intents

**Step 1：** 在 eod flow 集成测试中加测试：调用 `eod_flow(trade_date=...)`（用合成数据 fixture），断言事后 intent store 中存在该策略/该日的 `TradeIntent` 记录。

```python
def test_eod_flow_publishes_trade_intents(eod_test_bundle):
    result = eod_flow(trade_date="2024-01-15", source="tushare")
    assert result["overall_status"] in {"success", "partial"}
    intents = eod_test_bundle.intent_reader.list_intents(
        strategy_id=<published_strategy_id>, signal_date="2024-01-15"
    )
    assert len(intents) > 0  # 当前 RESEARCH 模式不 publish，此处会 FAIL
```

> 注：exact fixture/harness 名称以现有 `test_eod_flow*` / `create_strategy_bundle` 测试为准；执行时先 Read 现有 eod flow 测试与 `create_strategy_bundle` 的返回结构，镜像其 fixture，不要新造。

**Step 2：** `pixi run -e dev pytest packages/apps/tests/integration -k eod -q` → 预期 FAIL（无 intent）。

### Task A1.2：实现 —— eod 切 RECOMMENDATION + publish

**Step 3：** 修改 `_run_strategies`（eod.py:75）：
- `StrategyRunMode.RESEARCH` → `StrategyRunMode.RECOMMENDATION`（L111）。
- 从 bundle 取 `signal_package_publisher`；若为 None，记日志告警并跳过 publish（不阻断策略运行本身）。
- 对每个成功 run_result，调用 `publisher.publish(target=run_result.target, threshold=0.01)`，把 `SignalPackage` 摘要（intents 数、checksum）并入结果 dict。

**Step 4：** `pixi run -e dev pytest packages/apps/tests/integration -k eod -q` → PASS。
**Step 5：** `pixi run -e dev check`（含 lint/type/fast test）。
**Step 6：** Commit（独立分支）：`feat(eod): publish trade signal packages in daily pipeline`。

### Task A1.3（可选加固）：RECOMMENDATION 失败不阻断其他策略

- 已有 try/except 包裹单策略（eod.py:123）；确认 publish 异常也被捕获、记入 result，不影响其他策略与整体 flow。补一个测试：某策略 publish 抛错时，flow 仍返回其他策略结果。

**A1 DoD：** eod_flow 跑完后，`/trade/signals/latest` 能查到当日信号；单策略 publish 失败不阻断 flow。

---

## 3. 工作流 B0：组合优化器（cvxpy + 自有 Allocator）

**目标：** 用凸优化替换"等权天花板"，让组合构建有真实优化能力（MVO 先行，风险预算随后）。

**设计决策（关键）：**
1. **新增 `MeanVarianceAllocator`（实现 `WeightAllocator` Protocol）**，与现有 EqualWeight/InverseVol/Score 并列。保持 frozen dataclass + 纯 polars 风格。
2. **协方差注入而非自取**：portfolio 禁依赖 data（CLAUDE.md）。定义 `CovarianceProvider` Protocol（`covariance(frame: pl.DataFrame) -> np.ndarray`）；默认实现 `DiagonalVolCovariance`（从 `volatility` 列取对角阵）。全协方差由 application 层注入（与 Ditto 一贯的 Protocol 注入一致）。
3. **约束分两类处理（业界标准）：**
   - **硬排除类**（TradabilityConstraint ST/停牌、LiquidityConstraint、MaxPositions）→ 优化**前**用现有 ConstraintChecker 过滤（它们是排除，不是权重约束）。
   - **权重约束类**（MaxWeight 上限、满仓、long-only、可选行业上限）→ 直接写进 cvxpy 凸问题**联合求解**，替换顺序截断。
4. **边界**：polars frame → numpy（μ 向量、Σ 矩阵）→ cvxpy → weights → 回填 "weight" 列。cvxpy 类型不泄漏出 Allocator。

**Files:**
- Create: `packages/portfolio/src/ditto_portfolio/rebalancing/optimization.py`（`CovarianceProvider` Protocol、`DiagonalVolCovariance`、`MeanVarianceAllocator`、`RiskBudgetAllocator`）
- Modify: `packages/portfolio/src/ditto_portfolio/rebalancing/allocation.py`（`__all__` 导出新 Allocator；不删旧的）
- Modify: `packages/portfolio/src/ditto_portfolio/rebalancing/constraints.py`（可选：新增 `ConvexWeightConstraints` 把权重约束表达为 cvxpy 约束；保留顺序 ConstraintChecker 给硬排除类）
- Test: `packages/portfolio/tests/unit/rebalancing/test_optimization_unit.py`（新建）
- DI: `packages/application/src/ditto_application/builders/`（runtime_builder 注入 CovarianceProvider；registry 装配）

### Task B0.1：加 cvxpy 依赖 + 冒烟

- 见 §1.1。`pixi install` + import 冒烟 + 单独 commit。

### Task B0.2：TDD —— CovarianceProvider Protocol + DiagonalVolCovariance

- 测试：给定带 volatility 列的 frame，`DiagonalVolCovariance().covariance(frame)` 返回对角阵 = diag(vol²)，形状 (n,n)，与 instrument 顺序一致。
- 实现 Protocol + 默认实现（纯 numpy）。Commit。

### Task B0.3：TDD —— MeanVarianceAllocator（最小：最小方差，long-only，满仓）

- 测试用例（数值可手算/对照 PyPortfolioOpt 文档值）：
  - 2 资产、给定 μ + Σ → 权重和≈1、均 ≥0；
  - 高 vol 资产权重更低；
  - 空 frame → weight 全 0；
  - 单资产 → 权重=1。
- 实现：`@dataclass(frozen=True) class MeanVarianceAllocator`，字段 `returns_column`、`covariance: CovarianceProvider`、`max_weight: float = 1.0`、`objective: Literal["min_variance","max_sharpe"]`。内部 cp.Variable(n) + cpProblem solve。
- Commit。

### Task B0.4：TDD —— 权重约束联合求解（max_weight + 行业上限）

- 测试：max_weight=0.3 时无单标的超 0.3；industry_column 上限 0.3 时单行业合计 ≤0.3；权重和仍=1。
- 实现：把 max_weight、行业上限写进 cvxpy 约束；对照验证顺序截断版本（constraints.py）会违反 sum=1 的情况，凸解不违反。
- Commit。

### Task B0.5：TDD —— RiskBudgetAllocator（风险预算/风险平价）

- 测试：等风险预算时各资产边际风险贡献相等（数值容差内）。
- 实现：风险平价凸公式（Spinu / 凸近似）。Commit。

### Task B0.6：DI 接线 + 模板接入

- `runtime_builder` / 策略模板（[templates](packages/strategy/src/ditto_strategy/alpha/templates/)）增加 `MeanVarianceAllocator` 选项；CovarianceProvider 由 application/registry 注入（先用 DiagonalVolCovariance，全协方差后续）。
- 测试：一个 ETF 模板用 MVO allocator 跑通 slice。Commit。

### Task B0.7：golden 重录 + 证据

- 跑 golden baseline；预期变红（组合权重变了）。核对新组合合理 → `pixi run -e dev test --snapshot` 重录。
- 单独 commit，message 记录差异（例 Sharpe / 换手变化）。**禁止掰回旧值。**

**B0 DoD：** MVO + 风险预算 Allocator 可用、单测全绿、一个模板接入跑通、golden 重录带证据、cvxpy 依赖落地。

---

## 4. 工作流 B1：成交量约束 fill（回测真实性）

**目标：** 回测大单按成交量 participation rate 截断、支持部分成交，消除"系统性乐观"。

**根因回顾：** [fill.py](packages/backtest/src/ditto_backtest/simulation/fill.py) `AShareFillModel`（L123）连续竞价路径 `_evaluate`/`_fill_market_or_limit`（L160-213）不读 volume；[brokerage.py](packages/execution/src/ditto_execution/brokerage.py) L336-344 **强制 all-or-nothing**（`model_qty != fill_qty` 直接 `raise FillProcessingError`）。仅 `ClosingAuctionFillModel`（L81）有 participation rate。

**设计决策：**
1. **fill 合约支持部分成交**：移除/重构 brokerage.py:336 的 all-or-nothing 强制，允许 `fill_qty < order_qty`，未成交部分进"延迟队列/取消"（先实现"当日未成交部分取消"，延迟回填留 reserved）。
2. **连续竞价加 participation rate**：AShareFillModel 的 MARKET/LIMIT 路径加 `fillable_qty = min(order_qty, participation_rate × bar_volume)`；participation_rate 默认值（如 0.05~0.10，可配）。volume 缺失时的退化策略（保守视为不可成交或用 avg_volume_20d 估）需明确并测试。
3. **保留 all-or-nothing 作为可选旧行为**：用配置开关（`BacktestServiceConfig`），默认新行为；不破坏确定性原则。

**Files:**
- Modify: `packages/execution/src/ditto_execution/brokerage.py`（L336-344 部分成交支持）
- Modify: `packages/backtest/src/ditto_backtest/simulation/fill.py`（AShareFillModel 连续竞价 participation rate + 返回 fill_qty）
- Modify: `packages/backtest/src/ditto_backtest/simulation/` 相关（延迟/取消未成交部分）
- Test: `packages/backtest/tests/unit/simulation/test_fill_unit.py`、`packages/execution/tests/.../test_brokerage_unit.py`
- Config: `BacktestServiceConfig` 加 participation_rate / fill_mode

### Task B1.1：TDD —— fill 合约允许部分成交

- 测试：order_qty=1000、fillable=300 → 返回 fill_qty=300，**不抛错**（当前会 raise）。
- 实现：brokerage.py 移除 all-or-nothing raise；未成交部分按 fill_mode 处理。Commit。

### Task B1.2：TDD —— 连续竞价 participation rate 截断

- 测试：bar_volume=10000、order=2000、participation=0.05 → fill_qty=500；order=300 → fill_qty=300（不超量）。
- 实现：AShareFillModel `_fill_market_or_limit` 加 volume 截断。Commit。

### Task B1.3：TDD —— volume 缺失/ST/涨跌停退化

- 测试：volume=0 → fill_qty=0（保守不成交）；停牌 → 0；集合竞价路径不受影响（仍用 ClosingAuctionFillModel）。
- Commit。

### Task B1.4：配置开关 + DI

- `BacktestServiceConfig` 加 `fill_mode`（`partial` 默认 / `all_or_nothing` 兼容）、`participation_rate`；接入 [jobs/flows/backtest.py](packages/apps/src/ditto_apps/jobs/flows/backtest.py) 的 `build_*` 工厂。
- 测试：两种模式都能跑。Commit。

### Task B1.5：golden 重录 + 证据（重点）

- 跑 golden baseline；预期大面积变红（fill 量变了 → 收益/成本变了）。**逐策略核对**新数值合理（流动性差标的收益下降是正确的）。
- `pixi run -e dev test --snapshot` 重录；commit message 记录关键差异（如某低流动性标的权重/收益下降幅度），作为"流动性成本显性化"证据。
- **绝对禁止**为让 golden 通过而把 participation_rate 调到 1.0 或关掉截断。

**B1 DoD：** 连续竞价有 participation rate 截断、部分成交支持、配置开关、单测全绿、golden 重录带证据、不破坏确定性。

---

## 5. 工作流 A0：前端 ditto-app 接真实后端（capstone，独立仓库）

**目标：** 让 ditto-app 从"MSW mock 原型"变成"能消费真实后端、能记录决策"的可日常使用产品。

**仓库：** `/home/chevy/projects/ditto-app`（React 19 + TanStack + Vite，独立 git 仓库）。

**根因回顾：** [main.tsx](../../ditto-app/src/main.tsx) DEV 下 `worker.start` 全拦截；[api-client.ts](../../ditto-app/src/lib/api-client.ts) `VITE_API_BASE_URL ?? "/api"` 永远 fallback；全树零写路径；约半数页 mock；OpenAPI codegen 装了未用。

**Files（ditto-app 仓库内）：**
- Modify: `ditto-app/src/main.tsx`（MSW 改为可选/仅测试）
- Modify: `ditto-app/.env*`、`ditto-app/vite.config.ts`（VITE_API_BASE_URL + dev proxy → ditto 后端）
- Modify: `ditto-app/src/lib/api-client.ts`（真实 baseURL + 可选 auth header）
- Create: OpenAPI codegen 脚本 + 生成 `src/types/generated/`（消除手写 type 漂移）
- Modify: `src/hooks/`、各 page（补写路径：record fill / update intent status / confirm signal）
- Modify: 去 mock 页面（portfolio/strategy list/backtest list/factor/watchlist/signals/orders/positions/deviation/comparison）

### Task A0.1：环境与代理

- 加 `.env.development`（`VITE_API_BASE_URL`）、`vite.config.ts` dev server proxy → 后端 `http://localhost:<granian port>`。
- MSW 改为仅在显式 `VITE_USE_MOCK=true` 时启用（默认关）。冒烟：前端 dev 起来后，某只读页能打到真实后端。

### Task A0.2：OpenAPI codegen

- ditto 后端导出 OpenAPI（apps 已有 maturity-aware schema）；前端加 `openapi-typescript` 生成脚本，替换手写 `src/types/*.ts` 的手写部分（保留手写 view model）。

### Task A0.3：写路径（决策闭环）

- 实现 `useMutation`：`POST /trade/fills`（record fill）、`PUT /trade/intents/{id}/status`、（可选）confirm signal。补 trading overview"执行调仓"按钮的 onClick。

### Task A0.4：去 mock + 真实页接线

- portfolio / signals inbox / orders / positions / deviation / comparison 接真实 API；删除硬编码 mock 常量。

### Task A0.5：端到端冒烟（与后端联调）

- 起后端（granian）+ 前端 dev：跑一次 A1 的 eod publish → 前端 signals inbox 看到真实信号 → 录一笔 fill → deviation 页看到偏差。这是"首次真实使用"的预演。

**A0 DoD：** 前端连真实后端、有写路径、关键页去 mock、OpenAPI codegen 生效、端到端冒烟通过。

---

## 6. 工作流 B3：真实数据 promotion（治理，进行中）

**目标：** 14 个必需数据集到达 promotion-ready，满足 RC1 hard-gate（`rc1_real_data_acceptance.py --real-data --require-promoted` 返回 0）。

**性质：** 非纯代码——需真实环境 + governance（promotion 唯一路径是 `ReviewDatasetPromotionEvidenceHandler`，绝不自造通过）。

**Checklist（非 TDD，治理流程）：**
- [ ] 逐数据集跑 `ditto ops promotion-collect`（客观收集 3 条 criteria 证据）。
- [ ] 逐数据集 `ditto ops promotion-review`（reviewer evidence 写入，handler 评估）。
- [ ] 14 数据集 maturity 达 initial-focus/stable。
- [ ] 真实环境跑真实数据 E2E 全绿。
- [ ] `rc1_real_data_acceptance.py --real-data --require-promoted` 返回 0。

> 这是 A0 "看到真实数据"里程碑的硬前置。与代码工作流并行推进。

---

## 7. 汇合点验收（Wave 1 Definition of Done）

> 在一个真实交易日：打开 ditto-app → 看到**当天基于 promotion-ready 真实数据**的选股信号（A1 + B3）→ 组合由**真实 MVO 优化器**构建（B0）→ 记录决策（A0 写路径）→ 事后看 deviation 复盘（A0）。回测数值已含**成交量约束**真实成本（B1）。

**全局门禁：**
- [ ] `pixi run -e dev ci` 全绿（lint/fmt/type/test/golden/arch）。
- [ ] 37 架构契约全绿；源码零 `# type: ignore`。
- [ ] 5 条工作流各为独立 PR、规模可控（回应 PR 超标问题）。
- [ ] golden 重录 commit 带前后差异证据（B0/B1）。
- [ ] 战略文档 §5.2 分阶段优先级已与 capability-maturity.md 同步。

---

## 8. 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| cvxpy 求解器在某些病态 Σ 上不收敛 | B0 阻塞 | 加 fallback（收敛失败 → 退化到 InverseVolAllocator）+ 日志；测试病态输入 |
| B1 fill 合约重构波及面大（brokerage + fill + golden） | B1 超期 | 用 fill_mode 开关保留旧行为；先单测后集成；golden 分策略逐个核对 |
| A0 跨仓库联调（ditto + ditto-app） | A0 阻塞 | A0.5 端到端冒烟前置；后端先固定 API 契约（OpenAPI） |
| B3 治理依赖真实环境/人工 review | 阻塞"真实数据"里程碑 | 尽早启动、并行推进；不阻塞代码工作流 |
| golden 重录误判（把真回归当改进接受） | 掩盖 bug | 重录前逐策略人工核对数值方向合理性；差异写进 commit message 可追溯 |

---

## 执行交接

本计划已保存至 [2026-06-24-wave1-implementation-plan.md](2026-06-24-wave1-implementation-plan.md)。

**两种执行方式（选其一）：**

1. **Subagent 驱动（本会话）** —— 我按工作流顺序，每条用 `superpowers:subagent-driven-development` 派 fresh subagent 逐 task 执行、task 间我做 code review。适合快速迭代、实时纠偏。
2. **并行会话（独立）** —— 在新会话/worktree 用 `superpowers:executing-plans` 批量执行 + 检查点。适合大块独立推进。

> 因 A0 在独立仓库（ditto-app），建议 A1/B0/B1/B3 在 ditto 仓库推进，A0 单独在 ditto-app 仓库推进。

# B0 · 组合优化器（cvxpy + 自有 Allocator）实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 用凸优化替换"等权天花板"——新增基于 cvxpy 的 `MeanVarianceAllocator` 与 `RiskBudgetAllocator`，权重约束凸联合求解，让组合构建有真实优化能力。

**Architecture:** portfolio 包新增 `optimization.py`，定义 `CovarianceProvider` Protocol（注入，保持 portfolio 零 data 依赖）+ `MeanVarianceAllocator`/`RiskBudgetAllocator`（实现现有 `WeightAllocator` Protocol，与 EqualWeight 并列）。硬排除类约束（ST/停牌/流动性/最大持仓数）优化前用现有 `ConstraintChecker` 过滤；权重约束（max_weight/行业上限/满仓/long-only）写进 cvxpy 凸问题联合求解，替换顺序截断。application `template_builders.build_portfolio_stages` 增加 MVO 选项。

**Tech Stack:** Python / polars / **cvxpy（新增）** / numpy / pytest。

**战略索引:** [wave1 主计划](2026-06-24-wave1-implementation-plan.md) §1/§3；[战略定位](2026-06-24-strategic-positioning-and-functional-gap-analysis.md) §6.3（cvxpy 选型理由）。

> **⚠️ 新增依赖：** cvxpy 须人工批准（CLAUDE.md）。用 pixi 添加（见 Task B0.0）。cvxpy 接口是 numpy，**不绑 pandas**，与 Ditto polars-only 兼容。
> **⚠️ 分支基线注意：** 同 A1，基于含 dev 工作的基线。

---

## 现状实证

- [allocation.py](../../packages/portfolio/src/ditto_portfolio/rebalancing/allocation.py)：`WeightAllocator` Protocol（`allocate(frame: pl.DataFrame) -> pl.DataFrame`，加 `weight` 列）；现有 `EqualWeightAllocator`(L38)/`InverseVolAllocator`(L59)/`ScoreWeightAllocator`(L112)，全 frozen dataclass + 纯 polars。`AllocationStage`(L198) 是 Pipeline 适配器。
- [constraints.py](../../packages/portfolio/src/ditto_portfolio/rebalancing/constraints.py)：`ConstraintChecker.check`(L383) 按 priority **顺序**执行约束（L400-405），每条 `check` 返回 `ConstraintAdjustment` 截断/缩放权重——非凸，多约束冲突时 `sum≠1` 可能反复破坏。
- [runtime_builder.py](../../packages/application/src/ditto_application/builders/runtime_builder.py) `_build_pipeline`(L110) 调 `build_portfolio_stages(spec)`（来自 `template_builders`）组装 portfolio stages——**allocator 选择在 `template_builders`，不在 runtime_builder**。

---

## Task B0.0：加 cvxpy 依赖 + 冒烟（须批准）

**Step 1：** 在 `pixi.toml` 的 `dev` 与 `default` 环境加 `cvxpy`（开源求解器 ECOS/Clarabel/SCS/OSQP 随 cvxpy 安装）。
**Step 2：** `pixi install -e dev`。
**Step 3：** 冒烟：`pixi run -e dev python -c "import cvxpy as cp; import numpy as np; w=cp.Variable(3); p=cp.Problem(cp.Minimize(cp.quad_form(w, np.eye(3))), [cp.sum(w)==1, w>=0]); p.solve(); print(w.value)"` → 输出近似 `[0.33,0.33,0.33]`。
**Step 4：** Commit：`chore: add cvxpy dependency for portfolio optimization`。

---

## Task B0.1：TDD — CovarianceProvider Protocol + DiagonalVolCovariance

**Files:**
- Create: `packages/portfolio/src/ditto_portfolio/rebalancing/optimization.py`
- Test: `packages/portfolio/tests/unit/rebalancing/test_optimization_unit.py`

**Step 1（RED）：** 测试 `DiagonalVolCovariance` 给定带 `volatility` 列的 frame → 返回 `np.ndarray` 形状 (n,n)，对角 = vol²，顺序与 `instrument_id` 列一致；空 frame → 形状 (0,0)。
**Step 2：** `pixi run -e dev pytest packages/portfolio/tests/unit/rebalancing/test_optimization_unit.py -k covariance -q` → FAIL。
**Step 3（GREEN）：** 实现：

```python
class CovarianceProvider(Protocol):
    def covariance(self, frame: pl.DataFrame) -> np.ndarray: ...

@dataclass(frozen=True)
class DiagonalVolCovariance:
    vol_column: str = "volatility"
    def covariance(self, frame: pl.DataFrame) -> np.ndarray:
        if frame.is_empty():
            return np.zeros((0, 0))
        vol = frame[self.vol_column].to_numpy().astype(float)
        vol = np.nan_to_num(vol, nan=0.0)
        return np.diag(vol ** 2)
```

**Step 4：** 测试 → PASS。**Step 5：** Commit `feat(portfolio): add CovarianceProvider protocol + diagonal vol estimator`。

---

## Task B0.2：TDD — MeanVarianceAllocator（最小方差，long-only，满仓）

**Step 1（RED）：** 测试（μ + Σ 手算/对照）：
- 2 资产、给定 μ + Σ → `allocate` 返回 frame 含 `weight` 列，权和 ≈ 1，均 ≥ 0；
- 高 vol 资产权重更低（最小方差）；
- 空 frame → weight 全 0；单资产 → 权重 ≈ 1。

**Step 2：** FAIL。
**Step 3（GREEN）：**

```python
@dataclass(frozen=True)
class MeanVarianceAllocator:
    returns_column: str = "score"
    covariance: CovarianceProvider
    max_weight: float = 1.0
    cash_target: float = 0.0

    def allocate(self, frame: pl.DataFrame) -> pl.DataFrame:
        n = frame.height
        if n == 0:
            return frame.with_columns(pl.lit(0.0).alias("weight"))
        sigma = self.covariance.covariance(frame)
        w = cp.Variable(n)
        constraints = [w >= 0, cp.sum(w) == 1.0 - self.cash_target]
        if self.max_weight < 1.0:
            constraints.append(w <= self.max_weight)
        prob = cp.Problem(cp.Minimize(cp.quad_form(w, cp.psd_wrap(sigma))), constraints)
        prob.solve()
        weights = np.clip(np.asarray(w.value, dtype=float), 0.0, None)
        return frame.with_columns(pl.Series("weight", weights))
```

> 收敛失败（`w.value is None`）→ fallback 到 `InverseVolAllocator`（依赖项注入或内部退化）+ `logger.warning`。
**Step 4：** PASS。**Step 5：** Commit `feat(portfolio): add MeanVarianceAllocator (min-variance, long-only)`。

---

## Task B0.3：TDD — 凸权重约束联合求解（max_weight + 行业上限）

**Step 1（RED）：** 测试：
- `max_weight=0.3` → 无单标的 > 0.3，权和 = 1；
- 带 `industry` 列、`max_industry_weight=0.3` → 单行业合计 ≤ 0.3，权和 = 1；
- 对照验证：同样输入下顺序截断版（constraints.py `ConstraintChecker`）在多约束冲突时 `sum(weight)` 可能 ≠ 1，凸解必 = 1。

**Step 2：** FAIL。
**Step 3（GREEN）：** 扩展 `MeanVarianceAllocator`（或新增 `IndustryMaxWeightMixin`），把行业上限表达为 cvxpy 约束：按 industry 分组 `cp.sum(w[group]) <= cap`。max_weight、满仓、long-only、行业上限**一次凸求解联合满足**。
**Step 4：** PASS。**Step 5：** Commit `feat(portfolio): joint convex constraints (max_weight + industry cap)`。

---

## Task B0.4：TDD — RiskBudgetAllocator（风险平价）

**Step 1（RED）：** 测试：等风险预算 → 各资产边际风险贡献相等（数值容差内，如 `|rc_i - rc_j| < 1e-4`）；权和 = 1。
**Step 2：** FAIL。
**Step 3（GREEN）：** 实现风险平价凸公式（Spinu 2013 凸近似：`min 0.5 wᵀΣw - Σ b_i log(w_i)`，s.t. w>0），归一化。收敛失败 fallback InverseVol。
**Step 4：** PASS。**Step 5：** Commit `feat(portfolio): add RiskBudgetAllocator (risk parity)`。

---

## Task B0.5：集成 — template_builders + spec + DI

**Step 1：** Read `packages/application/src/ditto_application/builders/template_builders.py` `build_portfolio_stages`，理解当前 allocator 如何由 spec 选择（EqualWeight/Score/InverseVol）。
**Step 2：** Read `ditto_strategy/alpha/specs.py`，确认是否需要新增 spec 字段（如 `allocator: Literal["equal_weight","score","inverse_vol","mean_variance","risk_budget"]`）。
**Step 3（RED）：** 测试 `build_portfolio_stages` 在 spec 选 `mean_variance` 时返回含 `MeanVarianceAllocator`（经 `AllocationStage`）的 stages；CovarianceProvider 由 application 注入（默认 `DiagonalVolCovariance`）。
**Step 4（GREEN）：** 在 `build_portfolio_stages` 增加 MVO/RiskBudget 分支；application 层构造 `DiagonalVolCovariance`（全协方差后续由 data 注入）注入 allocator。
**Step 5：** 测试：一个 ETF 模板用 MVO allocator 跑通 slice（集成测试）。
**Step 6：** `pixi run -e dev check` + `arch-check`。
**Step 7：** Commit `feat(application): wire MeanVarianceAllocator into strategy templates`。

---

## Task B0.6：golden 重录 + 证据（关键，参见主计划 §1.3）

**Step 1：** `pixi run -e dev pytest packages/backtest/tests/integration/test_golden_baseline.py -q` → 预期变红（MVO 组合 ≠ 等权）。
**Step 2：** **逐策略核对**新组合合理（权重分散度、换手、收益方向）。
**Step 3：** `pixi run -e dev test --snapshot` 重录 golden。
**Step 4：** Commit，message 记录差异证据：`test: re-record golden for MVO portfolio (equal-weight baseline → optimized; <key metric delta>)`。
> **禁止**为让 golden 通过而回退到等权或放宽约束。

---

## DoD

- [ ] `MeanVarianceAllocator` + `RiskBudgetAllocator` 可用、实现 `WeightAllocator` Protocol。
- [ ] 权重约束凸联合求解（sum=1 保证），替代顺序截断。
- [ ] portfolio 零 data 依赖（CovarianceProvider 注入）；cvxpy 类型不泄漏出 Allocator。
- [ ] 至少一个模板接入 MVO 跑通；单测 + 集成测试全绿。
- [ ] golden 重录带证据；`check` + `arch-check` 全绿。

## 风险

| 风险 | 缓解 |
|---|---|
| cvxpy 在病态 Σ 上不收敛（`w.value is None`） | 收敛失败 fallback `InverseVolAllocator` + warning；测试病态输入（共线/零方差） |
| 全协方差缺失（只有 vol 列）→ MVO 退化为对角 | Wave 1 用 `DiagonalVolCovariance`；全协方差由 data 层后续注入（P1/P2） |
| 基数约束（恰好 N 只）非凸 | Wave 1 不做；MaxPositions 作为优化**前**硬排除（保留 ConstraintChecker），不做 cvxpy MIP |
| cvxpy 求解慢影响回测 | n 通常 ≤ 数十（ETF/选股池），QP 毫秒级；benchmark 确认无显著回归 |

# R4a cvxpy 组合优化实施计划（垂直切片）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 交付第一个真实凸求解器全链路——`ShrinkageCovarianceProvider`（features，Ledoit-Wolf）经 application 注入 → `ConstrainedMVOSolver`（portfolio，cvxpy，硬约束烘进 + L1 交易成本罚项）→ EngineLoop A/B golden 对照 EqualWeight。

**Architecture:** 协方差在 features 估计（计算平面，PIT），经 application 注入 portfolio 的 `CovarianceProvider` Protocol；cvxpy 求解器是 portfolio 新 `WeightAllocator` 实现；`ConstraintCvxpyAdapter` 把既有 7 个 dataclass Constraint 翻译成 cvxpy 表达式烘进问题。**cvxpy 限 portfolio 内，不向上泄漏**（架构测试守）。详见 [R4 设计](2026-08-04-r4-portfolio-risk-design.md) §3。

**Tech Stack:** Python 3.13、polars、numpy、**cvxpy（已批准 2026-08-04，portfolio 新依赖）**、pixi、TDD。

**纪律（CLAUDE.md）:** TDD(RED→GREEN→REFACTOR)；pixi 加依赖；orjson/polars；禁 TYPE_CHECKING 解循环；每 Task 后 `pixi run -e dev check`；commit 前 `git status` 干净。

**范围:** 垂直切片 Task 1-6（一个 cvxpy 求解器全链路）。Task 7+（CVaROptimizer / RiskParityAllocator / Black-Litterman）切片验证后做。

**关键事实（已勘探）:**
- `CovarianceProvider` Protocol：`packages/portfolio/src/ditto_portfolio/rebalancing/optimization.py:24`，方法 `covariance(frame: pl.DataFrame) -> npt.NDArray[np.float64]`。
- `MeanVarianceAllocator`（:48）默认 `covariance: CovarianceProvider = DiagonalVolCovariance`。
- DI 选点：`application/builders/_portfolio_stage_builder.py:56-65` 按 kind 选 allocator。
- 协方差估算落点：`features/evaluation/metrics/`（`orthogonalization.py:271` 已有 `_covariance_matrix`）。
- 测试范式：`portfolio/tests/unit/rebalancing/test_optimization_unit.py`。

---

## 前置：分支
从 `main` 拉 `feat/r4a-cvxpy-optimization`。

---

## Task 1: cvxpy 依赖 + 求解器模块骨架 + 泄漏守卫

**Files:**
- Modify: `pixi.toml`（`[dependencies]`）
- Modify: `packages/portfolio/pyproject.toml`（deps）
- Create: `packages/portfolio/src/ditto_portfolio/rebalancing/cvxpy_solvers/__init__.py`
- Test: `packages/portfolio/tests/unit/test_cvxpy_leak_guard_unit.py`

**Step 1: 写失败测试（cvxpy 仅 portfolio 内可用）**

```python
# packages/portfolio/tests/unit/test_cvxpy_leak_guard_unit.py
"""cvxpy 不得泄漏出 portfolio 包。"""
from __future__ import annotations

import pathlib


def test_cvxpy_only_imported_in_portfolio() -> None:
    root = pathlib.Path("packages")
    offenders: list[str] = []
    for pkg in root.iterdir():
        if not pkg.is_dir() or pkg.name == "portfolio":
            continue
        for py in (pkg / "src").rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "import cvxpy" in text or "from cvxpy" in text:
                offenders.append(str(py))
    assert not offenders, f"cvxpy 泄漏到 portfolio 之外: {offenders}"
```

**Step 2: 验证失败**

Run: `pixi run -e dev pytest packages/portfolio/tests/unit/test_cvxpy_leak_guard_unit.py -v`
Expected: PASS（暂无 cvxpy；测试先行作为持续守卫）。

**Step 3: 加 cvxpy 依赖**

`pixi.toml [dependencies]` 追加：
```toml
cvxpy = ">=1.5,<2"
```
`pixi install -e dev`。

`packages/portfolio/pyproject.toml` 的 `dependencies` 追加 `"cvxpy"`。

**Step 4: 创建求解器子包骨架**

`rebalancing/cvxpy_solvers/__init__.py`：
```python
"""cvxpy-based convex portfolio solvers（仅 portfolio 内使用）。"""
```

**Step 5: 验证**

Run: `pixi run -e dev pytest packages/portfolio/tests/unit/test_cvxpy_leak_guard_unit.py -v && pixi run -e dev type`
Expected: PASS + type 0。

**Step 6: Commit**

```bash
git add pixi.toml pixi.lock packages/portfolio/pyproject.toml packages/portfolio/src/ditto_portfolio/rebalancing/cvxpy_solvers packages/portfolio/tests/unit/test_cvxpy_leak_guard_unit.py
git commit -m "feat(portfolio): add cvxpy dep + cvxpy_solvers skeleton + leak guard"
```

---

## Task 2: ShrinkageCovarianceProvider（features，Ledoit-Wolf）

**Files:**
- Create: `packages/features/src/ditto_features/evaluation/metrics/risk_model.py`
- Test: `packages/features/tests/unit/evaluation/test_risk_model_unit.py`

> 实现既有 `CovarianceProvider` Protocol 的结构形状（`covariance(frame)->ndarray`），**不 import portfolio**（结构化 Protocol，duck-typed）。Ledoit-Wolf 常数相关收缩：`Σ_shrink = δ·Σ_sample + (1-δ)·F`，F 为常数相关先验，δ 由数据自动求解。

**Step 1: 写失败测试**

```python
# packages/features/tests/unit/evaluation/test_risk_model_unit.py
"""ShrinkageCovarianceProvider：正定、对称、对角为方差。"""
from __future__ import annotations

import numpy as np
import polars as pl

from ditto_features.evaluation.metrics.risk_model import ShrinkageCovarianceProvider


def test_shrinkage_covariance_is_symmetric_psd() -> None:
    returns = pl.DataFrame({
        "instrument_id": ["A", "B", "C"] * 5,
        "r": [0.01, 0.02, -0.01, 0.02, 0.0, 0.03, -0.01, 0.01, 0.02, 0.0, -0.02, 0.01, 0.03, -0.01, 0.0],
    })
    provider = ShrinkageCovarianceProvider(returns_col="r", lookback=5)
    cov = provider.covariance(pl.DataFrame({"instrument_id": ["A", "B", "C"]}))
    assert cov.shape == (3, 3)
    assert np.allclose(cov, cov.T)                       # 对称
    assert np.all(np.linalg.eigvalsh(cov) >= -1e-10)     # 半正定
    assert np.all(np.diag(cov) >= 0)                     # 对角非负
```

**Step 2: 验证失败**

Run: `pixi run -e dev pytest packages/features/tests/unit/evaluation/test_risk_model_unit.py -v`
Expected: FAIL（模块不存在）

**Step 3: 实现 Ledoit-Wolf 收缩**

`risk_model.py`：
```python
"""PIT-aware 协方差估计（Ledoit-Wolf 常数相关收缩），实现 CovarianceProvider 形状。"""
from __future__ import annotations

import numpy as np
import numpy.typing as npt
import polars as pl


class ShrinkageCovarianceProvider:
    """从 returns 历史估计收缩协方差；covariance(frame) 返回 frame 行序的 n×n 矩阵。"""

    def __init__(self, *, returns_col: str, lookback: int) -> None:
        self._returns_col = returns_col
        self._lookback = lookback

    def covariance(self, frame: pl.DataFrame) -> npt.NDArray[np.float64]:
        instruments = frame["instrument_id"].to_list()
        # TODO: 从 PIT 物化 returns 读取最近 self._lookback 日（执行时接 features 物化读路径）
        sample = self._load_returns_matrix(instruments)  # T×n
        return self._ledoit_wolf(sample)

    def _load_returns_matrix(self, instruments: list[str]) -> npt.NDArray[np.float64]:
        ...  # 执行时实现：PIT-aware 读取，避免前瞻

    @staticmethod
    def _ledoit_wolf(sample: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        t, n = sample.shape
        mean = sample.mean(axis=0)
        x = sample - mean
        sample_cov = (x.T @ x) / t
        # 常数相关先验 F
        std = np.sqrt(np.diag(sample_cov))
        corr = sample_cov / np.outer(std, std)
        rho = corr[np.triu_indices(n, 1)].mean()
        f = rho * np.outer(std, std)
        np.fill_diagonal(f, std**2)
        # 收缩强度 δ（Ledoit-Wolf 闭式）
        delta = ShrinkageCovarianceProvider._shrinkage_intensity(x, sample_cov, f, t)
        return delta * f + (1 - delta) * sample_cov

    @staticmethod
    def _shrinkage_intensity(
        x: npt.NDArray[np.float64], sample_cov: npt.NDArray[np.float64],
        f: npt.NDArray[np.float64], t: int,
    ) -> float:
        ...  # 闭式 δ（执行时补；范围 [0,1]）
```

> ⚠️ `_load_returns_matrix`（PIT 读路径）与 `_shrinkage_intensity`（闭式 δ）执行时按 Ledoit-Wolf 2004 公式补全；测试用注入的小 returns 矩阵验证对称/PSD/收缩 δ∈[0,1]。

**Step 4: 验证通过**

Run: `pixi run -e dev pytest packages/features/tests/unit/evaluation/test_risk_model_unit.py -v && pixi run -e dev arch-check`
Expected: PASS + arch 合规（features 不 import portfolio）。

**Step 5: Commit**

```bash
git add packages/features/src/ditto_features/evaluation/metrics/risk_model.py packages/features/tests/unit/evaluation/test_risk_model_unit.py
git commit -m "feat(features): add ShrinkageCovarianceProvider (Ledoit-Wolf, PIT-aware)"
```

---

## Task 3: ConstraintCvxpyAdapter（7 约束 → cvxpy）

**Files:**
- Create: `packages/portfolio/src/ditto_portfolio/rebalancing/cvxpy_solvers/constraints_adapter.py`
- Test: `packages/portfolio/tests/unit/rebalancing/test_constraints_adapter_unit.py`

> 把既有 7 个 dataclass `Constraint`（`rebalancing/constraints.py`）翻译成 cvxpy 约束列表。MaxPositions 用两步法（MVP，不在此 adapter 内做基数，由 solver 先 top-N）。

**Step 1: 写失败测试（每约束一测）**

```python
# packages/portfolio/tests/unit/rebalancing/test_constraints_adapter_unit.py
"""ConstraintCvxpyAdapter：每约束翻译成正确 cvxpy 表达式。"""
from __future__ import annotations

import cvxpy as cp
import numpy as np
import polars as pl

from ditto_portfolio.rebalancing.constraints import MaxWeightConstraint, IndustryMaxWeightConstraint
from ditto_portfolio.rebalancing.cvxpy_solvers.constraints_adapter import ConstraintCvxpyAdapter


def test_max_weight_translates() -> None:
    frame = pl.DataFrame({"instrument_id": ["A", "B"], "industry": ["x", "y"]})
    w = cp.Variable(2)
    cons = ConstraintCvxpyAdapter(frame, [MaxWeightConstraint(max_weight=0.5)]).to_cvxpy(w)
    val = cp.Problem(cp.Minimize(cp.sum(w)), [w >= 0, cp.sum(w) == 1, *cons]).solve()
    assert np.all(w.value <= 0.5 + 1e-6)
```

**Step 2: 验证失败 → Step 3: 实现 adapter**

`constraints_adapter.py`：遍历 `Constraint` 列表，按类型 dispatch（MaxWeight→`w<=cap`；MinWeight→`w>=floor`；IndustryMaxWeight→按 industry 分组求和 `<=cap`；Liquidity→`w<=cap·ADV`；Tradability→掩码 `w[i]=0`；MaxTurnover→`cp.norm(w-w_prev,1)<=τ`）。MaxPositions 标记给 solver 两步法处理（adapter 不直接产基数约束）。

**Step 4: 验证通过**

Run: `pixi run -e dev pytest packages/portfolio/tests/unit/rebalancing/test_constraints_adapter_unit.py -v`
Expected: PASS（7 约束子集，每约束至少一断言）。

**Step 5: Commit**

```bash
git add packages/portfolio/src/ditto_portfolio/rebalancing/cvxpy_solvers/constraints_adapter.py packages/portfolio/tests/unit/rebalancing/test_constraints_adapter_unit.py
git commit -m "feat(portfolio): add ConstraintCvxpyAdapter (7 constraints -> cvxpy)"
```

---

## Task 4: ConstrainedMVOSolver（最小方差 + 风险预算，全凸）

**Files:**
- Create: `packages/portfolio/src/ditto_portfolio/rebalancing/cvxpy_solvers/mvo_solver.py`
- Test: `packages/portfolio/tests/unit/rebalancing/test_mvo_solver_unit.py`

> MVP 做 **最小方差** 与 **风险预算（max return s.t. wᵀΣw ≤ risk_budget）** 两个全凸变体 + L1 交易成本罚项。max-Sharpe（分式规划）用 Schaible 变换，留 Task 7+。

**Step 1: 写失败测试（已知解对照）**

```python
# packages/portfolio/tests/unit/rebalancing/test_mvo_solver_unit.py
"""ConstrainedMVOSolver：最小方差解析解对照 + 约束满足 + 全金。"""
from __future__ import annotations

import numpy as np
import polars as pl
from unittest.mock import MagicMock

from ditto_portfolio.rebalancing.cvxpy_solvers.mvo_solver import ConstrainedMVOSolver


def test_min_variance_unconverged_to_inverse_variance() -> None:
    """对角协方差下，最小方差 ≈ 逆方差（对照 MeanVarianceAllocator 行为）。"""
    frame = pl.DataFrame({"instrument_id": ["A", "B"], "volatility": [0.1, 0.2]})
    cov_provider = MagicMock()
    cov_provider.covariance.return_value = np.diag([0.01, 0.04])  # 对角
    solver = ConstrainedMVOSolver(covariance=cov_provider, turnover_penalty=0.0)
    out = solver.allocate(frame)
    w = out["weight"].to_numpy()
    assert np.isclose(w.sum(), 1.0, atol=1e-4)         # 全金
    assert w[0] > w[1]                                   # 低波动者权重大
    # 逆方差解 [0.8, 0.2]
    assert np.allclose(w, [0.8, 0.2], atol=1e-2)


def test_max_weight_constraint_respected() -> None:
    ...
```

**Step 2: 验证失败 → Step 3: 实现 solver**

`mvo_solver.py`：
```python
"""cvxpy 凸 MVO 求解器（最小方差 / 风险预算 + L1 交易成本）。"""
from __future__ import annotations

import cvxpy as cp
import numpy as np
import polars as pl

from ditto_portfolio.rebalancing.optimization import CovarianceProvider


class ConstrainedMVOSolver:
    def __init__(
        self,
        *,
        covariance: CovarianceProvider,
        turnover_penalty: float = 0.0,
        previous_weights: np.ndarray | None = None,
    ) -> None:
        self._cov = covariance
        self._tc = turnover_penalty
        self._prev = previous_weights

    def allocate(self, frame: pl.DataFrame) -> pl.DataFrame:
        sigma = self._cov.covariance(frame)
        n = sigma.shape[0]
        w = cp.Variable(n)
        risk = cp.quad_form(w, cp.psd_wrap(sigma))
        tc = self._tc * cp.norm(w - (self._prev if self._prev is not None else np.zeros(n)), 1)
        objective = cp.Minimize(risk + tc)
        constraints = [w >= 0, cp.sum(w) == 1]  # + adapter.to_cvxpy(w, ...)
        cp.Problem(objective, constraints).solve()
        return frame.with_columns(weight=pl.Series(w.value))
```

> `allocate` 签名与既有 `WeightAllocator.allocate(frame)->frame` 一致；注入 `CovarianceProvider`。执行时把 adapter 约束并入 `constraints`。

**Step 4: 验证通过**

Run: `pixi run -e dev pytest packages/portfolio/tests/unit/rebalancing/test_mvo_solver_unit.py -v && pixi run -e dev check`
Expected: PASS + check 全绿。

**Step 5: Commit**

```bash
git add packages/portfolio/src/ditto_portfolio/rebalancing/cvxpy_solvers/mvo_solver.py packages/portfolio/tests/unit/rebalancing/test_mvo_solver_unit.py
git commit -m "feat(portfolio): add ConstrainedMVOSolver (cvxpy min-variance + risk-budget + L1 turnover)"
```

---

## Task 5: DI 注入（application _portfolio_stage_builder 选 cvxpy allocator）

**Files:**
- Modify: `packages/application/src/ditto_application/builders/_portfolio_stage_builder.py`
- Modify: application providers（注入 `ShrinkageCovarianceProvider`）
- Test: `packages/application/tests/unit/builders/test_portfolio_stage_cvxpy_unit.py`

> 在 allocator 选择处加 `ConstrainedMVOSolver` 分支（kind="mvo"），注入 `ShrinkageCovarianceProvider`（由 features 经 Protocol 提供，application 装配）。遵守 application 不直 import cvxpy（cvxpy 在 portfolio 内；application 只 import `ConstrainedMVOSolver` 类，cvxpy 是 portfolio 的传递依赖，不向上 import cvxpy 符号）。

**Step 1: 写失败测试（kind="mvo" 产出 ConstrainedMVOSolver）**

```python
# packages/application/tests/unit/builders/test_portfolio_stage_cvxpy_unit.py
"""_portfolio_stage_builder：kind='mvo' 选 ConstrainedMVOSolver + 注入协方差。"""
from ditto_application.builders._portfolio_stage_builder import build_allocator  # 按实际函数名核对


def test_mvo_kind_returns_cvxpy_solver() -> None:
    allocator = build_allocator(kind="mvo", covariance=object())  # 注入 provider
    assert allocator.__class__.__name__ == "ConstrainedMVOSolver"
```

**Step 2: 验证失败 → Step 3: 接线**（在 stage_builder 加 `"mvo"` 分支 + provider 注入参数；provider 由 dishka 从 features 提供）。

**Step 4: 验证**

Run: `pixi run -e dev pytest packages/application/tests/unit/builders/test_portfolio_stage_cvxpy_unit.py -v && pixi run -e dev arch-check`
Expected: PASS + arch 合规（application 未 import cvxpy）。

**Step 5: Commit**

```bash
git add packages/application/src/ditto_application/builders/_portfolio_stage_builder.py packages/application/src/ditto_application/providers*.py packages/application/tests/unit/builders/test_portfolio_stage_cvxpy_unit.py
git commit -m "feat(application): wire ConstrainedMVOSolver + ShrinkageCovarianceProvider injection"
```

---

## Task 6: A/B 集成 golden（cvxpy MVO vs EqualWeight 回测对照）

**Files:**
- Test: `packages/backtest/tests/integration/test_mvo_vs_equal_weight_golden.py`

> 跑同一策略/spec 两次：一次 EqualWeight、一次 MVO（kind="mvo"），断言 MVO 实例可跑通全链路、产出合理 EngineResult（波动率/权重满足约束），并与 EqualWeight 结果不同（证明 cvxpy 路径生效）。**不断言 MVO 一定更优**（那是策略问题，非工程）。

**Step 1: 写 golden 测试**

```python
# packages/backtest/tests/integration/test_mvo_vs_equal_weight_golden.py
"""cvxpy MVO 全链路：可跑通 + 满足约束 + 与 EqualWeight 结果不同。"""
```
（构造最小 strategy spec + fixture returns，跑两次 EngineLoop，断言权重满足 max_weight、Σw=1，且两组 weight 不同。）

**Step 2-4: 实现/验证**

Run: `pixi run -e dev pytest packages/backtest/tests/integration/test_mvo_vs_equal_weight_golden.py -v && pixi run -e dev check`
Expected: PASS + check 全绿（arch 37 contracts + type 0）。

**Step 5: Commit**

```bash
git add packages/backtest/tests/integration/test_mvo_vs_equal_weight_golden.py
git commit -m "test(backtest): MVO vs EqualWeight A/B golden (cvxpy path end-to-end)"
```

---

## Task 7+（垂直切片验证后）

- **Task 7**：`CVaROptimizer`（Rockafellar-Uryasev 线性公式，min CVaR s.t. 全金+约束）+ 单元对照（已知尾部解）。
- **Task 8**：`RiskParityAllocator`（Spinu 凸风险平价）+ 等风险贡献断言。
- **Task 9**：`BlackLittermanPrior`（views 融合后验 μ，前置 MVO）+ 最大 Sharpe（Schaible 凸变换）。
- **Task 10**：MaxPositions 两步法（先 top-N 再 QP）或 MIQP（ECOS_BB）。
- **Task 11**：协方差 lookback 敏感性 + 求解器性能基线（大 universe）。

---

## 验证命令速查

```bash
pixi run -e dev arch-check          # cvxpy 不泄漏（Task 1 守卫 + importlinter）
pixi run -e dev type                # 0 error
pixi run -e dev test --unit --fast  # 全绿
pixi run -e dev check               # 每 Task 后
```

## 关键风险与对策

| 风险 | 对策 |
|------|------|
| cvxpy 求解器在大 universe 慢 | MVP 两步法 MaxPositions；ECOS/CLARABEL 默认；个股 universe 用因子模型降维（R4b） |
| 收缩 δ 闭式实现错 | 用 Ledoit-Wolf 2004 公式 + δ∈[0,1] 断言 + 与 sklearn `LedoitWolf` 交叉对照（dev 依赖） |
| 协方差 PIT 前瞻风险 | `_load_returns_matrix` 严格 knowledge_date 对齐；PIT 单测 |
| application 误 import cvxpy | Task 1 泄漏守卫测试 + importlinter |
| max-Sharpe 非凸 | MVP 不做；Task 9 用 Schaible 凸变换 |

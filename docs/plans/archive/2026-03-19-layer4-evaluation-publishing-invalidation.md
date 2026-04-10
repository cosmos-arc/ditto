# Layer 4: 评估 + 发布安全 + 失效传播 — 实施计划

> **状态**: ✅ 全部完成（2026-03-19）
> **Commits**: `9e4f5b9d`, `b15cba2d`, `954e9772`, `c0946079`
> **测试**: 2626 passed, 新增 ~79 个测试

## Context

日频策略底层能力完备度缺口分析中，Layer 4 当前完备度 90%，目标 100%。共 14 个缺口（P1×9 + P2×5），分布在三个子域：评估指标增强、发布安全 DQ 扩展、失效传播韧性。本计划一次覆盖全部 14 个缺口。

**前置依赖**: Layer 3（物化 + 存储 + 查询）已完成。

---

## 依赖关系

```
Phase 1 (Core 指标基础)  ─────────────────────┐
  EVAL-EV-1, EV-4, EV-6, EV-7, EV-8          │
                                               ├──> Phase 3 (增强分析)
Phase 2 (FMBA + 暴露分析)  ────────────────────┘    EVAL-EV-5, EV-9, EV-10, PUB-PB-1
  EVAL-EV-2, EV-3

Phase 4 (失效韧性)  ──> Phase 5 (去重)
  INVAL-IC-1, IC-2, IC-3         INVAL-IC-4
```

Phase 1 和 Phase 4 **可并行**。

---

## Phase 1: Core 指标基础（P1 + P2 混合）✅

**Commit**: `9e4f5b9d`

**覆盖缺口**: EVAL-EV-1, EVAL-EV-4, EVAL-EV-6, EVAL-EV-7, EVAL-EV-8

### 1a. EVAL-EV-6: `periods_per_year` 可配置化

**文件**: [evaluator.py](packages/core/src/ditto_core/engine/evaluation/evaluator.py)

- `EvaluationConfig` 新增 `periods_per_year: int = 244`
- `_evaluate_impl` 中所有 `DEFAULT_PERIODS_PER_YEAR` 引用替换为 `config.periods_per_year`（L175, L182, L160 的 `turnover_adjusted_ir` 传参）
- 保留 `DEFAULT_PERIODS_PER_YEAR = 244` 常量

### 1b. EVAL-EV-1: Sharpe 公式纳入无风险利率

**文件**: [metrics.py](packages/core/src/ditto_core/engine/evaluation/metrics.py) `long_short_returns()` L500

当前: `sharpe = annual_return / annual_vol`
改为: 从 `ls_daily` 减去日化无风险利率后再年化，使 sharpe = (annual_return - rf) / annual_vol

### 1c. EVAL-EV-4: 尾部风险指标

**文件**: [report.py](packages/core/src/ditto_core/engine/evaluation/report.py)

新增 `TailRiskMetrics` frozen dataclass:
```
cvar_95, cvar_99, skewness, kurtosis, max_single_day_loss
```

**文件**: [metrics.py](packages/core/src/ditto_core/engine/evaluation/metrics.py)

新增 `tail_risk_metrics(ls_daily: pl.Series) -> TailRiskMetrics`:
- CVaR: 排序后取尾部 (1-alpha) 分位均值
- 偏度/峰度: `pl.Series.skew()` / `kurtosis()`（减 3 得超额峰度）
- `LongShortResult` 新增 `tail_risk: TailRiskMetrics` 字段

### 1d. EVAL-EV-7: Calmar Ratio

**文件**: [report.py](packages/core/src/ditto_core/engine/evaluation/report.py) + [metrics.py](packages/core/src/ditto_core/engine/evaluation/metrics.py)

- `LongShortResult` 新增 `calmar: float`
- `long_short_returns()` 计算: `calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0.0`

### 1e. EVAL-EV-8: Grinold-Kahn IR 形式化

**文件**: [metrics.py](packages/core/src/ditto_core/engine/evaluation/metrics.py)

新增 `grinold_kahn_ir(mean_ic, ic_std, ic_autocorr_lag1, breadth, rebalance_freq) -> float`:
- `IR = IC × sqrt(BR_effective)`，使用 Gordon Ritter 修正公式
- `FactorEvaluationReport` 新增 `grinold_kahn_ir: float` 字段

### 测试

**新建**: [test_evaluation_metrics_unit.py](packages/core/tests/unit/engine/test_evaluation_metrics_unit.py)

| 测试 | 验证 |
|------|------|
| `test_sharpe_uses_risk_free_rate` | rf=0.03 时 sharpe 与 rf=0 不同 |
| `test_sharpe_zero_rf_backward_compat` | rf=0 结果与旧公式一致 |
| `test_cvar_known_distribution` | 合成数据 CVaR 与手动计算匹配 |
| `test_tail_risk_empty` | 空数据返回全零 |
| `test_calmar_ratio` | calmar = return / \|mdd\| |
| `test_calmar_zero_drawdown` | mdd=0 时 calmar=0 |
| `test_period_per_year_configurable` | EvaluationConfig(252) 正确传递 |
| `test_grinold_kahn_ir_formula` | 已知输入验证输出 |
| `test_grinold_kahn_ir_zero_autocorr` | rho=0 时 IR = IC × sqrt(breadth) |

---

## Phase 2: Fama-MacBeth + 因子暴露分析（P1）✅

**Commit**: `b15cba2d`（与 Phase 3 合并提交）

**覆盖缺口**: EVAL-EV-2, EVAL-EV-3
**前置**: Phase 1 完成（复用 `periods_per_year` 配置）

### 2a. EVAL-EV-2: Fama-MacBeth 回归

**文件**: [report.py](packages/core/src/ditto_core/engine/evaluation/report.py)

新增 `FamaMacBethResult` frozen dataclass:
```
factor_exposure, exposure_t_stat, exposure_p_value, exposure_stderr,
r_squared_avg, n_periods, slopes: list[tuple[str, float]]
```

**文件**: [metrics.py](packages/core/src/ditto_core/engine/evaluation/metrics.py)

新增 `fama_macbeth(factor_df, return_df, *, risk_factors=None, min_cross_section=30) -> FamaMacBethResult`:

算法:
1. 每日截面 OLS 回归: `r_t = α + β·f_t + ε_t`（若提供 risk_factors 则多变量）
2. 记录每日 slope + R²
3. 时序统计: mean(β), std(β), t-stat, p-value

### 2b. EVAL-EV-3: 因子暴露分析

**文件**: [report.py](packages/core/src/ditto_core/engine/evaluation/report.py)

新增 `FactorExposureResult` frozen dataclass:
```
target_exposure: dict[str, float]       # {factor_name: R² after removal}
correlation_matrix: dict[str, dict[str, float]]
orthogonal_residual_stats: dict[str, float]  # {factor_name: residual_mean_ic}
n_factors, n_dates
```

**文件**: [metrics.py](packages/core/src/ditto_core/engine/evaluation/metrics.py)

新增 `factor_exposure(target_df, risk_factor_dfs, *, min_cross_section=30, method="sequential") -> FactorExposureResult`:
- 复用现有 `orthogonalize()` 函数逐个因子正交化
- 计算正交残差 IC、因子间相关矩阵、暴露度量

### 2c. 集成到 Evaluator

**文件**: [evaluator.py](packages/core/src/ditto_core/engine/evaluation/evaluator.py)

- `EvaluationConfig` 新增: `run_fama_macbeth: bool = False`, `run_exposure_analysis: bool = False`
- `FactorEvaluationReport` 新增: `fama_macbeth: FamaMacBethResult | None`, `factor_exposure: FactorExposureResult | None`
- 新增 `RiskFactorProvider` Protocol（通过 DI 获取风险因子数据）

### 测试

**新建**: [test_fama_macbeth_unit.py](packages/core/tests/unit/engine/test_fama_macbeth_unit.py)
- 单因子合成数据验证 slope 匹配 OLS
- 多因子验证 slope 调整
- 小截面返回空结果
- t-statistic 验证
- 行业中性化验证

**新建**: [test_factor_exposure_unit.py](packages/core/tests/unit/engine/test_factor_exposure_unit.py)
- 单因子暴露验证 R² 和残差 IC
- 相关矩阵验证
- 空风险因子返回零暴露

---

## Phase 3: 增强分析（P1 + P2 混合）✅

**Commit**: `b15cba2d`

**覆盖缺口**: EVAL-EV-5, EVAL-EV-9, EVAL-EV-10, PUB-PB-1
**前置**: Phase 1 + Phase 2 完成

### 3a. PUB-PB-1: 发布 DQ 增强约束

**文件**: [publication_safety.py](packages/core/src/ditto_core/engine/publication_safety.py)

`DerivedMinimalDQSummary` 新增字段（additive，全部有默认值）:
```
coverage_rate: float = 0.0
value_mean: float = 0.0
value_std: float = 0.0
value_skewness: float = 0.0
distribution_drift: float | None = None
value_jump_rate: float = 0.0
max_consecutive_nulls: int = 0
```

新增方法 `advanced_checks() -> tuple[str, ...]`:
- `coverage_rate < 0.95` → `"coverage_rate_minimum"`
- `distribution_drift > 0.1` → `"distribution_stability"`
- `value_jump_rate > 0.3` → `"value_continuity"`

**文件**: [materialization.py](apps/port/src/ditto_port/services/derived/materialization.py)

`_build_minimal_dq_summary()` 计算新字段（覆盖率、均值、标准差、偏度、跳跃率、最大连续空值）。

### 3b. EVAL-EV-5 + EVAL-EV-10: Regime-Adjusted IC + IC 趋势监测

**文件**: [report.py](packages/core/src/ditto_core/engine/evaluation/report.py)

新增 `RegimeICResult` frozen dataclass:
```
regimes: dict[str, ICSummary]
regime_labels: list[tuple[str, str]]
transition_matrix: dict[str, dict[str, float]]
ic_trend: float
ic_trend_p_value: float
```

**文件**: [metrics.py](packages/core/src/ditto_core/engine/evaluation/metrics.py)

新增 `regime_adjusted_ic(ic_df, *, n_regimes=2) -> RegimeICResult`:
- 2 状态 Markov Regime Switching（简版 EM + 高斯混合）
- IC 绝对值分高低波动率两个 regime
- 新增 `ic_momentum(ic_df, *, window=60) -> tuple[float, float]` 线性回归趋势斜率

### 3c. EVAL-EV-9: Performance Attribution

**文件**: [report.py](packages/core/src/ditto_core/engine/evaluation/report.py)

新增 `PerformanceAttributionResult` frozen dataclass:
```
total_return, selection_return, timing_return, interaction_return,
annual_alpha, tracking_error, information_ratio,
win_rate_by_quantile: dict[int, float]
```

**文件**: [metrics.py](packages/core/src/ditto_core/engine/evaluation/metrics.py)

新增 `performance_attribution(quantile_ret_df, *, periods_per_year=244) -> PerformanceAttributionResult`:
- Selection: 各分位超额收益加权
- Alpha: 年化超额收益
- Tracking Error: 日超额收益标准差 × √ppy
- IR: alpha / tracking_error

### 3d. 集成到 Evaluator

**文件**: [evaluator.py](packages/core/src/ditto_core/engine/evaluation/evaluator.py)

- `EvaluationConfig` 新增: `run_regime_ic: bool = False`, `run_performance_attribution: bool = False`
- `FactorEvaluationReport` 新增: `regime_ic: RegimeICResult | None`, `performance_attribution: PerformanceAttributionResult | None`

### 测试

**新建**: [test_evaluation_regime_unit.py](packages/core/tests/unit/engine/test_evaluation_regime_unit.py)
- 双 regime 合成 IC 验证分段
- IC 趋势上升/平稳/下降

**新建**: [test_evaluation_attribution_unit.py](packages/core/tests/unit/engine/test_evaluation_attribution_unit.py)
- 已知分位收益验证 alpha 和 IR
- 无基准仅 selection 归因
- 空数据退化处理

---

## Phase 4: 失效传播韧性（P1 Invalidation）✅

**Commit**: `954e9772`

**覆盖缺口**: INVAL-IC-1, INVAL-IC-2, INVAL-IC-3
**前置**: 无（可与 Phase 1 并行）

### 4a. INVAL-IC-1: repair_batch 失败不终止

**文件**: [cascade_protocol.py](apps/port/src/ditto_port/services/derived/cascade_protocol.py) L200-206

当前 `except` 块 `raise` 终止整个 batch。改为:
- 捕获异常，记录日志，`continue` 处理下一个
- 返回类型改为 `RepairBatchResult(repaired, failed)` dataclass

### 4b. INVAL-IC-2: 死信队列

**文件**: [derived.py](packages/data/src/ditto_data/models/derived.py) `DerivedInvalidationRecord`

新增字段（有默认值）:
```
retry_count: int = 0
error_message: str | None = None
dead_letter_at: str | None = None
```

**文件**: [reader.py](packages/data/src/ditto_data/stores/runtime/derived_sqlite/reader.py) + [writer.py](packages/data/src/ditto_data/stores/runtime/derived_sqlite/writer.py)

- SQLite schema 迁移: `ALTER TABLE` 新增 3 列
- 新增 `list_dead_letter_invalidations()` 方法
- 新增 `increment_retry_count()` + `mark_invalidation_dead_letter()` 方法

**文件**: [derived_catalog_service.py](packages/data/src/ditto_data/services/derived_catalog_service.py)

代理新增的 reader/writer 方法。

**文件**: [cascade_protocol.py](apps/port/src/ditto_port/services/derived/cascade_protocol.py)

- `CascadeStatus` 新增 `DEAD_LETTER = "dead_letter"`
- `repair_batch` 失败时: `retry_count += 1`，达到 3 次转入 DEAD_LETTER
- 死信条目不再被 `list_stale_invalidations()` 选取

### 4c. INVAL-IC-3: 优先级队列

**文件**: [derived.py](packages/data/src/ditto_data/models/derived.py) `DerivedInvalidationRecord`

新增字段: `role: str = "factor"`

**文件**: [reader.py](packages/data/src/ditto_data/stores/runtime/derived_sqlite/reader.py)

`list_stale_invalidations()` SQL 的 `ORDER BY` 新增角色优先级:
```sql
ORDER BY
    CASE role
        WHEN 'signal' THEN 0 WHEN 'factor' THEN 1
        WHEN 'label' THEN 2 WHEN 'feature' THEN 3 ELSE 4
    END ASC,
    depth ASC, created_at ASC
```

**文件**: [cascade_protocol.py](apps/port/src/ditto_port/services/derived/cascade_protocol.py)

`propagate()` 创建 `DerivedInvalidationRecord` 时从 spec 读取 `role` 字段传入。

### 测试

**扩展**: [test_cascade_protocol_unit.py](apps/port/tests/unit/services/derived/test_cascade_protocol_unit.py)

| 测试 | 验证 |
|------|------|
| `test_repair_batch_continues_on_failure` | 3 个 item 中间失败，首尾成功 |
| `test_repair_batch_tracks_failures` | `RepairBatchResult.failed` 包含失败 ID |
| `test_dead_letter_after_max_retries` | 失败 3 次转入死信 |
| `test_dead_letter_not_retried` | 死信不被 list_stale 选取 |
| `test_priority_queue_ordering` | signal > factor > feature 同深度排序 |

---

## Phase 5: 跨事件去重（P2 Invalidation）✅

**Commit**: `c0946079`

**覆盖缺口**: INVAL-IC-4
**前置**: Phase 4 完成

### 5a. INVAL-IC-4: 跨事件去重

**文件**: [reader.py](packages/data/src/ditto_data/stores/runtime/derived_sqlite/reader.py)

`list_stale_invalidations()` SQL 新增去重子查询:
```sql
AND NOT EXISTS (
    SELECT 1 FROM derived_invalidation h
    WHERE h.derived_id = i.derived_id AND h.version = i.version
      AND h.status = 'healed'
      AND h.affected_start <= i.affected_start
      AND h.affected_end >= i.affected_end
)
```

**文件**: [cascade_protocol.py](apps/port/src/ditto_port/services/derived/cascade_protocol.py)

`repair_batch()` 成功修复后，调用 `_mark_subsumed_healed()`:
- 查找同 derived_id:version 中 affected 范围是已修复范围的子集的 STALE 记录
- 将这些隐式修复的记录标记为 HEALED

### 测试

**新建**: [test_cascade_dedup_unit.py](apps/port/tests/unit/services/derived/test_cascade_dedup_unit.py)
- 子集范围自动愈合
- 部分重叠不自动愈合
- 不同版本不互相覆盖
- 并发 cascade 去重

---

## 验证

每个 Phase 完成后:
```bash
pixi run -e dev check          # lint + fmt + type + test --fast
```

全部 Phase 完成后:
```bash
pixi run -e dev ci             # 完整 CI
```

覆盖率目标: 新文件分支覆盖率 ≥ 80%。

### 实际验证结果 ✅

```
pixi run -e dev check
- ruff lint: 0 errors
- ruff format: clean
- basedpyright: 0 errors, 0 warnings
- pytest: 2626 passed (新增 ~79 个测试)
```

### 实现摘要

| Phase | 缺口 | 主要变更 |
|-------|------|----------|
| Phase 1 | EVAL-EV-1,4,6,7,8 | periods_per_year 可配置、Sharpe 纳入 rf、TailRiskMetrics、Calmar、Grinold-Kahn IR |
| Phase 2 | EVAL-EV-2,3 | Fama-MacBeth 两步回归、因子暴露分析（正交化 + 相关矩阵） |
| Phase 3 | EVAL-EV-5,9,10, PUB-PB-1 | Regime IC、IC 趋势、Performance Attribution、DQ 增强约束 |
| Phase 4 | INVAL-IC-1,2,3 | 修复失败不终止、死信队列（3 次重试）、优先级队列（signal>factor>label>feature） |
| Phase 5 | INVAL-IC-4 | NOT EXISTS 跨事件去重、子集范围自动愈合 |

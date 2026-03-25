# Phase 1 Part 04: RiskLockFilter + etf_rotation Template + E2E Verification

**Status:** Done (2026-03-22)
**Branch:** `phase1/04-risklock-template-e2e`
**Depends on:** Part 02（Built-in Stages）+ Part 03（Portfolio Construction）
**Design Doc:** v3 §2.5（etf_rotation 模板）, §6.1（RiskLockFilter, R4）, §9.1（templates/）

---

## 概述

实现 RiskLockFilter（R4）、etf_rotation 策略模板配置、以及 Phase 1 的端到端 RECOMMENDATION 集成测试。Phase 1 的收官任务。

---

## 任务清单

### Task 1: RiskLockFilter `[M]`

- **描述**: 实现风控锁定过滤器 — 过滤被 RiskLock 锁定的标的（R4）
- **文件**:
  - `packages/core/src/ditto_core/strategy/builtins/filtering.py` — 追加 RiskLockFilter
- **实现要点**:
  ```python
  @dataclass(frozen=True)
  class RiskLockFilter:
      """RiskLock 过滤器 — 过滤被 PostTradeRiskGuard 锁定的标的（R4）

      从 context.risk_locked_instruments 读取锁定列表。
      锁定标的不进入 Pipeline 后续阶段，防止 same-day re-entry。
      """

      def process(
          self, frame: pl.DataFrame, context: StrategyContext,
      ) -> pl.DataFrame:
          locked = context.risk_locked_instruments
          if not locked:
              return frame
          return frame.filter(
              ~pl.col("instrument_id").is_in(list(locked.keys()))
          )
  ```
- **验收**:
  - [ ] 无锁定标的 → 原样返回
  - [ ] 部分锁定 → 过滤锁定标的
  - [ ] 全部锁定 → 返回空 frame
  - [ ] 锁定标的不在 frame 中 → 正常（不报错）
  - [ ] context.risk_locked_instruments 为空 → 原样返回

### Task 2: etf_rotation 策略模板配置 `[M]`

- **描述**: 定义 etf_rotation 模板的标准配置，包含 Pipeline 组装逻辑
- **文件**:
  - `packages/core/src/ditto_core/strategy/templates/__init__.py`
  - `packages/core/src/ditto_core/strategy/templates/etf_rotation.py`
- **实现要点**:
  ```python
  @dataclass(frozen=True)
  class ETFRotationConfig:
      """etf_rotation 策略模板的运行时配置"""
      top_k: int = 10
      scoring_method: ScoringMethod = ScoringMethod.RANK
      allocation_method: str = "equal_weight"   # equal_weight / score_weight
      cash_target: float = 0.0
      signal_column: str = "signal_value"
      constraints: tuple[ConstraintSpec, ...] = ()

  def build_etf_rotation_pipeline(
      config: ETFRotationConfig,
  ) -> StrategyPipeline:
      """组装 etf_rotation 的标准 Pipeline

      标准流程:
        Universe → Signal → Score → RiskLockFilter → Filter → Select → Allocate → Constraint
      """
      stages: list[DecisionStage] = [
          SignalStage(source_column=config.signal_column),
          ScoringStage(method=config.scoring_method),
          RiskLockFilter(),
          SelectionStage(top_k=config.top_k),
          _build_allocator(config),
          _build_constraint_stage(config),
      ]
      return StrategyPipeline(stages)
  ```
- **验收**:
  - [ ] 默认配置能组装出合法 Pipeline
  - [ ] 各参数可定制（top_k / scoring_method / allocation_method）
  - [ ] Pipeline 内含 RiskLockFilter
  - [ ] 空约束 → Pipeline 仍正常工作

### Task 3: etf_rotation 模板单元测试 `[S]`

- **描述**: etf_rotation 模板的单元测试
- **文件**:
  - `packages/core/tests/unit/strategy/test_template_unit.py`
- **测试用例**:
  - `test_default_config_builds_pipeline` — 默认配置
  - `test_custom_top_k` — 自定义 top_k
  - `test_score_weight_allocation` — score_weight 分配
  - `test_with_constraints` — 带约束的 Pipeline
  - `test_pipeline_contains_risklock_filter` — 确认包含 RiskLockFilter
  - `test_empty_universe_returns_empty` — 空 Universe
- **验收**:
  - [ ] 所有测试通过
  - [ ] `pixi run -e dev check` 通过

### Task 4: E2E RECOMMENDATION 集成测试 `[L]`

- **描述**: 端到端测试 — 给定输入数据 + etf_rotation 配置，验证 Pipeline 输出合法 TargetPortfolio
- **文件**:
  - `packages/core/tests/integration/strategy/test_etf_rotation_e2e.py`
- **测试场景**:
  ```python
  @pytest.fixture
  def sample_bundle():
      """构造测试用 StrategyInputBundle"""
      instruments = pl.DataFrame({
          "instrument_id": ["ETF001", "ETF002", "ETF003", "ETF004", "ETF005",
                           "ETF006", "ETF007", "ETF008", "ETF009", "ETF010",
                           "ETF011", "ETF012"],
      })
      market_data = pl.DataFrame({
          "instrument_id": ["ETF001", "ETF002", ...],
          "close": [1.0, 2.0, ...],
          # ... OHLCV
      })
      signal_values = pl.DataFrame({
          "instrument_id": ["ETF001", "ETF002", ...],
          "momentum_20d": [0.05, 0.03, -0.01, ...],  # 12 个标的不同信号
      })
      return StrategyInputBundle(
          trade_date="2026-01-15",
          strategy_id="test_etf_rotation",
          run_id="run_001",
          instruments=instruments,
          market_data=market_data,
          signal_values=signal_values,
      )

  def test_etf_rotation_recommendation(sample_bundle):
      """完整 E2E: 输入 → Pipeline → TargetPortfolio"""
      config = ETFRotationConfig(top_k=5)
      pipeline = build_etf_rotation_pipeline(config)
      context = StrategyContext()
      target = pipeline.run(context, sample_bundle)

      assert isinstance(target, TargetPortfolio)
      assert len(target.positions) == 5
      assert abs(sum(target.positions.values()) - 1.0) < 1e-9  # 权重和 = 1
      # 选中的应该是 signal 最高的 5 个
  ```
- **测试用例**:
  - `test_etf_rotation_recommendation` — 标准 E2E
  - `test_risklock_filtering_in_pipeline` — 部分标的被 RiskLock 过滤
  - `test_all_locked_returns_empty` — 全部被锁定
  - `test_with_max_weight_constraint` — 带权重上限约束
  - `test_cash_target` — 现金保留
  - `test_fewer_instruments_than_top_k` — 标的数 < top_k
- **验收**:
  - [ ] 所有测试通过
  - [ ] TargetPortfolio 权重和 = 1.0（无现金保留时）
  - [ ] RiskLockFilter 正确工作
  - [ ] 约束正确应用

### Task 5: __init__.py 更新 + Phase 1 完整验证 `[S]`

- **描述**: 更新所有 __init__.py 导出，运行 Phase 1 完整质量门禁
- **文件**:
  - `packages/core/src/ditto_core/strategy/__init__.py`
  - `packages/core/src/ditto_core/strategy/builtins/__init__.py`
  - `packages/core/src/ditto_core/portfolio/__init__.py`
- **验收**:
  - [ ] `pixi run -e dev check` 通过
  - [ ] `pixi run -e dev test --unit` 全部通过
  - [ ] `pixi run -e dev test --integration` 全部通过
  - [ ] `pixi run -e dev type` 0 errors
  - [ ] 分支覆盖率 ≥ 80%

---

## 实施注意事项

1. **RiskLockFilter 位置**: 在 Pipeline 中放在 Scoring 之后、Selection 之前，确保锁定的标的即使 score 高也不会被选中
2. **模板是配置 + 工厂函数**: etf_rotation 模板不是一个类，而是一个 `build_*_pipeline()` 工厂函数 + frozen 配置 dataclass
3. **E2E 测试数据**: 使用 fixture 构造小型测试数据集，不依赖真实市场数据
4. **权重精度**: 测试中使用 `abs(x - y) < 1e-9` 而非 `x == y` 处理浮点精度

## 交付物

```
strategy/builtins/
├── filtering.py         # 追加 RiskLockFilter

strategy/templates/
├── __init__.py
└── etf_rotation.py      # ETFRotationConfig + build_etf_rotation_pipeline()

tests/unit/strategy/
├── test_template_unit.py     # 6+ 测试用例

tests/integration/strategy/
├── test_etf_rotation_e2e.py  # 6+ E2E 测试用例
```

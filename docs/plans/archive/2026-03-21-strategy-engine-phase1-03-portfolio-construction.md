# Phase 1 Part 03: Portfolio Construction — Allocation + Constraint

**Status:** Done (2026-03-22)
**Branch:** `phase1/03-portfolio-construction`
**Depends on:** Part 01（StrategyPipeline + TargetPortfolio）
**Design Doc:** v3 §2.2（约束优先级）, §9.1（portfolio/ 模块布局）

---

## 概述

创建 `portfolio/` 子模块，实现 WeightAllocator（权重分配）和 ConstraintChecker（约束检查 + priority 排序）。同时创建 AllocationStage 和 ConstraintStage 作为 Pipeline Stage 适配器。

---

## 任务清单

### Task 1: portfolio/ 模块脚手架 `[S]`

- **描述**: 创建 portfolio 包目录和 __init__.py
- **文件**:
  - `packages/core/src/ditto_core/portfolio/__init__.py`
- **验收**:
  - [ ] 包可正常导入
  - [ ] 汇总导出 WeightAllocator + ConstraintChecker

### Task 2: WeightAllocator Protocol + EqualWeightAllocator `[M]`

- **描述**: 定义权重分配接口和等权分配实现
- **文件**:
  - `packages/core/src/ditto_core/portfolio/allocation.py`
- **实现要点**:
  ```python
  class WeightAllocator(Protocol):
      """权重分配器 — 将 score/selection 转换为权重"""

      def allocate(
          self,
          frame: pl.DataFrame,
          context: StrategyContext,
      ) -> pl.DataFrame:
          """在 frame 上添加 weight 列"""
          ...

  class EqualWeightAllocator:
      """等权分配 — 所有标的无差别分配"""
      cash_target: float = 0.0  # 目标现金比例（0.0 = 全仓）

      def allocate(
          self,
          frame: pl.DataFrame,
          context: StrategyContext,
      ) -> pl.DataFrame:
          n = len(frame)
          if n == 0:
              return frame.with_columns(pl.lit(0.0).alias("weight"))
          weight_per_instrument = (1.0 - self.cash_target) / n
          return frame.with_columns(pl.lit(weight_per_instrument).alias("weight"))
  ```
- **验收**:
  - [ ] 空 frame → weight = 0.0
  - [ ] 5 个标的 + cash_target=0.0 → weight = 0.2
  - [ ] 5 个标的 + cash_target=0.1 → weight = 0.18
  - [ ] 1 个标的 + cash_target=0.0 → weight = 1.0

### Task 3: ScoreWeightAllocator `[M]`

- **描述**: 按 score 分配权重（score 高的权重大）
- **文件**:
  - `packages/core/src/ditto_core/portfolio/allocation.py` — 追加类
- **实现要点**:
  ```python
  class ScoreWeightAllocator:
      """按 score 加权分配 — score 高的权重大"""
      score_column: str = "score"
      cash_target: float = 0.0
      min_weight: float = 0.0     # 单标的最低权重（0 = 不限制）

      def allocate(self, frame, context) -> pl.DataFrame:
          # 1. 过滤 null score
          # 2. score 归一化到 [0, 1]
          # 3. weight = normalized_score / sum(normalized_score) * (1 - cash_target)
          # 4. 可选: 裁剪到 [min_weight, ...]
          ...
  ```
- **验收**:
  - [ ] 正常分配 → weight 之和 = 1 - cash_target
  - [ ] 全部 null score → weight = 0.0
  - [ ] 单标的 → weight = 1 - cash_target
  - [ ] min_weight 生效 → 不低于最低权重
  - [ ] 负 score → 正常处理（绝对值归一化或排除）

### Task 4: ConstraintChecker + priority 排序 `[L]`

- **描述**: 实现约束检查器，按 priority 排序执行，每条约束可调整权重并记录原因
- **文件**:
  - `packages/core/src/ditto_core/portfolio/constraints.py`
- **实现要点**:
  ```python
  @dataclass(frozen=True)
  class ConstraintAdjustment:
      """单条约束的调整结果"""
      constraint_id: str
      adjusted_weights: dict[str, float]
      reason_codes: tuple[str, ...]

  class Constraint(Protocol):
      """单条约束规则"""
      constraint_id: str
      priority: int

      def check(
          self,
          weights: dict[str, float],
          frame: pl.DataFrame,
          context: StrategyContext,
      ) -> ConstraintAdjustment: ...

  class ConstraintChecker:
      """约束检查器 — 按 priority 升序执行，逐条调整权重"""

      def __init__(self, constraints: Sequence[Constraint]): ...

      def check(
          self,
          frame: pl.DataFrame,
          context: StrategyContext,
      ) -> pl.DataFrame:
          """按 priority 排序执行约束，返回调整后的 frame"""
          weights = dict(zip(
              frame["instrument_id"].to_list(),
              frame["weight"].to_list(),
          ))
          all_reasons: list[str] = []

          for constraint in sorted(self._constraints, key=lambda c: c.priority):
              result = constraint.check(weights, frame, context)
              weights = result.adjusted_weights
              all_reasons.extend(result.reason_codes)

          # 更新 frame 的 weight 列
          return frame.with_columns(
              pl.col("instrument_id")
              .map_dict(weights, default=0.0)
              .alias("weight")
          ).with_columns(
              pl.lit(all_reasons).alias("reason_codes")
          )
  ```
- **V1 内置约束**:
  - `MaxWeightConstraint` — 单标的权重上限
  - `MinWeightConstraint` — 单标的权重下限（低于则清零）
  - `MaxPositionsConstraint` — 最大持仓数量（保留 top K，其余清零）
- **验收**:
  - [ ] 无约束 → 原样返回
  - [ ] 单约束 MaxWeight(20%) → 超限标的被裁剪
  - [ ] 多约束按 priority 排序执行
  - [ ] reason_codes 正确累积
  - [ ] MinWeight 约束 → 低于阈值的标的 weight 清零
  - [ ] MaxPositions 约束 → 保留 top K，其余清零

### Task 5: AllocationStage + ConstraintStage 适配器 `[S]`

- **描述**: 将 WeightAllocator 和 ConstraintChecker 包装为 DecisionStage
- **文件**:
  - `packages/core/src/ditto_core/portfolio/allocation.py` — AllocationStage
  - `packages/core/src/ditto_core/portfolio/constraints.py` — ConstraintStage
- **实现要点**:
  ```python
  @dataclass(frozen=True)
  class AllocationStage:
      """Pipeline Stage 适配器 — 包装 WeightAllocator"""
      allocator: WeightAllocator

      def process(self, frame, context) -> pl.DataFrame:
          return self.allocator.allocate(frame, context)

  @dataclass(frozen=True)
  class ConstraintStage:
      """Pipeline Stage 适配器 — 包装 ConstraintChecker"""
      checker: ConstraintChecker

      def process(self, frame, context) -> pl.DataFrame:
          return self.checker.check(frame, context)
  ```
- **验收**:
  - [ ] 通过 DecisionStage Protocol 检查（runtime_checkable）
  - [ ] 在 Pipeline 中正常工作

### Task 6: 单元测试 `[M]`

- **描述**: Allocation + Constraint 完整单元测试
- **文件**:
  - `packages/core/tests/unit/strategy/test_allocation_unit.py`
  - `packages/core/tests/unit/strategy/test_constraints_unit.py`
- **测试用例（Allocation）**:
  - `test_equal_weight_empty` / `test_equal_weight_normal` / `test_equal_weight_with_cash`
  - `test_score_weight_empty` / `test_score_weight_normal` / `test_score_weight_null`
  - `test_score_weight_min_weight` / `test_score_weight_negative_score`
  - `test_allocation_stage_adapter`
- **测试用例（Constraint）**:
  - `test_no_constraints` / `test_max_weight` / `test_min_weight`
  - `test_max_positions` / `test_priority_ordering`
  - `test_reason_codes_accumulation`
  - `test_constraint_stage_adapter`
- **验收**:
  - [ ] 所有测试通过
  - [ ] 覆盖率 ≥ 90%
  - [ ] `pixi run -e dev check` 通过

### Task 7: __init__.py 更新 + 完整验证 `[S]`

- **描述**: 更新 portfolio/__init__.py 和 strategy/__init__.py 导出
- **文件**:
  - `packages/core/src/ditto_core/portfolio/__init__.py`
  - `packages/core/src/ditto_core/strategy/__init__.py`
- **新增导出**:
  - `portfolio/`: `WeightAllocator`, `EqualWeightAllocator`, `ScoreWeightAllocator`, `AllocationStage`, `ConstraintChecker`, `ConstraintStage`, `ConstraintAdjustment`
- **验收**:
  - [ ] 所有符号可正常导入
  - [ ] `pixi run -e dev check` 通过

---

## 实施注意事项

1. **模块依赖**: portfolio/ 只依赖 strategy/（消费 TargetPortfolio / DecisionStage / StrategyContext），不依赖 execution/ 或 accounting/
2. **Polars 向量化**: WeightAllocator 的 `allocate()` 输入/输出都是 pl.DataFrame
3. **权重归一化**: ConstraintChecker 调整后的权重不一定归一化（由下一轮 Constraint 自然处理）
4. **frozen dataclass**: 所有配置类为 frozen，ConstraintChecker 内部持有 tuple[Constraint]
5. **v3 §2.2 对齐**: ConstraintSpec.priority 已在 Phase 0 定义（specs.py），Constraint.priority 与之对应

## 交付物

```
portfolio/
├── __init__.py
├── allocation.py        # WeightAllocator + EqualWeight + ScoreWeight + AllocationStage
└── constraints.py       # ConstraintChecker + Constraint Protocol + 3 个内置约束 + ConstraintStage

tests/unit/strategy/
├── test_allocation_unit.py   # 10+ 测试用例
├── test_constraints_unit.py  # 10+ 测试用例
```

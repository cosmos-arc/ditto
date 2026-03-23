# Phase 1 Part 02: Built-in Stages

**Status:** Done (2026-03-22)
**Branch:** `phase1/02-builtin-stages`
**Depends on:** Part 01（StrategyPipeline + DecisionFrame）
**Design Doc:** v3 §2, §9.1

---

## 概述

实现 Pipeline 的 5 个内置 Stage：Universe / Signal / Scoring / Filtering / Selection。所有 Stage 实现 DecisionStage Protocol，内部使用 Polars 向量化操作。

---

## 任务清单

### Task 1: builtins/ 模块脚手架 `[S]`

- **描述**: 创建 builtins 包目录和 __init__.py
- **文件**:
  - `packages/core/src/ditto_core/strategy/builtins/__init__.py`
- **验收**:
  - [ ] 包可正常导入
  - [ ] 汇总导出所有内置 Stage

### Task 2: UniverseStage `[M]`

- **描述**: 按 instrument_id 列表过滤标的，缩小 Pipeline 处理范围
- **文件**:
  - `packages/core/src/ditto_core/strategy/builtins/universe.py`
- **实现要点**:
  ```python
  @dataclass(frozen=True)
  class UniverseStage:
      """Universe Stage — 按 instrument_id 白名单过滤"""
      instrument_ids: frozenset[str]

      def process(
          self, frame: pl.DataFrame, context: StrategyContext,
      ) -> pl.DataFrame:
          return frame.filter(pl.col("instrument_id").is_in(list(self.instrument_ids)))
  ```
- **验收**:
  - [ ] 白名单为空 → 返回空 frame
  - [ ] 白名单包含所有标的 → 原样返回
  - [ ] 部分匹配 → 只保留匹配行
  - [ ] 无 `instrument_id` 列 → 抛出明确错误

### Task 3: SignalStage `[M]`

- **描述**: 将预计算信号值映射到 DecisionFrame，或从 market_data 列计算简单信号
- **文件**:
  - `packages/core/src/ditto_core/strategy/builtins/signal.py`
- **实现要点**:
  ```python
  @dataclass(frozen=True)
  class SignalStage:
      """Signal Stage — 将预计算信号值 attach 到 DecisionFrame

      模式 1（推荐）: 从 StrategyInputBundle.signal_values 映射
      模式 2: 从 frame 中已有列提取（如 frame 包含 momentum_20d 列）
      """
      signal_column: str = "signal_value"       # 输出列名
      source_column: str | None = None          # 输入列名（None = 使用 signal_values）

      def process(
          self, frame: pl.DataFrame, context: StrategyContext,
      ) -> pl.DataFrame:
          ...
  ```
- **设计决策**:
  - SignalStage 的输入信号由 Port 层预计算（使用现有 engine/ 因子系统），Pipeline 不做因子计算
  - SignalStage 从 frame 中提取已有的信号列并重命名为 `signal_value`
  - 如果 frame 没有 source_column，signal_value 填充为 null
- **验收**:
  - [ ] 正常映射 signal_values → signal_value 列
  - [ ] source_column 指定 → 从已有列重命名
  - [ ] 无信号数据 → signal_value 全 null
  - [ ] frame 空 → 返回空 frame（不报错）

### Task 4: ScoringStage `[M]`

- **描述**: 将 signal_value 转换为 score（排名/归一化）
- **文件**:
  - `packages/core/src/ditto_core/strategy/builtins/scoring.py`
- **实现要点**:
  ```python
  class ScoringMethod(StrEnum):
      RAW = "raw"              # 直接使用 signal_value
      RANK = "rank"            # 百分位排名 (0-1)
      ZSCORE = "zscore"        # Z-score 标准化

  @dataclass(frozen=True)
  class ScoringStage:
      """Scoring Stage — 将 signal_value 转换为 score"""
      method: ScoringMethod = ScoringMethod.RANK
      ascending: bool = False   # True = signal 小的得分高（如波动率）
      output_column: str = "score"

      def process(
          self, frame: pl.DataFrame, context: StrategyContext,
      ) -> pl.DataFrame:
          ...
  ```
- **实现要点**:
  - `RAW`: score = signal_value
  - `RANK`: score = signal_value.rank(descending=not ascending) / count
  - `ZSCORE`: score = (signal_value - mean) / std，std=0 时 score=0
  - null signal_value → score = null（后续 Filtering/Selection 自然过滤）
- **验收**:
  - [ ] RAW 模式 → score = signal_value
  - [ ] RANK 模式 → score ∈ [0, 1]，无并列时均匀分布
  - [ ] ZSCORE 模式 → mean=0, std=1
  - [ ] ascending=True → 排序方向反转
  - [ ] null signal_value → score = null
  - [ ] 全部 null → score 全 null

### Task 5: FilteringStage `[M]`

- **描述**: 通用过滤 Stage，支持多个命名过滤条件
- **文件**:
  - `packages/core/src/ditto_core/strategy/builtins/filtering.py`
- **实现要点**:
  ```python
  @dataclass(frozen=True)
  class FilterCondition:
      """单条过滤条件"""
      name: str                                    # 过滤器名称（审计用）
      column: str                                  # 过滤依据列
      min_value: float | None = None               # 最小值（含）
      max_value: float | None = None               # 最大值（含）
      exclude_nulls: bool = True                   # True = 排除 null 值

  @dataclass(frozen=True)
  class FilteringStage:
      """Filtering Stage — 按条件过滤标的"""
      conditions: tuple[FilterCondition, ...] = ()

      def process(
          self, frame: pl.DataFrame, context: StrategyContext,
      ) -> pl.DataFrame:
          ...
  ```
- **验收**:
  - [ ] 无条件 → 原样返回
  - [ ] 单条件过滤 → 正确保留/排除
  - [ ] 多条件 AND 组合 → 全部满足才保留
  - [ ] exclude_nulls=True → null 值被排除
  - [ ] exclude_nulls=False → null 值保留
  - [ ] 条件列不存在 → 抛出明确错误

### Task 6: SelectionStage `[M]`

- **描述**: 按 score 排序选取 top K 标的
- **文件**:
  - `packages/core/src/ditto_core/strategy/builtins/selection.py`
- **实现要点**:
  ```python
  @dataclass(frozen=True)
  class SelectionStage:
      """Selection Stage — 按 score 选取 top K 标的"""
      top_k: int                                     # 选取数量
      score_column: str = "score"                    # 排序依据列
      ascending: bool = False                        # False = score 大的优先

      def process(
          self, frame: pl.DataFrame, context: StrategyContext,
      ) -> pl.DataFrame:
          ...
  ```
- **验收**:
  - [ ] top_k > 行数 → 返回全部（按排序）
  - [ ] top_k = 0 → 返回空 frame
  - [ ] null score 排末尾（不参与 top K）
  - [ ] ascending=True → score 小的优先
  - [ ] 空输入 → 返回空 frame

### Task 7: Stages 集成测试 `[M]`

- **描述**: 内置 Stages 的完整单元测试
- **文件**:
  - `packages/core/tests/unit/strategy/test_stages_unit.py`
- **测试用例**:
  - UniverseStage: 4 cases（空/全/部分/无列）
  - SignalStage: 4 cases（正常映射/重命名/无数据/空 frame）
  - ScoringStage: 6 cases（RAW/RANK/ZSCORE × ascending × null）
  - FilteringStage: 6 cases（无条件/单条件/多条件/null 处理/列不存在）
  - SelectionStage: 5 cases（top_k>行数/0/null/ascending/空）
  - Pipeline 集成: Universe → Signal → Score → Filter → Select 完整链路
- **验收**:
  - [ ] 所有测试通过
  - [ ] 覆盖率 ≥ 90%
  - [ ] `pixi run -e dev check` 通过

### Task 8: __init__.py 更新 `[S]`

- **描述**: 更新 builtins/__init__.py 和 strategy/__init__.py 导出
- **文件**:
  - `packages/core/src/ditto_core/strategy/builtins/__init__.py`
  - `packages/core/src/ditto_core/strategy/__init__.py`
- **验收**:
  - [ ] 所有 Stage 可从 `ditto_core.strategy.builtins` 导入
  - [ ] `pixi run -e dev check` 通过

---

## 实施注意事项

1. **Polars 向量化**: 所有 Stage 内部使用 `pl.col()` / `pl.when()` / `pl.filter()` 操作，禁止 `iter_rows()`
2. **frozen dataclass**: 所有 Stage 配置类为 frozen，无状态，`process()` 是纯函数
3. **null 安全**: null signal_value → null score → 排末尾 → 自然被 SelectionStage 排除
4. **列名约定**: SignalStage 输出 `signal_value`，ScoringStage 输出 `score`，与 DecisionFrame schema 一致
5. **RiskLockFilter**: 在 Part 04 实现（作为 FilteringStage 的一个特例）

## 交付物

```
strategy/builtins/
├── __init__.py
├── universe.py          # UniverseStage
├── signal.py            # SignalStage
├── scoring.py           # ScoringStage + ScoringMethod
├── filtering.py         # FilteringStage + FilterCondition
└── selection.py         # SelectionStage

tests/unit/strategy/
├── test_stages_unit.py  # 25+ 测试用例
```

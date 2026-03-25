# Phase 1 Part 01: Pipeline Runner + DecisionFrame + StrategyInputBundle

**Status:** Done (2026-03-22)
**Branch:** `phase1/01-pipeline-runner`
**Depends on:** Phase 0 完成（accounting/ + strategy/ 类型定义已就位）
**Design Doc:** v3 §2.1-2.4, §6.1, §9.1

---

## 概述

实现 StrategyPipeline（Pipeline Runner）和 StrategyInputBundle（输入数据容器），建立 Pipeline 的编排框架和数据流转约定。

---

## 任务清单

### Task 1: StrategyInputBundle 数据容器 `[S]`

- **描述**: 定义 Pipeline 的输入数据结构，封装市场数据、策略配置、参数覆盖
- **文件**:
  - `packages/core/src/ditto_core/strategy/pipeline.py` — StrategyInputBundle 类
- **实现要点**:
  ```python
  @dataclass(frozen=True)
  class StrategyInputBundle:
      """Pipeline 输入数据容器 — 由 Port 层组装"""
      trade_date: str
      strategy_id: str
      run_id: str
      instruments: pl.DataFrame          # instrument_id + 元数据
      market_data: pl.DataFrame          # OHLCV 等市场数据
      signal_values: pl.DataFrame | None # 预计算信号值（可选，有则 SignalStage 直接映射）
      parameters: dict[str, object]      # 参数覆盖
      benchmark_close: float | None = None
  ```
- **验收**:
  - [ ] frozen dataclass，不可变
  - [ ] 所有字段有合理默认值
  - [ ] 单元测试：构造、字段访问

### Task 2: DecisionFrame Schema 约定文档（内联 docstring） `[S]`

- **描述**: 在 StrategyPipeline 的模块 docstring 中记录 DecisionFrame 的列名约定
- **文件**:
  - `packages/core/src/ditto_core/strategy/pipeline.py` — 模块级 docstring
- **DecisionFrame 列名约定**:
  ```
  必选列:
    instrument_id: str    — 标的 ID

  可选列（由各 Stage 按需添加）:
    signal_value: float   — 信号值（SignalStage）
    score: float          — 评分（ScoringStage）
    weight: float         — 权重（AllocationStage）
    reason_codes: list[str] — 约束调整原因（ConstraintStage）
  ```
- **验收**:
  - [ ] 模块 docstring 包含完整列名表
  - [ ] 标注哪些 Stage 读写哪些列

### Task 3: StrategyPipeline 编排器 `[M]`

- **描述**: 实现 Pipeline Runner，顺序编排 DecisionStage 并输出 TargetPortfolio
- **文件**:
  - `packages/core/src/ditto_core/strategy/pipeline.py` — StrategyPipeline 类
- **实现要点**:
  ```python
  class StrategyPipeline:
      """策略决策 Pipeline — 顺序编排 DecisionStage"""

      def __init__(self, stages: Sequence[DecisionStage]): ...

      def run(
          self,
          context: StrategyContext,
          input_bundle: StrategyInputBundle,
      ) -> TargetPortfolio:
          """执行完整 Pipeline，返回 TargetPortfolio"""
          # 1. 从 input_bundle 构建 DecisionFrame（初始 DataFrame）
          # 2. 顺序执行每个 stage.process(frame, context)
          # 3. 从最终 frame 提取 TargetPortfolio
          ...
  ```
- **验收**:
  - [ ] 空 stages 列表 → 返回空 TargetPortfolio
  - [ ] 单 stage → 正确转发
  - [ ] 多 stage → 顺序执行，前一个输出是后一个输入
  - [ ] 最终 frame 转换为 TargetPortfolio（instrument_id → weight 映射）
  - [ ] context 透传给每个 stage

### Task 4: Pipeline 单元测试 `[S]`

- **描述**: StrategyPipeline 的完整单元测试
- **文件**:
  - `packages/core/tests/unit/strategy/test_pipeline_unit.py`
- **测试用例**:
  - `test_empty_pipeline_returns_empty_target` — 无 stage
  - `test_single_stage_forwarding` — 单 stage 透传
  - `test_multi_stage_sequential` — 多 stage 顺序
  - `test_context_passed_to_all_stages` — context 透传验证
  - `test_target_portfolio_from_final_frame` — frame → TargetPortfolio 转换
  - `test_target_portfolio_preserves_cash_target` — cash_target 保留
  - `test_input_bundle_construction` — StrategyInputBundle 构造
  - `test_input_bundle_frozen` — frozen 不可变
- **验收**:
  - [ ] 所有测试通过
  - [ ] 覆盖率 ≥ 90%

### Task 5: __init__.py 更新 + 模块验证 `[S]`

- **描述**: 更新 strategy/__init__.py 导出，运行完整验证
- **文件**:
  - `packages/core/src/ditto_core/strategy/__init__.py` — 新增导出
- **新增导出**: `StrategyPipeline`, `StrategyInputBundle`
- **验收**:
  - [ ] `pixi run -e dev check` 通过
  - [ ] 新增符号可正常导入

---

## 实施注意事项

1. **DecisionFrame 不做 schema 校验**：Pipeline 通过列名约定流转，不在运行时强制 schema。如果某个 stage 期望的列不存在，由 Polars 的 column not found 错误自然暴露。
2. **TargetPortfolio 转换**：从最终 frame 中提取 `instrument_id` 和 `weight` 列，`weight` 默认 0.0。如果没有 `weight` 列，使用 equal_weight 兜底（但正常流程应经过 AllocationStage）。
3. **StrategyInputBundle.instruments**：初始 DataFrame 至少包含 `instrument_id` 列。其他元数据列由具体 Stage 决定。
4. **纯函数**：StrategyPipeline 无状态，`run()` 方法是纯函数（相同输入 → 相同输出）。

## 交付物

```
strategy/
├── pipeline.py              # StrategyPipeline + StrategyInputBundle + DecisionFrame doc
tests/unit/strategy/
├── test_pipeline_unit.py    # 8+ 测试用例
```

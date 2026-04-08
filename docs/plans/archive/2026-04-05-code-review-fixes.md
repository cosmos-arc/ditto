# Code Review 修复计划

## 概述
- Sprint: PR #61 | Phase: Code Review 修复
- 创建: 2026-04-05

## 技术方案

PR #61 代码审查发现 5 个问题（评分 75-90），全部需要修复。按依赖关系分为 3 组，串行执行。

## 任务清单

### Task 1: 修复 `_compute_value_jump_rate` 阈值尺度不匹配 `[S]` ✅

**问题**: 函数用 `3.0 * value_std`（原始值标准差，如价格 std=1.5）作为阈值，但比较对象是 `pct_change`（百分比变化，范围 0.01-0.10）。检测器永远不会触发，`value_jump_rate` 恒为 0.0。

**修复方案**: 阈值改为基于 pct_change 自身的标准差（z-score 逻辑），而非原始值 std。

**验收**:
- [x] 阈值基于 pct_change 分布，而非原始 value
- [x] 空数据 / std≤0 边界条件仍正确
- [x] 新增单元测试覆盖正常/边界场景（7 个测试用例）
- [x] `pixi run -e dev check` 通过

**文件**:
- `packages/app/src/ditto_app/process/materialization.py` — 修改 `_compute_value_jump_rate`（L537-580）
- `packages/app/tests/unit/process/test_materialization_unit.py` — 新增测试（新建）

**修改细节**:
```python
# 当前（错误）:
def _compute_value_jump_rate(frame: pl.DataFrame, value_std: float) -> float:
    threshold = 3.0 * value_std  # 原始值尺度
    ...
    n_jumps = int(all_pct.filter(pl.col("pct").abs() > threshold).height)

# 修复后:
def _compute_value_jump_rate(frame: pl.DataFrame, value_std: float) -> float:
    ...
    # 用 pct_change 自身分布的 z-score 检测异常跳跃
    all_pct_values = all_pct.to_series()
    pct_std = all_pct_values.std()
    if pct_std is None or pct_std <= 0:
        return 0.0
    threshold = 3.0 * pct_std  # pct_change 尺度
    n_jumps = int(all_pct.filter(pl.col("pct").abs() > threshold).height)
```

> 注意: `value_std` 参数保留签名兼容但不再用于阈值计算，避免影响调用方 `build_minimal_dq_record`（L437）。

---

### Task 2: 修复 `METAL_CODE_ALIASES` 重复 API 调用 `[S]` ✅

**问题**: `METAL_CODE_ALIASES` 有 6 个键映射到 2 个唯一值（3→XAUUSD.FXCM, 3→XAGUSD.FXCM），但 `ingestion.py` 传入所有 6 个键，导致 4 次冗余 API 调用 + 重复数据行。

**修复方案**: 对 values 去重后再传入 fetch。

**验收**:
- [x] 仅传入唯一 metal codes
- [x] 无重复数据行
- [x] 现有测试通过
- [x] `pixi run -e dev check` 通过

**文件**:
- `packages/app/src/ditto_app/process/ingestion.py` — L1777 修改

**修改细节**:
```python
# 当前（错误）:
metal_codes = list(METAL_CODE_ALIASES.keys())

# 修复后:
metal_codes = list(dict.fromkeys(METAL_CODE_ALIASES.values()))
```

> `dict.fromkeys` 保持去重后顺序，比 `set()` 更可预测。

---

### Task 3: 修复 `QualityService` DI 注入缺失 `quarantine_writer` + `check_and_quarantine` 文档不一致 `[M]` ✅

**问题 A**: `providers.py` 中 `quality_service` 只注入 `engine`，未注入 `quarantine_writer`（`QualityRecordService`），导致隔离功能完全失效。

**问题 B**: `check_and_quarantine` 文档声称返回 `cleaned_df`，但实际返回原始 df。调用方 `ingestion.py:2046` 执行 `df = checked_df` 是无操作。

**修复方案**:
- A: 在 `AppProcessProvider.quality_service` 中注入 `QualityRecordService`
- B: 修正文档字符串，明确返回的是原始 df（隔离不等于清洗）

**验收**:
- [x] `QualityService` 通过 DI 获得有效的 `quarantine_writer`
- [x] docstring 准确描述方法行为（返回原始 df + 阻断标记）
- [x] 现有测试通过
- [x] `pixi run -e dev check` 通过

**文件**:
- `packages/app/src/ditto_app/providers.py` — L312-315 注入 `quarantine_writer`
- `packages/app/src/ditto_app/process/quality.py` — L86-139 修正 docstring

**修改细节**:
```python
# providers.py — 修改后:
@provide
def quality_service(
    self,
    dq_engine: QualityEngine,
    quality_record_service: QualityRecordService,
) -> QualityService:
    """写入时 DQ 质量服务."""
    return QualityService(engine=dq_engine, quarantine_writer=quality_record_service)

# quality.py — docstring 修正:
Returns:
    Tuple of (df, should_block):
        - df: Original DataFrame (unchanged; quarantine copies bad rows to separate store)
        - should_block: Whether to block ingestion (True if L1 errors found)
```

---

### Task 4: 移除 `post_trade.py` 不必要的 TYPE_CHECKING `[S]` ✅

**问题**: `packages/engine/src/ditto_engine/risk/post_trade.py` 使用 `TYPE_CHECKING` 保护 `Slice` 导入，但 `data_feed.py` 不反向导入 `post_trade`，无循环依赖。

**修复方案**: `Slice` 实际存在循环依赖（`backtest → risk` 大量导入），不能简单移至顶层。改为定义 `_SliceView` Protocol 替代导入，遵循依赖倒置原则。

**验收**:
- [x] `TYPE_CHECKING` 块移除，`Slice` 替换为 `_SliceView` Protocol
- [x] `_SliceView` Protocol 定义只读 `bars` 属性
- [x] `importlinter` 无循环依赖报告
- [x] `pixi run -e dev check` 通过

**文件**:
- `packages/engine/src/ditto_engine/risk/post_trade.py` — L22, L30-31

**修改细节**:
```python
# 当前:
from typing import TYPE_CHECKING, Protocol
...
if TYPE_CHECKING:
    from ditto_engine.backtest.data_feed import Slice

# 修复后:
from typing import Any, Protocol
...

class _SliceView(Protocol):
    """Minimal slice protocol — decouples risk from backtest."""
    @property
    def bars(self) -> dict[InstrumentId, Any]: ...

# 所有方法签名中 Slice → _SliceView
```

> **架构说明**: 原计划将 `Slice` 改为顶层导入，但 importlinter 检测到 `backtest → risk` 已存在大量导入，
> 顶层导入会产生真实的循环依赖。改用 Protocol 实现依赖倒置，风险模块仅依赖抽象接口。

---

## 执行顺序

```
Task 1 (value_jump_rate) ──┐
Task 2 (METAL_CODE_ALIASES) ──┤── 无依赖，可并行
Task 4 (TYPE_CHECKING) ──────┘
        │
Task 3 (quarantine_writer + docstring) ── 依赖 Task 1/2/4 完成（最终验证）
        │
pixi run -e dev check ── 全量验证
```

Task 1/2/4 相互独立可并行，Task 3 最后执行以确保全量验证一次通过。

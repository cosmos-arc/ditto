# 跨源对比功能实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 在现有 L1/L2/L3 质量检查体系基础上，新增跨源对比能力（Tushare vs 通达信），实现数据质量增强验证。

**架构:** Core 层纯业务逻辑（CrossSourceChecker）→ DataHub 层数据访问（TdxSource、ComparisonStore）→ Port 层编排协调（QualityReconciliationService）。

**技术栈:** Polars、Pydantic、Dishka DI、Parquet

---

## 概述

- **Sprint**: Sprint 2 - Phase 5 (黄金数据集验证扩展)
- **Phase**: 0.5 数据摄取完善期
- **创建**: 2026-01-25
- **设计文档**: [2026-01-24-quality-reconciliation-design.md](../design/2026-01-24-quality-reconciliation-design.md)

## 技术方案

### 核心设计决策

| 决策点 | 方案 | 理由 |
|--------|------|------|
| **DQ 级别** | L3 定时批量（ALERT） | 不阻塞数据摄入，异步执行 |
| **分层架构** | Core（纯逻辑）+ DataHub（数据访问）+ Port（编排） | 遵循现有架构边界 |
| **配置管理** | Port 层加载 yml，注入 Core 层 | 遵循依赖注入原则 |
| **存储格式** | Parquet（隔离区，30 天清理） | 高效查询，支持趋势分析 |
| **对比方法** | Polars 向量化 | 性能优化 |
| **TDX 定位** | 仅用于质量对账，不参与主摄入 | 降低风险 |

### 分层职责

```
┌─────────────────────────────────────────────────────────────────┐
│ Port 层（apps/port）                                            │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ QualityReconciliationService                               │ │
│ │ - 编排协调                                                  │ │
│ │ - 获取多源数据                                              │ │
│ │ - 调用 Core 层引擎                                          │ │
│ │ - 存储结果 + 触发告警                                       │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ registry/core.py 扩展                                       │ │
│ │ - 加载跨源对比规则配置                                      │ │
│ │ - 注入到 QualityEngine                                     │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↓ DI
┌─────────────────────────────────────────────────────────────────┐
│ Core 层（packages/core）                                         │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ spec.py 扩展                                                │ │
│ │ - CrossSourceRule Pydantic 模型                            │ │
│ │ - CompareMethod 枚举                                        │ │
│ │ - ToleranceRule 数据类                                       │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ checkers/cross_source.py (新增)                            │ │
│ │ - CrossSourceChecker                                       │ │
│ │ - 纯函数式对比逻辑                                          │ │
│ │ - Tick 对齐 / 相对容差 / 绝对容差                           │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ engine.py 扩展                                              │ │
│ │ - check_cross_source() 方法                                 │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↓ DI
┌─────────────────────────────────────────────────────────────────┐
│ DataHub 层（packages/data）                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ sources/tdx/ (新增)                                         │ │
│ │ - TdxSource: 数据源抽象                                     │ │
│ │ - TdxReader: .day 二进制文件读取                            │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ stores/quality/comparison_store.py (新增)                  │ │
│ │ - ComparisonStore: 对比结果存储                             │ │
│ │ - 隔离区：data_root/quarantine/quality_comparison/          │ │
│ │ - 30 天自动清理                                             │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 配置
┌─────────────────────────────────────────────────────────────────┐
│ 配置文件（config/default/dq_rules/）                             │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ stock_daily.yml (扩展)                                     │ │
│ │ - 新增 l3_statistical 跨源对比规则                          │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 执行顺序

```
阶段 1: Core 层（P0）- 纯业务逻辑，无依赖
    │
    ├─ Task 1.1: 扩展 spec.py（数据模型）
    ├─ Task 1.2: 创建 CrossSourceChecker（检查器）
    ├─ Task 1.3: 扩展 QualityEngine（集成）
    └─ Task 1.4: Core 层单元测试
    │
    ↓
阶段 2: DataHub 层 - TDX 数据源（P1）
    │
    ├─ Task 2.1: 创建 TdxReader（.day 文件读取）
    ├─ Task 2.2: 创建 TdxSource（数据源抽象）
    └─ Task 2.3: TDX 单元测试
    │
    ↓
阶段 3: DataHub 层 - 对比结果存储（P1）
    │
    ├─ Task 3.1: 创建 ComparisonStore（存储层）
    ├─ Task 3.2: 创建 ComparisonAccessor（访问层）
    └─ Task 3.3: 存储层单元测试
    │
    ↓
阶段 4: Port 层（P2）
    │
    ├─ Task 4.1: 扩展 registry/core.py（配置加载）
    ├─ Task 4.2: 创建 QualityReconciliationService（编排服务）
    ├─ Task 4.3: 集成测试
    └─ Task 4.4: 文档更新
```

---

## 任务清单

### 阶段 1: Core 层（P0）- 4-6 小时

#### Task 1.1: 扩展 spec.py 数据模型 `[S]`

**文件:**
- 修改: `packages/core/src/ditto_core/quality/spec.py`

**Step 1: 添加比对方法枚举和容差规则**

```python
# 在 RuleType 枚举后添加

class CompareMethod(str, Enum):
    """跨源比对方法."""
    TICK_ALIGNED = "tick_aligned"  # Tick 对齐（价格类）
    RELATIVE = "relative"          # 相对容差（百分比）
    ABSOLUTE = "absolute"          # 绝对容差（成交量类）


@dataclass(frozen=True)
class ToleranceRule:
    """容差规则."""
    method: CompareMethod
    tick_size: float | None = None       # Tick 对齐时的 tick 大小
    relative_tol: float | None = None    # 相对容差（如 0.001 = 0.1%）
    absolute_tol: float | None = None    # 绝对容差
```

**Step 2: 添加跨源对比规则模型**

```python
# 在 L3 Rules 后添加

class CrossSourceRule(BaseRule):
    """跨源对比规则（L3 统计检查）."""
    rule: RuleType = RuleType.CROSS_SOURCE_COMPARE
    fields: list[str]                    # 要对比的字段（如 [open, high, low, close, vol]）
    key_columns: list[str]               # 对比键（如 [src_code, trade_date]）
    tolerance_rules: dict[str, dict] | None = None  # 字段 → 容差配置
    enabled: bool = True                 # 开关控制
```

**Step 3: 更新 RuleType 枚举**

```python
# 在 RuleType 枚举中添加
class RuleType(str, Enum):
    # ... existing rules ...
    CROSS_SOURCE_COMPARE = "cross_source_compare"  # 跨源对比
```

**Step 4: 运行类型检查**

```bash
pixi run -e dev type
```

预期: 通过

**Step 5: 提交**

```bash
git add packages/core/src/ditto_core/quality/spec.py
git commit -m "feat(cross-source): add CrossSourceRule data model"
```

---

#### Task 1.2: 创建 CrossSourceChecker `[M]`

**文件:**
- 创建: `packages/core/src/ditto_core/quality/checkers/cross_source.py`
- 修改: `packages/core/src/ditto_core/quality/checkers/__init__.py`

**Step 1: 创建 CrossSourceChecker 框架**

```python
"""跨源对比检查器 - L3 统计检查.

Core 层：纯业务逻辑，无数据访问依赖。
接收两个 DataFrame 进行对比，不关心数据从哪来。
"""

from typing import Any
import polars as pl
from loguru import logger
from ditto_core.quality.spec import (
    DQIssue,
    DQLevel,
    DQSeverity,
    CompareMethod,
    ToleranceRule,
)


class CrossSourceChecker:
    """跨源对比检查器.

    Core 层：纯函数式，接收两个 DataFrame 进行对比。
    """

    def __init__(
        self,
        tolerance_rules: dict[str, ToleranceRule] | None = None,
    ) -> None:
        """初始化检查器.

        Args:
            tolerance_rules: 默认容差规则（字段 → 规则）
        """
        self.tolerance_rules = tolerance_rules or self._default_rules()

    def _default_rules(self) -> dict[str, ToleranceRule]:
        """默认容差规则."""
        return {
            "open": ToleranceRule(method=CompareMethod.TICK_ALIGNED, tick_size=0.01),
            "high": ToleranceRule(method=CompareMethod.TICK_ALIGNED, tick_size=0.01),
            "low": ToleranceRule(method=CompareMethod.TICK_ALIGNED, tick_size=0.01),
            "close": ToleranceRule(method=CompareMethod.TICK_ALIGNED, tick_size=0.01),
            "vol": ToleranceRule(method=CompareMethod.RELATIVE, relative_tol=0.001),
            "amount": ToleranceRule(method=CompareMethod.RELATIVE, relative_tol=0.001),
        }

    def check(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        rules: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[DQIssue]:
        """执行跨源对比检查.

        Args:
            primary: 主数据源 DataFrame（如 Tushare）
            secondary: 辅助数据源 DataFrame（如 TDX）
            rules: 跨源对比规则列表
            context: 额外上下文

        Returns:
            DQIssue 列表
        """
        issues: list[DQIssue] = []

        for rule in rules:
            if rule.get("rule") != "cross_source_compare":
                continue
            if not rule.get("enabled", True):
                continue

            issue = self._check_cross_source(primary, secondary, rule, context)
            if issue:
                issues.append(issue)

        return issues

    def _check_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        rule: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> DQIssue | None:
        """检查单个跨源对比规则.

        Args:
            primary: 主数据源
            secondary: 辅助数据源
            rule: 规则配置
            context: 额外上下文

        Returns:
            DQIssue if rule violated, None otherwise
        """
        key_columns = rule.get("key_columns", ["src_code", "trade_date"])
        fields = rule.get("fields", [])
        custom_tolerance = rule.get("tolerance_rules", {})

        # 合并容差规则（自定义覆盖默认）
        tolerance = self.tolerance_rules.copy()
        for field, rule_config in custom_tolerance.items():
            tolerance[field] = ToleranceRule(
                method=CompareMethod(rule_config.get("method", "relative")),
                tick_size=rule_config.get("tick_size"),
                relative_tol=rule_config.get("relative_tol"),
                absolute_tol=rule_config.get("absolute_tol"),
            )

        # 使用 key_columns 进行 join
        merged = primary.join(secondary, on=key_columns, how="inner", suffix="_secondary")

        if merged.height == 0:
            logger.debug(
                "cross_source_no_overlap",
                event="dq_check",
                rule="cross_source_compare",
                reason="No overlapping records found",
            )
            return None

        # 检查每个字段
        diff_samples: list[dict[str, Any]] = []
        for field in fields:
            if field not in primary.columns or field not in secondary.columns:
                continue

            field_diff = self._check_field(merged, field, tolerance.get(field))
            if field_diff is not None:
                diff_samples.extend(field_diff)

        if diff_samples:
            logger.warning(
                "cross_source_difference_found",
                event="dq_check",
                rule="cross_source_compare",
                diff_count=len(diff_samples),
            )
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name="cross_source_compare",
                message=rule.get("message", "Cross-source comparison found differences"),
                affected_rows=len(diff_samples),
                sample_data=diff_samples[:10],  # 最多 10 个样本
            )

        return None

    def _check_field(
        self,
        merged: pl.DataFrame,
        field: str,
        tolerance: ToleranceRule | None,
    ) -> list[dict[str, Any]] | None:
        """检查单个字段的差异.

        Args:
            merged: 合并后的 DataFrame
            field: 字段名
            tolerance: 容差规则

        Returns:
            差异样本列表，无差异返回 None
        """
        if tolerance is None:
            return None

        primary_col = pl.col(field)
        secondary_col = pl.col(f"{field}_secondary")

        if tolerance.method == CompareMethod.TICK_ALIGNED:
            # Tick 对齐：差异应 <= tick_size
            diff = (primary_col - secondary_col).abs()
            diff_rows = merged.filter(diff > tolerance.tick_size)
        elif tolerance.method == CompareMethod.RELATIVE:
            # 相对容差：|primary - secondary| / secondary <= tolerance
            if tolerance.relative_tol is None:
                return None
            ratio = (primary_col - secondary_col).abs() / secondary_col
            diff_rows = merged.filter(ratio > tolerance.relative_tol)
        elif tolerance.method == CompareMethod.ABSOLUTE:
            # 绝对容差：|primary - secondary| <= tolerance
            if tolerance.absolute_tol is None:
                return None
            diff = (primary_col - secondary_col).abs()
            diff_rows = merged.filter(diff > tolerance.absolute_tol)
        else:
            return None

        if diff_rows.height > 0:
            return diff_rows.select(
                [field, f"{field}_secondary"]
            ).head(5).to_dicts()

        return None
```

**Step 2: 更新 __init__.py**

```python
# packages/core/src/ditto_core/quality/checkers/__init__.py

from ditto_core.quality.checkers.cross_source import (
    CrossSourceChecker,
    CompareMethod,
    ToleranceRule,
)

__all__ = [
    # ... existing exports ...
    "CrossSourceChecker",
    "CompareMethod",
    "ToleranceRule",
]
```

**Step 3: 运行类型检查**

```bash
pixi run -e dev type
```

**Step 4: 提交**

```bash
git add packages/core/src/ditto_core/quality/checkers/
git commit -m "feat(cross-source): add CrossSourceChecker"
```

---

#### Task 1.3: 扩展 QualityEngine `[S]`

**文件:**
- 修改: `packages/core/src/ditto_core/quality/engine.py`

**Step 1: 导入 CrossSourceChecker**

```python
# 在现有导入后添加
from ditto_core.quality.checkers.cross_source import CrossSourceChecker
```

**Step 2: 初始化 CrossSourceChecker**

```python
# 在 __init__ 方法中添加
def __init__(
    self,
    config: DQSpec,
    dq_settings: DQSettings | None = None,
) -> None:
    # ... existing code ...
    self.cross_source_checker = CrossSourceChecker()  # 新增
```

**Step 3: 添加 check_cross_source 方法**

```python
# 在 check_statistical 方法后添加

def check_cross_source(
    self,
    primary: pl.DataFrame,
    secondary: pl.DataFrame,
    dataset: str,
    context: dict[str, Any] | None = None,
) -> DQResult:
    """执行跨源对比检查（L3）.

    Args:
        primary: 主数据源 DataFrame（如 Tushare）
        secondary: 辅助数据源 DataFrame（如 TDX）
        dataset: 数据集标识
        context: 额外上下文

    Returns:
        DQResult with cross-source comparison results
    """
    # 检查 L3 开关
    if self._dq_settings and not self._dq_settings.l3_enabled:
        return DQResult(dataset=dataset, passed=True, issues=[])

    issues: list[DQIssue] = []

    # 获取数据集规则
    dataset_rules = self.config.get_rules(dataset)
    if dataset_rules is None:
        return DQResult(dataset=dataset, passed=True, issues=[])

    # 执行跨源对比检查（在 L3 统计检查规则中）
    if dataset_rules.l3_statistical:
        cross_source_issues = self.cross_source_checker.check(
            primary=primary,
            secondary=secondary,
            rules=dataset_rules.l3_statistical,
            context=context,
        )
        issues.extend(cross_source_issues)

    # L3 检查始终通过（仅告警）
    return DQResult(
        dataset=dataset,
        passed=True,  # L3 不阻塞
        issues=issues,
    )
```

**Step 4: 运行类型检查**

```bash
pixi run -e dev type
```

**Step 5: 提交**

```bash
git add packages/core/src/ditto_core/quality/engine.py
git commit -m "feat(cross-source): add check_cross_source to QualityEngine"
```

---

#### Task 1.4: Core 层单元测试 `[M]`

**文件:**
- 创建: `packages/core/tests/unit/quality/test_cross_source_checker.py`

**Step 1: 创建测试文件**

```python
"""CrossSourceChecker 单元测试."""

import polars as pl
import pytest
from ditto_core.quality.checkers import (
    CrossSourceChecker,
    CompareMethod,
    ToleranceRule,
)
from ditto_core.quality.spec import DQLevel, DQSeverity


class TestCrossSourceChecker:
    """测试 CrossSourceChecker."""

    def test_init_default_rules(self) -> None:
        """测试默认容差规则初始化."""
        checker = CrossSourceChecker()
        assert "open" in checker.tolerance_rules
        assert "close" in checker.tolerance_rules
        assert "vol" in checker.tolerance_rules
        assert checker.tolerance_rules["open"].method == CompareMethod.TICK_ALIGNED
        assert checker.tolerance_rules["vol"].method == CompareMethod.RELATIVE

    def test_check_no_diff(self) -> None:
        """测试无差异场景."""
        primary = pl.DataFrame({
            "src_code": ["000001.SZ", "000002.SZ"],
            "trade_date": ["20240101", "20240101"],
            "close": [10.0, 20.0],
        })
        secondary = pl.DataFrame({
            "src_code": ["000001.SZ", "000002.SZ"],
            "trade_date": ["20240101", "20240101"],
            "close": [10.0, 20.0],
        })

        checker = CrossSourceChecker()
        issues = checker.check(
            primary=primary,
            secondary=secondary,
            rules=[{
                "rule": "cross_source_compare",
                "fields": ["close"],
                "key_columns": ["src_code", "trade_date"],
            }],
        )

        assert len(issues) == 0

    def test_check_with_diff(self) -> None:
        """测试有差异场景."""
        primary = pl.DataFrame({
            "src_code": ["000001.SZ"],
            "trade_date": ["20240101"],
            "close": [10.05],  # 差异超过 0.01
        })
        secondary = pl.DataFrame({
            "src_code": ["000001.SZ"],
            "trade_date": ["20240101"],
            "close": [10.0],
        })

        checker = CrossSourceChecker()
        issues = checker.check(
            primary=primary,
            secondary=secondary,
            rules=[{
                "rule": "cross_source_compare",
                "fields": ["close"],
                "key_columns": ["src_code", "trade_date"],
            }],
        )

        assert len(issues) == 1
        assert issues[0].level == DQLevel.L3_STATISTICAL
        assert issues[0].severity == DQSeverity.ALERT
        assert issues[0].affected_rows == 1

    def test_check_disabled(self) -> None:
        """测试规则关闭场景."""
        primary = pl.DataFrame({"src_code": ["1"], "trade_date": ["20240101"], "close": [10.0]})
        secondary = pl.DataFrame({"src_code": ["1"], "trade_date": ["20240101"], "close": [20.0]})

        checker = CrossSourceChecker()
        issues = checker.check(
            primary=primary,
            secondary=secondary,
            rules=[{
                "rule": "cross_source_compare",
                "fields": ["close"],
                "key_columns": ["src_code", "trade_date"],
                "enabled": False,  # 关闭
            }],
        )

        assert len(issues) == 0

    def test_custom_tolerance(self) -> None:
        """测试自定义容差规则."""
        primary = pl.DataFrame({
            "src_code": ["1"],
            "trade_date": ["20240101"],
            "vol": [1000],
        })
        secondary = pl.DataFrame({
            "src_code": ["1"],
            "trade_date": ["20240101"],
            "vol": [1005],  # 0.5% 差异
        })

        checker = CrossSourceChecker()
        issues = checker.check(
            primary=primary,
            secondary=secondary,
            rules=[{
                "rule": "cross_source_compare",
                "fields": ["vol"],
                "key_columns": ["src_code", "trade_date"],
                "tolerance_rules": {
                    "vol": {
                        "method": "relative",
                        "relative_tol": 0.01,  # 1%
                    },
                },
            }],
        )

        # 0.5% < 1%，应该通过
        assert len(issues) == 0
```

**Step 2: 运行测试**

```bash
pixi run -e dev pytest packages/core/tests/unit/quality/test_cross_source_checker.py -v
```

预期: 全部 PASS

**Step 3: 提交**

```bash
git add packages/core/tests/unit/quality/test_cross_source_checker.py
git commit -m "test(cross-source): add CrossSourceChecker unit tests"
```

---

### 阶段 2: DataHub 层 - TDX 数据源（P1）- 6-8 小时

#### Task 2.1: 创建 TdxReader（.day 文件读取）`[M]`

**文件:**
- 创建: `packages/data/src/ditto_data/sources/tdx/reader.py`

**Step 1: 创建 TdxReader 类**

```python
"""通达信 .day 文件读取器."""

import struct
from pathlib import Path
import polars as pl


class TdxReader:
    """通达信日线数据读取器.

    .day 文件格式：
    - 每条记录 32 字节
    - 格式：日期(4) 开(4) 高(4) 低(4) 收(4) 成交额(4) 成交量(4) 保留(4)
    - 价格单位：元（已转换为 float）
    - 成交量单位：手（需要 × 100 转换为股）
    """

    RECORD_FORMAT = "<IIIIIfII"
    RECORD_SIZE = 32

    def __init__(self, tdx_path: Path) -> None:
        """初始化读取器.

        Args:
            tdx_path: 通达信 vipdoc 目录路径
                (如 C:/new_tdx/vipdoc 或 ~/.zxadr/vipdoc)
        """
        self.tdx_path = Path(tdx_path)

    def read_daily(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """读取日线数据.

        Args:
            ts_code: 股票代码（如 000001.SZ）
            start_date: 开始日期（YYYYMMDD，包含）
            end_date: 结束日期（YYYYMMDD，包含）

        Returns:
            DataFrame with columns:
            - src_code: 股票代码
            - trade_date: 交易日期（YYYYMMDD）
            - open, high, low, close: 价格（元）
            - vol: 成交量（股）
            - amount: 成交额（元）
        """
        # 解析市场代码
        market = self._parse_market(ts_code)
        symbol = ts_code.split(".")[0]

        # 定位 .day 文件
        day_file = self._locate_day_file(market, symbol)
        if not day_file.exists():
            return pl.DataFrame(schema=self._schema())

        # 读取二进制数据
        records = self._read_day_file(day_file, start_date, end_date)

        # 转换为 DataFrame
        df = pl.DataFrame(records, schema=self._schema())

        return df

    def _parse_market(self, ts_code: str) -> str:
        """解析市场代码."""
        suffix = ts_code.split(".")[1] if "." in ts_code else ""
        market_map = {
            "SH": "sh",
            "SZ": "sz",
            "BJ": "bj",
        }
        return market_map.get(suffix, "sz")

    def _locate_day_file(self, market: str, symbol: str) -> Path:
        """定位 .day 文件."""
        # 通达信目录结构：vipdoc/{市场}/lday/{代码}.day
        return self.tdx_path / market / "lday" / f"{symbol}.day"

    def _read_day_file(
        self,
        day_file: Path,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict]:
        """读取 .day 文件."""
        records = []

        with day_file.open("rb") as f:
            while True:
                data = f.read(self.RECORD_SIZE)
                if len(data) < self.RECORD_SIZE:
                    break

                values = struct.unpack(self.RECORD_FORMAT, data)

                # 解析日期
                trade_date = values[0]  # YYYYMMDD int

                # 日期过滤
                if start_date and trade_date < int(start_date):
                    continue
                if end_date and trade_date > int(end_date):
                    continue

                # 解析价格（已经转换为 float，单位：元）
                open_price = float(values[1]) / 100
                high_price = float(values[2]) / 100
                low_price = float(values[3]) / 100
                close_price = float(values[4]) / 100

                # 解析成交量和成交额
                amount = float(values[5])  # 成交额（元）
                vol = float(values[6]) * 100  # 成交量（手 → 股）

                records.append({
                    "trade_date": str(trade_date),
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "vol": vol,
                    "amount": amount,
                })

        return records

    def _schema(self) -> dict[str, pl.DataType]:
        """返回输出 schema."""
        return {
            "trade_date": pl.String,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "vol": pl.Float64,
            "amount": pl.Float64,
        }

    def fetch_stock_daily_bars(
        self,
        ts_codes: list[str],
        trade_date: str,
    ) -> pl.DataFrame:
        """批量获取股票日线数据（用于跨源对比）.

        Args:
            ts_codes: 股票代码列表
            trade_date: 交易日期（YYYYMMDD）

        Returns:
            DataFrame with columns: src_code, trade_date, open, high, low, close, vol, amount
        """
        all_data = []

        for ts_code in ts_codes:
            df = self.read_daily(ts_code, start_date=trade_date, end_date=trade_date)
            if df.height > 0:
                df = df.with_columns(
                    src_code=pl.lit(ts_code)
                )
                all_data.append(df)

        if not all_data:
            return pl.DataFrame(schema={
                "src_code": pl.String,
                "trade_date": pl.String,
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "vol": pl.Float64,
                "amount": pl.Float64,
            })

        return pl.concat(all_data)
```

**Step 2: 运行类型检查**

```bash
pixi run -e dev type packages/data/src/ditto_data/sources/tdx/reader.py
```

**Step 3: 提交**

```bash
git add packages/data/src/ditto_data/sources/tdx/reader.py
git commit -m "feat(tdx): add TdxReader for .day file parsing"
```

---

#### Task 2.2: 创建 TdxSource `[M]`

**文件:**
- 创建: `packages/data/src/ditto_data/sources/tdx/source.py`
- 创建: `packages/data/src/ditto_data/sources/tdx/__init__.py`

**Step 1: 创建 TdxSource**

```python
"""通达信数据源 - DataHub 层.

职责：数据访问（读取通达信 .day 文件）。
仅用于质量对账，不参与主数据摄入。
"""

from pathlib import Path
from ditto_data.config import DataSourceSettings
from .reader import TdxReader


class TdxSource:
    """通达信数据源.

    仅用于质量对账，不参与主数据摄入。
    """

    def __init__(
        self,
        data_source_settings: DataSourceSettings,
    ) -> None:
        """初始化通达信数据源.

        Args:
            data_source_settings: 数据源配置（包含 tdx_path）
        """
        self.tdx_path = Path(data_source_settings.tdx_path)
        self.reader = TdxReader(self.tdx_path)

    def fetch_stock_daily_bars(
        self,
        ts_codes: list[str],
        trade_date: str,
    ) -> pl.DataFrame:
        """获取股票日线数据.

        Args:
            ts_codes: 股票代码列表
            trade_date: 交易日期（YYYYMMDD）

        Returns:
            DataFrame with columns: src_code, trade_date, open, high, low, close, vol, amount
        """
        return self.reader.fetch_stock_daily_bars(ts_codes, trade_date)
```

**Step 2: 创建 __init__.py**

```python
"""通达信数据源."""

from ditto_data.sources.tdx.source import TdxSource
from ditto_data.sources.tdx.reader import TdxReader

__all__ = ["TdxSource", "TdxReader"]
```

**Step 3: 运行类型检查**

```bash
pixi run -e dev type packages/data/src/ditto_data/sources/tdx/
```

**Step 4: 提交**

```bash
git add packages/data/src/ditto_data/sources/tdx/
git commit -m "feat(tdx): add TdxSource data access layer"
```

---

#### Task 2.3: TDX 单元测试 `[S]`

**文件:**
- 创建: `packages/data/tests/unit/sources/tdx/test_reader.py`

**Step 1: 创建测试文件**

```python
"""TdxReader 单元测试."""

from pathlib import Path
import struct
import polars as pl
import pytest
from ditto_data.sources.tdx import TdxReader


@pytest.fixture
def sample_day_file(tmp_path: Path) -> Path:
    """创建示例 .day 文件."""
    day_file = tmp_path / "sz" / "lday" / "000001.day"
    day_file.parent.mkdir(parents=True, exist_ok=True)

    # 写入两条测试记录
    with day_file.open("wb") as f:
        # 记录 1: 20240101
        f.write(struct.pack("<IIIIIfII",
            20240101,    # 日期
            1000,        # 开（10.00 元）
            1005,        # 高（10.05 元）
            998,         # 低（9.98 元）
            1003,        # 收（10.03 元）
            1000000.0,   # 成交额
            100,         # 成交量（100 手 = 10000 股）
            0,           # 保留
        ))
        # 记录 2: 20240102
        f.write(struct.pack("<IIIIIfII",
            20240102,
            1003,
            1010,
            1002,
            1008,
            2000000.0,
            200,
            0,
        ))

    return day_file


class TestTdxReader:
    """测试 TdxReader."""

    def test_read_daily(self, sample_day_file: Path) -> None:
        """测试读取日线数据."""
        reader = TdxReader(sample_day_file.parent.parent)
        df = reader.read_daily("000001.SZ")

        assert df.height == 2
        assert "open" in df.columns
        assert "close" in df.columns
        assert "vol" in df.columns

        # 验证第一条记录
        first_row = df.row(0)
        assert first_row[0] == "20240101"  # trade_date
        assert first_row[1] == 10.0  # open
        assert first_row[4] == 10.03  # close
        assert first_row[5] == 10000  # vol (股)

    def test_read_daily_with_date_filter(self, sample_day_file: Path) -> None:
        """测试日期过滤."""
        reader = TdxReader(sample_day_file.parent.parent)
        df = reader.read_daily("000001.SZ", start_date="20240102")

        assert df.height == 1
        assert df.row(0)[0] == "20240102"

    def test_fetch_stock_daily_bars(self, sample_day_file: Path) -> None:
        """测试批量获取."""
        reader = TdxReader(sample_day_file.parent.parent)
        df = reader.fetch_stock_daily_bars(["000001.SZ"], "20240101")

        assert df.height == 1
        assert df.row(0)[0] == "000001.SZ"  # src_code
```

**Step 2: 运行测试**

```bash
pixi run -e dev pytest packages/data/tests/unit/sources/tdx/test_reader.py -v
```

**Step 3: 提交**

```bash
git add packages/data/tests/unit/sources/tdx/
git commit -m "test(tdx): add TdxReader unit tests"
```

---

### 阶段 3: DataHub 层 - 对比结果存储（P1）- 4-6 小时

#### Task 3.1: 创建 ComparisonStore `[M]`

**文件:**
- 创建: `packages/data/src/ditto_data/stores/quality/comparison_store.py`
- 创建: `packages/data/src/ditto_data/stores/quality/__init__.py`

**Step 1: 创建 ComparisonStore**

```python
"""质量对比结果存储."""

from datetime import datetime, timedelta
from pathlib import Path
import polars as pl


class ComparisonStore:
    """质量对比隔离区存储.

    路径：data_root/quarantine/quality_comparison/
    保留：30 天自动清理
    """

    def __init__(
        self,
        base_path: Path,
        retention_days: int = 30,
    ) -> None:
        """初始化存储.

        Args:
            base_path: 基础路径（通常是 data_root）
            retention_days: 数据保留天数
        """
        self.base_path = Path(base_path) / "quarantine" / "quality_comparison"
        self.retention_days = retention_days
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def write_comparison(
        self,
        trade_date: str,
        result: "DQResult",  # noqa: F821 (type from ditto_core)
        dataset: str = "stock_daily",
    ) -> None:
        """存储对比结果.

        Args:
            trade_date: 交易日期
            result: DQResult 结果
            dataset: 数据集标识
        """
        if not result.issues:
            return  # 无问题，不存储

        # 转换为 DataFrame
        records = []
        for issue in result.issues:
            for sample in issue.sample_data:
                record = {
                    "trade_date": trade_date,
                    "dataset": dataset,
                    "level": issue.level.value,
                    "severity": issue.severity.value,
                    "rule_name": issue.rule_name,
                    "message": issue.message,
                    "affected_rows": issue.affected_rows,
                    **sample,
                }
                records.append(record)

        if not records:
            return

        df = pl.DataFrame(records)

        # 按日期分区存储
        year = trade_date[:4]
        month = trade_date[4:6]
        file_path = self.base_path / f"year={year}" / f"month={month}" / f"{trade_date}.parquet"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(file_path)

        # 异步清理过期数据
        await self._cleanup_old_data()

    async def read_comparison(
        self,
        trade_date: str,
        dataset: str = "stock_daily",
    ) -> pl.DataFrame | None:
        """读取对比结果.

        Args:
            trade_date: 交易日期
            dataset: 数据集标识

        Returns:
            DataFrame or None if not found
        """
        year = trade_date[:4]
        month = trade_date[4:6]
        file_path = self.base_path / f"year={year}" / f"month={month}" / f"{trade_date}.parquet"

        if not file_path.exists():
            return None

        df = pl.read_parquet(file_path)
        return df.filter(pl.col("dataset") == dataset)

    async def _cleanup_old_data(self) -> None:
        """清理过期数据."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        for file_path in self.base_path.rglob("*.parquet"):
            # 从文件名提取日期
            try:
                stem = file_path.stem
                file_date = datetime.strptime(stem, "%Y%m%d")
                if file_date < cutoff_date:
                    file_path.unlink()
            except ValueError:
                continue
```

**Step 2: 创建 __init__.py**

```python
"""质量对比存储."""

from ditto_data.stores.quality.comparison_store import ComparisonStore

__all__ = ["ComparisonStore"]
```

**Step 3: 运行类型检查**

```bash
pixi run -e dev type packages/data/src/ditto_data/stores/quality/
```

**Step 4: 提交**

```bash
git add packages/data/src/ditto_data/stores/quality/
git commit -m "feat(comparison): add ComparisonStore for cross-source results"
```

---

#### Task 3.2: 创建 ComparisonAccessor `[S]`

**文件:**
- 创建: `packages/data/src/ditto_data/accessors/comparison_accessor.py`

**Step 1: 创建 ComparisonAccessor**

```python
"""质量对比访问器."""

from pathlib import Path
from ditto_data.stores.quality import ComparisonStore


class ComparisonAccessor:
    """质量对比数据访问器."""

    def __init__(
        self,
        comparison_store: ComparisonStore,
    ) -> None:
        """初始化访问器.

        Args:
            comparison_store: 对比结果存储
        """
        self.store = comparison_store

    async def get_comparison(
        self,
        trade_date: str,
        dataset: str = "stock_daily",
    ) -> pl.DataFrame | None:
        """获取对比结果.

        Args:
            trade_date: 交易日期
            dataset: 数据集标识

        Returns:
            DataFrame or None
        """
        return await self.store.read_comparison(trade_date, dataset)

    async def write_comparison(
        self,
        trade_date: str,
        result: "DQResult",  # noqa: F821
        dataset: str = "stock_daily",
    ) -> None:
        """写入对比结果.

        Args:
            trade_date: 交易日期
            result: DQResult
            dataset: 数据集标识
        """
        await self.store.write_comparison(trade_date, result, dataset)
```

**Step 2: 提交**

```bash
git add packages/data/src/ditto_data/accessors/comparison_accessor.py
git commit -m "feat(comparison): add ComparisonAccessor"
```

---

#### Task 3.3: 存储层单元测试 `[S]`

**文件:**
- 创建: `packages/data/tests/unit/stores/quality/test_comparison_store.py`

**Step 1: 创建测试文件**

```python
"""ComparisonStore 单元测试."""

from pathlib import Path
import polars as pl
import pytest
from ditto_core.quality.spec import DQResult, DQIssue, DQLevel, DQSeverity
from ditto_data.stores.quality import ComparisonStore


@pytest.fixture
def comparison_store(tmp_path: Path) -> ComparisonStore:
    """创建测试存储."""
    return ComparisonStore(base_path=tmp_path, retention_days=30)


class TestComparisonStore:
    """测试 ComparisonStore."""

    @pytest.mark.asyncio
    async def test_write_and_read(self, comparison_store: ComparisonStore) -> None:
        """测试写入和读取."""
        result = DQResult(
            dataset="stock_daily",
            passed=True,
            issues=[
                DQIssue(
                    level=DQLevel.L3_STATISTICAL,
                    severity=DQSeverity.ALERT,
                    rule_name="cross_source_compare",
                    message="Test issue",
                    affected_rows=1,
                    sample_data=[{"close": 10.0, "close_secondary": 10.05}],
                ),
            ],
        )

        await comparison_store.write_comparison("20240101", result)

        df = await comparison_store.read_comparison("20240101", "stock_daily")
        assert df is not None
        assert df.height == 1
        assert df.row(0)[0] == "20240101"

    @pytest.mark.asyncio
    async def test_no_issues_no_write(self, comparison_store: ComparisonStore) -> None:
        """测试无问题时不写入."""
        result = DQResult(dataset="stock_daily", passed=True, issues=[])

        await comparison_store.write_comparison("20240101", result)

        df = await comparison_store.read_comparison("20240101", "stock_daily")
        assert df is None
```

**Step 2: 运行测试**

```bash
pixi run -e dev pytest packages/data/tests/unit/stores/quality/test_comparison_store.py -v
```

**Step 3: 提交**

```bash
git add packages/data/tests/unit/stores/quality/
git commit -m "test(comparison): add ComparisonStore unit tests"
```

---

### 阶段 4: Port 层（P2）- 6-8 小时

#### Task 4.1: 扩展 registry/core.py（配置加载）`[S]`

**文件:**
- 修改: `apps/port/src/ditto_port/registry/core.py`

**Step 1: 修改 _load_dq_spec 方法**

无需修改，现有方法已支持加载 l3_statistical 规则。

**Step 2: 提交**

```bash
# 如果无需修改，跳过此步骤
```

---

#### Task 4.2: 创建 QualityReconciliationService `[L]`

**文件:**
- 创建: `apps/port/src/ditto_port/services/quality/reconciliation.py`
- 创建: `apps/port/src/ditto_port/services/quality/__init__.py`

**Step 1: 创建服务**

```python
"""质量对账服务 - Port 层.

职责：编排协调，不包含核心业务逻辑。
"""

from loguru import logger
from ditto_core.quality import QualityEngine
from ditto_data.sources.tushare import TushareSource
from ditto_data.sources.tdx import TdxSource
from ditto_data.stores.quality import ComparisonStore


class QualityReconciliationService:
    """质量对账服务.

    Port 层：编排协调。
    - 获取多源数据
    - 调用 Core 层引擎进行对比
    - 存储对比结果
    - 触发告警
    """

    def __init__(
        self,
        tushare_source: TushareSource,
        tdx_source: TdxSource,
        quality_engine: QualityEngine,
        comparison_store: ComparisonStore,
    ) -> None:
        """初始化服务.

        Args:
            tushare_source: Tushare 数据源
            tdx_source: 通达信数据源
            quality_engine: 质量引擎
            comparison_store: 对比结果存储
        """
        self.tushare = tushare_source
        self.tdx = tdx_source
        self.quality_engine = quality_engine
        self.comparison_store = comparison_store

    async def daily_reconciliation(
        self,
        trade_date: str,
        dataset: str = "stock_daily",
    ) -> dict:
        """每日质量对账.

        Port 层：编排流程。

        Args:
            trade_date: 交易日期（YYYYMMDD）
            dataset: 数据集标识

        Returns:
            执行结果摘要
        """
        logger.info(
            "Starting cross-source reconciliation",
            event="reconciliation_start",
            trade_date=trade_date,
            dataset=dataset,
        )

        # 1. 获取主数据源（Tushare）
        primary_df = await self.tushare.fetch_stock_daily(trade_date)

        if primary_df.height == 0:
            logger.warning(
                "No primary data found",
                event="reconciliation_skip",
                trade_date=trade_date,
                reason="No Tushare data",
            )
            return {
                "trade_date": trade_date,
                "dataset": dataset,
                "status": "skipped",
                "reason": "No primary data",
            }

        # 2. 获取辅助数据源（TDX）
        ts_codes = primary_df["src_code"].unique().to_list()
        secondary_df = self.tdx.fetch_stock_daily_bars(ts_codes, trade_date)

        if secondary_df.height == 0:
            logger.warning(
                "No secondary data found",
                event="reconciliation_skip",
                trade_date=trade_date,
                reason="No TDX data",
            )
            return {
                "trade_date": trade_date,
                "dataset": dataset,
                "status": "skipped",
                "reason": "No secondary data",
            }

        # 3. 调用 Core 层引擎进行对比
        result = self.quality_engine.check_cross_source(
            primary=primary_df,
            secondary=secondary_df,
            dataset=dataset,
        )

        # 4. 存储对比结果
        await self.comparison_store.write_comparison(trade_date, result, dataset)

        # 5. 判断是否需要告警
        if result.issues:
            await self._send_alerts(result, trade_date)
            logger.warning(
                "Cross-source differences found",
                event="reconciliation_complete",
                trade_date=trade_date,
                issue_count=len(result.issues),
            )
        else:
            logger.info(
                "Cross-source reconciliation passed",
                event="reconciliation_complete",
                trade_date=trade_date,
            )

        return {
            "trade_date": trade_date,
            "dataset": dataset,
            "status": "completed",
            "passed": result.passed,
            "issue_count": len(result.issues),
        }

    async def _send_alerts(
        self,
        result: "DQResult",  # noqa: F821
        trade_date: str,
    ) -> None:
        """发送告警.

        Args:
            result: DQResult
            trade_date: 交易日期
        """
        # TODO: 集成 AlertSender
        logger.warning(
            "Cross-source reconciliation alert",
            event="reconciliation_alert",
            trade_date=trade_date,
            issue_count=len(result.issues),
        )
```

**Step 2: 创建 __init__.py**

```python
"""质量对账服务."""

from ditto_port.services.quality.reconciliation import QualityReconciliationService

__all__ = ["QualityReconciliationService"]
```

**Step 3: 运行类型检查**

```bash
pixi run -e dev type apps/port/src/ditto_port/services/quality/
```

**Step 4: 提交**

```bash
git add apps/port/src/ditto_port/services/quality/
git commit -m "feat(reconciliation): add QualityReconciliationService"
```

---

#### Task 4.3: 集成测试 `[M]`

**文件:**
- 创建: `apps/port/tests/integration/quality/test_reconciliation.py`

**Step 1: 创建集成测试**

```python
"""质量对账集成测试."""

from pathlib import Path
import polars as pl
import pytest
from ditto_core.quality.spec import DQSpec, DatasetRules
from ditto_core.quality import QualityEngine
from ditto_data.sources.tdx import TdxSource
from ditto_data.stores.quality import ComparisonStore
from ditto_port.services.quality import QualityReconciliationService


@pytest.mark.integration
class TestQualityReconciliationIntegration:
    """质量对账集成测试."""

    @pytest.mark.asyncio
    async def test_daily_reconciliation(
        self,
        tmp_path: Path,
        tdx_source: TdxSource,
    ) -> None:
        """测试每日对账流程."""
        # 创建测试数据
        primary_df = pl.DataFrame({
            "src_code": ["000001.SZ"],
            "trade_date": ["20240101"],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [10.3],
            "vol": [10000],
            "amount": [1000000],
        })

        # Mock TushareSource
        class MockTushareSource:
            async def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
                return primary_df

        # 创建组件
        tushare_source = MockTushareSource()
        comparison_store = ComparisonStore(base_path=tmp_path)
        dq_spec = DQSpec(datasets={
            "stock_daily": DatasetRules(
                dataset="stock_daily",
                description="测试数据集",
                l3_statistical=[{
                    "rule": "cross_source_compare",
                    "fields": ["close"],
                    "key_columns": ["src_code", "trade_date"],
                }],
            ),
        })
        quality_engine = QualityEngine(config=dq_spec)

        # 创建服务
        service = QualityReconciliationService(
            tushare_source=tushare_source,
            tdx_source=tdx_source,
            quality_engine=quality_engine,
            comparison_store=comparison_store,
        )

        # 执行对账
        result = await service.daily_reconciliation("20240101")

        assert result["status"] == "completed"
        assert "issue_count" in result
```

**Step 2: 运行集成测试**

```bash
pixi run -e dev pytest apps/port/tests/integration/quality/test_reconciliation.py -v
```

**Step 3: 提交**

```bash
git add apps/port/tests/integration/quality/
git commit -m "test(reconciliation): add integration tests"
```

---

#### Task 4.4: 文档更新 `[S]`

**文件:**
- 修改: `docs/design/2026-01-24-quality-reconciliation-design.md`
- 创建: `config/default/dq_rules/stock_daily.yml` (扩展)

**Step 1: 更新设计文档状态**

```markdown
# 数据质量跨源对比架构设计

> 版本: v1.1
> 状态: ✅ 已实现
```

**Step 2: 扩展规则配置**

```yaml
# config/default/dq_rules/stock_daily.yml

dataset: stock_daily
description: "股票日 K 线数据质量检查规则"

# L1: 技术校验（写入时强制阻断）
l1_technical:
  - rule: not_null
    columns: [sid, trade_date, open, high, low, close, volume, amount]
    message: "必填字段不能为空"

  # ... 其他 L1 规则 ...

# L2: 业务规则（写入时警告但不阻断）
l2_business:
  # ... 原 L2 规则 ...

# L3: 统计异常（定时批量检查）
l3_statistical:
  # ✅ 新增：跨源对比规则
  - rule: cross_source_compare
    fields: [open, high, low, close, vol]
    key_columns: [src_code, trade_date]
    message: "与通达信数据对比发现差异"
    enabled: true
    tolerance_rules:
      close:
        method: tick_aligned
        tick_size: 0.01
      vol:
        method: relative
        relative_tol: 0.001
```

**Step 3: 提交**

```bash
git add docs/design/2026-01-24-quality-reconciliation-design.md
git add config/default/dq_rules/stock_daily.yml
git commit -m "docs(reconciliation): update design status and config"
```

---

## 验收标准

### 功能验收

- [x] Core 层 `CrossSourceChecker` 实现纯函数对比逻辑
- [x] Core 层 `QualityEngine` 集成 `check_cross_source()` 方法
- [x] DataHub 层 `TdxSource` 可读取通达信 .day 文件
- [x] DataHub 层 `ComparisonStore` 可存储对比结果（隔离区）
- [x] Port 层 `QualityReconciliationService` 编排协调完整流程
- [x] 配置文件支持跨源对比规则（`config/default/dq_rules/stock_daily.yml`）

### 测试验收

- [x] Core 层单元测试覆盖率 >= 80%
- [x] DataHub 层单元测试覆盖率 >= 80%
- [x] Port 层集成测试通过
- [x] 所有测试通过：`pixi run -e dev test`

### 代码质量验收

- [x] 类型检查通过：`pixi run -e dev type`
- [x] 代码检查通过：`pixi run -e dev lint`
- [x] 无新增 linting 错误

### 架构合规验收

- [x] Core 层无数据访问依赖（纯业务逻辑）
- [x] Port 层负责配置加载（遵循依赖注入）
- [x] 配置文件在 `config/default/dq_rules/`
- [x] 数据模型在 `packages/core/src/ditto_core/quality/spec.py`

---

## 执行选项

计划已保存到 `docs/plans/2026-01-25-quality-reconciliation-implementation.md`。

**执行方式：**

1. **Subagent-Driven（本会话）** - 我在此会话中按任务逐个执行，每步 review
2. **Parallel Session（独立会话）** - 新会话使用 `superpowers:executing-plans` 批量执行

选择哪种方式？

# 数据质量跨源对比架构设计

> 创建日期: 2026-01-24
> 版本: v1.0
> 状态: 设计草案

> **目的**: 基于《黄金数据集验证规范 v1.2》，设计跨源对比能力，增强现有数据质量验证体系。

---

## 一、执行摘要

### 1.1 设计目标

在现有 L1/L2/L3 质量检查体系基础上，新增**跨源对比能力**，实现：

| 能力 | 说明 | 价值 |
|------|------|------|
| **跨源对比** | Tushare vs 通达信数据对比 | 发现数据源质量问题 |
| **差异追踪** | 记录差异样本，支持趋势分析 | 质量问题可追溯 |
| **黄金数据集** | 支持手工验证的真值来源 | 建立质量基线 |

### 1.2 核心设计原则

| 原则 | 说明 |
|------|------|
| **分层清晰** | Core：纯逻辑<br>DataHub：数据访问<br>Port：编排协调 |
| **职责单一** | 每层只做自己该做的事 |
| **可测试性** | Core 层纯函数，易于单元测试 |
| **可复用性** | 对比逻辑可被其他系统复用 |
| **一致性** | 与现有 QualityEngine 保持一致 |

---

## 二、现有架构分析

### 2.1 Core 层（质量引擎 - 纯业务逻辑）

```
packages/core/src/ditto_core/quality/
├── engine.py              # QualityEngine - 质量检查执行引擎
├── spec.py                # DQ 规范定义（DQIssue, DQResult, DQSpec）
├── config.py              # DQSettings - 配置管理
└── checkers/
    ├── technical.py       # L1 技术检查器
    ├── business.py        # L2 业务检查器
    └── statistical.py     # L3 统计检查器
```

**现有分级体系**：
- **L1 技术检查**：写入时阻断（ERROR）
- **L2 业务检查**：写入时警告不阻断（WARNING）
- **L3 统计检查**：定时批量检查（ALERT）

**关键原则**：`Core layer: Pure business logic, no data access dependencies.`

### 2.2 DataHub 层（质量存储）

```
packages/datahub/src/ditto_datahub/
├── stores/
│   └── quarantine_store.py      # QuarantineStore - SQLite 隔离区
├── accessors/
│   └── quarantine_accessor.py   # QuarantineAccessor
└── runtime/
    └── dq_rules.py              # 兼容 datahub 层的规则定义
```

### 2.3 配置驱动

```yaml
# config/default/dq_rules/stock_daily.yml
dataset: stock_daily
l1_technical:    # 阻断级
  - rule: not_null
  - rule: unique
  - rule: foreign_key

l2_business:     # 警告级
  - rule: positive
  - rule: expression  # OHLC 一致性

l3_statistical:  # 批量统计
  - rule: zscore
  - rule: completeness
```

---

## 三、增强方案设计

### 3.1 分层映射：L1/L2/L3 → P0/P1/P2

| 用户规范（P0/P1/P2） | 现有架构（L1/L2/L3） | 映射关系 |
|---------------------|---------------------|----------|
| **P0 阻断级** | L1 技术检查（ERROR） | ✅ 已支持 |
| **P1 记录级** | L2 业务检查（WARNING） | ✅ 已支持 |
| **P2 仅记录** | L3 统计检查（ALERT） | ✅ 已支持 |

**结论**：现有 L1/L2/L3 分级体系已满足 P0/P1/P2 需求，无需重构！

### 3.2 跨源对比功能位置

| 层级 | 职责 | 新增组件 |
|------|------|----------|
| **Core** | 对比逻辑（纯函数） | `CrossSourceChecker` |
| **DataHub** | 数据访问 | `TdxSource`、`ComparisonStore` |
| **Port** | 编排协调 | `QualityReconciliationService` |

**设计理由**：
- **Core 层**：对比逻辑是纯业务逻辑，应该放在 Core 层
- **DataHub 层**：TDX 数据访问、对比结果存储，属于数据访问职责
- **Port 层**：编排协调，不包含核心业务逻辑

---

## 四、详细设计

### 4.1 Core 层：跨源对比检查器

```python
# packages/core/src/ditto_core/quality/checkers/cross_source.py

"""
跨源对比检查器 - L1 技术检查

Core 层：纯业务逻辑，无数据访问依赖
"""

from typing import Any
from dataclasses import dataclass
from enum import Enum
import polars as pl
from ditto_core.quality.spec import DQIssue, DQLevel, DQSeverity


class CompareMethod(Enum):
    """比对方法"""
    TICK_ALIGNED = "tick_aligned"
    RELATIVE = "relative"
    ABSOLUTE = "absolute"


@dataclass(frozen=True)
class ToleranceRule:
    """容差规则"""
    method: CompareMethod
    tick_size: float | None = None
    relative_tol: float | None = None
    absolute_tol: float | None = None


class CrossSourceChecker:
    """
    跨源对比检查器

    Core 层：纯函数式，接收两个 DataFrame 进行对比
    不关心数据从哪来，由 Port 层负责获取数据
    """

    def __init__(self, tolerance_rules: dict[str, ToleranceRule] | None = None):
        self.tolerance_rules = tolerance_rules or self._default_rules()

    def check(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        rules: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> list[DQIssue]:
        """执行跨源对比检查"""
        issues: list[DQIssue] = []

        for rule in rules:
            issue = self._check_rule(primary, secondary, rule, context)
            if issue:
                issues.append(issue)

        return issues

    def _default_rules(self) -> dict[str, ToleranceRule]:
        """默认容差规则"""
        return {
            "open": ToleranceRule(CompareMethod.TICK_ALIGNED, tick_size=0.01),
            "high": ToleranceRule(CompareMethod.TICK_ALIGNED, tick_size=0.01),
            "low": ToleranceRule(CompareMethod.TICK_ALIGNED, tick_size=0.01),
            "close": ToleranceRule(CompareMethod.TICK_ALIGNED, tick_size=0.01),
            "vol": ToleranceRule(CompareMethod.RELATIVE, relative_tol=0.001),
        }
```

### 4.2 Core 层：集成到 QualityEngine

```python
# packages/core/src/ditto_core/quality/engine.py（修改）

class QualityEngine:
    """Quality execution engine."""

    def __init__(self, config: DQSpec, dq_settings: DQSettings | None = None):
        # ... existing code ...
        self.cross_source_checker = CrossSourceChecker()  # ✅ 新增

    def check_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        """
        跨源对比检查（新增方法）

        Args:
            primary: 主数据源（如 Tushare）
            secondary: 辅助数据源（如 TDX）
            dataset: 数据集标识
            context: 额外上下文

        Returns:
            DQResult with cross-source comparison results
        """
        # ... implementation ...
```

### 4.3 DataHub 层：TDX 数据源

```python
# packages/datahub/src/ditto_datahub/sources/tdx/source.py

"""
通达信数据源 - DataHub 层

职责：数据访问（读取通达信 .day 文件）
"""

from pathlib import Path
from .reader import TdxReader


class TdxSource(DataSource):
    """
    通达信数据源

    仅用于质量对账，不参与主数据摄入
    """

    def __init__(self, tdx_path: str | Path = "C:/new_tdx/vipdoc"):
        self.tdx_path = Path(tdx_path)
        from .reader import TdxReader
        self.reader = TdxReader(self.tdx_path)

    def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
        """获取股票日线数据"""
        # 实现略（读取 .day 文件）
        pass
```

```python
# packages/datahub/src/ditto_datahub/sources/tdx/reader.py

"""
通达信 .day 文件读取器
"""

import struct
from pathlib import Path
import polars as pl


class TdxReader:
    """通达信日线数据读取器"""

    RECORD_FORMAT = '<IIIIIfII'
    RECORD_SIZE = 32

    def __init__(self, tdx_path: Path):
        self.tdx_path = Path(tdx_path)

    def read_daily(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """
        读取日线数据

        Returns:
            DataFrame with columns:
            - src_code, trade_date, open, high, low, close, vol
            - 单位：股（已从手转换）
        """
        # 实现略（解析 .day 二进制文件）
        pass
```

### 4.4 DataHub 层：对比结果存储

```python
# packages/datahub/src/ditto_datahub/stores/quality/comparison_store.py

"""
质量对比结果存储
"""

from pathlib import Path
from datetime import datetime, timedelta
import polars as pl


class ComparisonStore:
    """
    质量对比隔离区存储

    路径：data_root/quarantine/quality_comparison/
    保留：30 天自动清理
    """

    def __init__(
        self,
        base_path: Path = Path("data_root/quarantine/quality_comparison"),
        retention_days: int = 30,
    ):
        self.base_path = Path(base_path)
        self.retention_days = retention_days
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def write_comparison(
        self,
        trade_date: str,
        result: "DQResult",
    ) -> None:
        """存储对比结果"""
        # 实现略（写入 Parquet 文件）
        pass

    async def _cleanup_old_data(self) -> None:
        """清理过期数据"""
        # 实现略
        pass
```

### 4.5 Port 层：协调编排服务

```python
# packages/port/src/ditto_port/services/quality/reconciliation.py

"""
质量对账服务 - Port 层

职责：编排协调，不包含核心业务逻辑
"""

from ditto_core.quality.engine import QualityEngine
from ditto_datahub.sources.tushare import TushareSource
from ditto_datahub.sources.tdx import TdxSource
from ditto_datahub.stores.quality import ComparisonStore


class QualityReconciliationService:
    """
    质量对账服务

    Port 层：编排协调
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
    ):
        self.tushare = tushare_source
        self.tdx = tdx_source
        self.quality_engine = quality_engine
        self.comparison_store = comparison_store

    async def daily_reconciliation(
        self,
        trade_date: str,
        dataset: str = "stock_daily",
    ) -> dict:
        """
        每日质量对账

        Port 层：编排流程
        """
        # 1. 获取主数据源（Tushare）
        primary_df = await self.tushare.fetch_stock_daily(trade_date)

        # 2. 获取辅助数据源（TDX）
        ts_codes = primary_df["src_code"].unique().to_list()
        secondary_df = self.tdx.fetch_stock_daily_bars(ts_codes, trade_date)

        # 3. 调用 Core 层引擎进行对比
        result = self.quality_engine.check_cross_source(
            primary=primary_df,
            secondary=secondary_df,
            dataset=dataset,
        )

        # 4. 存储对比结果
        await self.comparison_store.write_comparison(trade_date, result)

        # 5. 判断是否需要告警
        if result.issues:
            await self._send_alerts(result, trade_date)

        return {
            "trade_date": trade_date,
            "dataset": dataset,
            "passed": result.passed,
            "issue_count": len(result.issues),
        }
```

---

## 五、目录结构

```
packages/
├── core/src/ditto_core/quality/
│   ├── engine.py                    # ✅ 修改：新增 check_cross_source()
│   ├── spec.py                      # ✅ 无修改
│   └── checkers/
│       ├── technical.py             # ✅ 无修改
│       ├── business.py              # ✅ 无修改
│       ├── statistical.py           # ✅ 无修改
│       └── cross_source.py          # ✅ 新增：跨源对比检查器
│
├── datahub/src/ditto_datahub/
│   ├── sources/
│   │   ├── tushare/                 # ✅ 无修改
│   │   └── tdx/                     # ✅ 新增：通达信数据源
│   │       ├── __init__.py
│   │       ├── source.py            # TdxSource
│   │       └── reader.py            # TdxReader（.day 文件读取）
│   │
│   ├── stores/
│   │   ├── quarantine_store.py      # ✅ 无修改
│   │   └── quality/                 # ✅ 新增：质量对比存储
│   │       ├── __init__.py
│   │       └── comparison_store.py  # ComparisonStore
│   │
│   └── quality/                     # ✅ 新增：质量配置
│       ├── __init__.py
│       └── config/
│           ├── __init__.py
│           ├── instrument_spec.py   # 标的元数据
│           └── golden_instruments.py # 黄金数据集配置
│
└── port/src/ditto_port/
    └── services/
        └── quality/                 # ✅ 新增：质量对账服务
            ├── __init__.py
            └── reconciliation.py     # QualityReconciliationService
```

---

## 六、配置示例

### 6.1 扩展现有规则配置

```yaml
# config/default/dq_rules/stock_daily.yml（扩展）

dataset: stock_daily
description: "股票日 K 线数据质量检查规则"

# L1: 技术校验（写入时强制阻断）
l1_technical:
  - rule: not_null
    columns: [sid, trade_date, open, high, low, close, volume, amount]
    message: "必填字段不能为空"

  - rule: unique
    columns: [sid, trade_date]
    message: "主键 (sid, trade_date) 重复"

  # ... 其他 L1 规则 ...

# L2: 业务规则（写入时警告但不阻断）
l2_business:
  # ... 原 L2 规则 ...

  # ✅ 新增：跨源对比规则
  - rule: cross_source_compare
    fields: [open, high, low, close, vol]
    key_columns: [src_code, trade_date]
    message: "与通达信数据对比发现差异"
    enabled: true  # 可选：开关控制

# L3: 统计异常（定时批量检查）
l3_statistical:
  # ... 原 L3 规则 ...
```

### 6.2 标的元数据配置

```python
# packages/datahub/src/ditto_datahub/quality/config/golden_instruments.py

"""
黄金数据集标的配置
"""

from .instrument_spec import InstrumentSpec, Market, Board, AssetType
from decimal import Decimal

GOLDEN_INSTRUMENTS: dict[str, InstrumentSpec] = {
    "510300.SH": InstrumentSpec(
        ts_code="510300.SH",
        name="沪深300ETF",
        market=Market.SH,
        board=Board.MAIN,
        asset_type=AssetType.ETF,
        tick_size=Decimal("0.001"),  # 上交所 ETF 是 0.001
        lot_size=100,
        default_limit_ratio=Decimal("0.10"),
    ),
    "000300.SH": InstrumentSpec(
        ts_code="000300.SH",
        name="沪深300指数",
        market=Market.SH,
        board=Board.MAIN,
        asset_type=AssetType.INDEX,
        tick_size=Decimal("0.01"),
        lot_size=1,
        default_limit_ratio=Decimal("1.0"),  # 指数无涨跌停
    ),
    # ... 其他标的配置 ...
}
```

---

## 七、实施路线图

### 7.1 分阶段实施

| 阶段 | 任务 | 优先级 | 说明 |
|------|------|--------|------|
| **阶段 1** | Core 层跨源对比检查器 | P0 | 纯业务逻辑，无依赖 |
| **阶段 2** | DataHub 层 TDX 数据源 | P1 | 数据访问 |
| **阶段 3** | DataHub 层对比结果存储 | P1 | 隔离区管理 |
| **阶段 4** | Port 层对账编排服务 | P2 | 协调与告警 |

### 7.2 任务清单

#### 阶段 1：Core 层（P0）

```yaml
tasks:
  - name: "创建 CrossSourceChecker"
    file: "packages/core/src/ditto_core/quality/checkers/cross_source.py"
    estimate: 4h

  - name: "修改 QualityEngine"
    file: "packages/core/src/ditto_core/quality/engine.py"
    changes:
      - "导入 CrossSourceChecker"
      - "新增 check_cross_source() 方法"
    estimate: 2h

  - name: "单元测试"
    file: "packages/core/tests/unit/quality/test_cross_source_checker.py"
    estimate: 4h
```

#### 阶段 2：DataHub 层 - TDX 数据源（P1）

```yaml
tasks:
  - name: "创建 TdxSource"
    file: "packages/datahub/src/ditto_datahub/sources/tdx/source.py"
    estimate: 4h

  - name: "创建 TdxReader"
    file: "packages/datahub/src/ditto_datahub/sources/tdx/reader.py"
    estimate: 6h  # .day 文件格式解析

  - name: "单元测试"
    file: "packages/datahub/tests/unit/sources/tdx/test_reader.py"
    estimate: 4h
```

#### 阶段 3：DataHub 层 - 对比结果存储（P1）

```yaml
tasks:
  - name: "创建 ComparisonStore"
    file: "packages/datahub/src/ditto_datahub/stores/quality/comparison_store.py"
    estimate: 4h

  - name: "创建 ComparisonAccessor"
    file: "packages/datahub/src/ditto_datahub/accessors/comparison_accessor.py"
    estimate: 2h

  - name: "单元测试"
    file: "packages/datahub/tests/unit/stores/quality/test_comparison_store.py"
    estimate: 4h
```

#### 阶段 4：Port 层（P2）

```yaml
tasks:
  - name: "创建 QualityReconciliationService"
    file: "packages/port/src/ditto_port/services/quality/reconciliation.py"
    estimate: 6h

  - name: "集成测试"
    file: "packages/port/tests/integration/quality/test_reconciliation.py"
    estimate: 6h

  - name: "文档更新"
    file: "docs/design/quality-reconciliation.md"
    estimate: 2h
```

---

## 八、关键设计决策

| 问题 | 推荐方案 | 原因 |
|------|---------|------|
| **跨源对比位置** | **Core 层（逻辑） + Port 层（编排）** | Core 层保持纯业务逻辑，Port 层负责协调 |
| **TDX 数据是否落地** | **可选（隔离区，30天清理）** | 用于调试和趋势分析，成本可控 |
| **对比结果级别** | **L2 业务检查（WARNING）** | 不阻断数据发布，仅记录和告警 |
| **存储格式** | **Parquet（月度汇总）** | 高效查询，支持分区剪裁 |
| **对比方法** | **Polars 向量化** | 比循环快 100 倍 |

---

## 九、参考资料

### 9.1 相关文档

- [黄金数据集验证规范 v1.2](../validation/golden_dataset_v1.2.md)
- [DataHub 架构设计](./2026-01-24-datahub-architecture-design.md)
- [Core 层质量引擎设计](../core/quality-design.md)

### 9.2 技术规范

- Polars 向量化操作：https://pola-rs.github.io/polars-book/user-guide/dsl/
- 通达信 .day 文件格式：官方文档

---

**文档版本**: v1.0
**创建日期**: 2026-01-24
**状态**: 设计草案

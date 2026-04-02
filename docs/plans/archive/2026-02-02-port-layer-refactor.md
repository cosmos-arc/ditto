# Port 层重新实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标:** 重构 Port 层，实现完整的数据摄取流程编排，包括质量检查、隔离数据、报告生成

**架构:** Port 层负责应用编排（ingestion, quality, data_writer, data_service），DataHub 层只负责底层读写，Core 层提供计算引擎

**技术栈:** Python 3.12+, Polars, Pydantic, FastAPI, Prefect, Pyright Strict

---

## 概述

### 背景说明

1. **三域重构已完成**：Metadata、Market、Capital 三个域在 DataHub 层已实现
2. **架构错误需要修正**：之前在 DataHub 中实现的 IngestionCoordinator 位置错误
3. **正确架构**：
   - DataHub 只负责底层读写（source, store, query）
   - Port 层负责完整的业务流程编排（ingestion, quality, data_writer）
   - Core 层提供计算引擎（dq_engine, feature_engine, factor_engine）

### 模块职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| **ingestion** | 数据摄取流程编排（调用 source → quality → writer） | DataHub Source, quality, writer |
| **quality** | 质量检查、隔离、报告、对账 | Core DQEngine, DataHub QuarantineStore |
| **data_writer** | 统一的数据写入接口（路由到正确的 Store） | DataHub Stores |
| **data_service** | 跨域查询编排（聚合多个 Store 的数据） | DataHub Stores, QueryServices |

### 目录结构

```
apps/port/src/ditto_port/services/
├── ingestion/          # 摄取服务
│   ├── coordinator.py
│   ├── base_ingestion.py
│   ├── metadata_ingestion.py
│   ├── market_ingestion.py
│   └── capital_ingestion.py
│
├── quality/            # 质量服务（独立模块）
│   ├── service.py              # 写入时检查（技术类+业务类）
│   ├── batch_check_service.py  # 批量检查服务
│   └── reconciliation.py       # 质量对账
│
├── data_writer/        # 数据写入服务（独立模块）
│   └── service.py
│
└── data_service/       # 数据查询服务（独立模块）
    └── service.py
```

---

## 阶段一：完善 DataHub 读写能力（4.5 天）

### 任务 1：删除 DataHub 中的错误实现（0.5 天）

**目标:** 删除 DataHub 层中的 IngestionCoordinator，因为业务编排应该在 Port 层

**Files:**
- Delete: `packages/data/src/ditto_data/ingestion/coordinator.py`
- Delete: `packages/data/src/ditto_data/ingestion/__init__.py` (如果只导出 coordinator)
- Modify: `packages/data/src/ditto_data/__init__.py` (移除相关导出)
- Test: `packages/data/tests/unit/ingestion/test_coordinator_unit.py` (删除相关测试)

**Step 1: 确认当前实现**

检查 `packages/data/src/ditto_data/ingestion/` 目录下的文件

**Step 2: 删除 coordinator.py**

```bash
rm packages/data/src/ditto_data/ingestion/coordinator.py
```

**Step 3: 清理 __init__.py**

如果 `__init__.py` 只导出 coordinator，清空文件；如果有其他导出，只移除 coordinator 相关导出

**Step 4: 更新主 __init__.py**

从 `packages/data/src/ditto_data/__init__.py` 中移除 IngestionCoordinator 相关导出

**Step 5: 删除相关测试**

```bash
rm packages/data/tests/unit/ingestion/test_coordinator_unit.py
```

**Step 6: 运行测试验证**

```bash
pixi run -e dev pytest --unit
```

预期：所有测试通过（coordinator 相关测试已删除）

**Step 7: 提交**

```bash
git add packages/data/src/ditto_data/ingestion/
git add packages/data/src/ditto_data/__init__.py
git add packages/data/tests/unit/ingestion/test_coordinator_unit.py
git commit -m "refactor(datahub): remove IngestionCoordinator from DataHub layer

Business orchestration should be in Port layer, not DataHub layer.
DataHub should only provide raw read/write capabilities."
```

---

### 任务 2：验证 Source 层返回标准化数据（1 天）

**目标:** 确保所有 Source 方法返回符合 SourceSchema 的标准化数据

**Files:**
- Verify: `packages/data/src/ditto_data/sources/tushare/*.py`
- Verify: `packages/data/src/ditto_data/sources/akshare/*.py`
- Test: `packages/data/tests/integration/sources/test_*.py`

**Step 1: 检查 SourceSchema 定义**

查看 `packages/data/src/ditto_data/models/source_schemas.py` 中的 Schema 定义

**Step 2: 验证 Tushare Stock Source**

检查 `packages/data/src/ditto_data/sources/tushare/stock.py`:
- `fetch_daily_bars()` 返回数据符合 `STOCK_BARS_SOURCE_SCHEMA`
- `fetch_status()` 返回数据符合 `STOCK_STATUS_SOURCE_SCHEMA`

**Step 3: 编写集成测试验证**

```python
# packages/data/tests/integration/sources/test_tushare_stock_schema.py

import pytest
from ditto_data.sources.tushare import TushareStockSource
from ditto_data.models.source_schemas import STOCK_BARS_SOURCE_SCHEMA


@pytest.mark.integration
def test_stock_daily_bars_schema():
    """验证股票日线数据符合 SourceSchema"""
    source = TushareStockSource()
    df = source.fetch_daily_bars(
        src_codes=["600000.SH"],
        start_date="2024-01-01",
        end_date="2024-01-10",
    )

    # 验证 Schema
    STOCK_BARS_SOURCE_SCHEMA.validate(df)

    # 验证数据质量
    assert len(df) > 0
    assert "instrument_id" in df.columns
    assert "source_ticker" in df.columns
```

**Step 4: 运行集成测试**

```bash
pixi run -e dev pytest packages/data/tests/integration/sources/test_tushare_stock_schema.py -v
```

**Step 5: 对其他 Source 重复 Step 2-4**

- ETF Source
- Index Source
- Capital Source
- Metadata Source

**Step 6: 提交**

```bash
git add packages/data/tests/integration/sources/
git commit -m "test(datahub): add SourceSchema validation tests"
```

---

### 任务 3：验证 Store 层读写接口完整（1 天）

**目标:** 确保所有 Store 提供完整的读写接口

**Files:**
- Verify: `packages/data/src/ditto_data/domains/*/`
- Test: `packages/data/tests/unit/stores/test_*.py`

**Step 1: 检查 Store 接口规范**

每个 Store 应该提供：
- `write(df, on_duplicate) -> WriteResult`
- `get(...) -> pl.DataFrame`

**Step 2: 验证 InstrumentStore**

```python
# packages/data/tests/unit/stores/test_instrument_store.py

from ditto_data.domains.metadata.instrument import InstrumentStore
from ditto_data.models.common import OnDuplicate


def test_instrument_store_write():
    """测试 InstrumentStore 写入"""
    store = InstrumentStore()
    # ... 测试代码
```

**Step 3: 运行 Store 测试**

```bash
pixi run -e dev pytest packages/data/tests/unit/stores/ -v
```

**Step 4: 修复任何缺失的接口**

如果有 Store 缺少必要方法，补充实现

**Step 5: 提交**

```bash
git add packages/data/src/ditto_data/domains/
git add packages/data/tests/unit/stores/
git commit -m "refactor(datahub): verify and fix Store interfaces"
```

---

### 任务 4：实现 QueryService（可选，1 天）

**目标:** 为每个域实现基础查询编排服务（如果需要）

**Files:**
- Create: `packages/data/src/ditto_data/domains/metadata/metadata_query_service.py`
- Create: `packages/data/src/ditto_data/domains/market/market_query_service.py`
- Create: `packages/data/src/ditto_data/domains/capital/capital_query_service.py`
- Test: `packages/data/tests/unit/query_services/test_*.py`

**Step 1: 实现 MetadataQueryService**

```python
# packages/data/src/ditto_data/domains/metadata/metadata_query_service.py

from dataclasses import dataclass
from ditto_data.domains.metadata.instrument import InstrumentStore
from ditto_data.domains.metadata.calendar import TradingCalendarStore


@dataclass
class MetadataQueryService:
    """Metadata 域查询服务"""

    instrument_store: InstrumentStore
    calendar_store: TradingCalendarStore

    def get_active_instruments(
        self,
        as_of_date: str,
    ):
        """获取活跃标的列表"""
        # 实现
```

**Step 2: 实现 MarketQueryService**

```python
# packages/data/src/ditto_data/domains/market/market_query_service.py

from dataclasses import dataclass
from ditto_data.domains.market.stock.bars import StockBarsStore


@dataclass
class MarketQueryService:
    """Market 域查询服务"""

    stock_bars_store: StockBarsStore
    # ... 其他 Store

    def get_stock_bars_with_status(
        self,
        instrument_ids: list[str],
        start_date: str,
        end_date: str,
    ):
        """获取 K 线数据，包含状态"""
        # 实现
```

**Step 3: 实现 CapitalQueryService**

类似模式实现 Capital 域查询服务

**Step 4: 编写测试**

```python
# packages/data/tests/unit/query_services/test_metadata_query_service.py

def test_get_active_instruments():
    """测试获取活跃标的"""
    # 测试代码
```

**Step 5: 运行测试**

```bash
pixi run -e dev pytest packages/data/tests/unit/query_services/ -v
```

**Step 6: 提交**

```bash
git add packages/data/src/ditto_data/domains/
git add packages/data/tests/unit/query_services/
git commit -m "feat(datahub): implement QueryServices for all domains"
```

---

### 任务 5：确保测试覆盖率 ≥ 80%（1 天）

**目标:** 确保 DataHub 层测试覆盖率达到标准

**Files:**
- All: `packages/data/src/ditto_data/`
- Test: All test files

**Step 1: 运行测试覆盖率检查**

```bash
pixi run -e dev pytest --cov=packages/data/src/ditto_data --cov-report=term-missing
```

**Step 2: 分析覆盖率报告**

找出覆盖率 < 80% 的文件

**Step 3: 补充测试**

为低覆盖率文件补充测试用例

**Step 4: 重新运行检查**

```bash
pixi run -e dev pytest --cov=packages/data/src/ditto_data --cov-report=term-missing
```

**Step 5: 提交**

```bash
git add packages/data/tests/
git commit -m "test(datahub): improve test coverage to ≥80%"
```

---

## 阶段二：Port 层重新实现（12 天）

### Week 1：核心模块实现

#### 任务 6：定义模型（1 天）

**目标:** 定义 IngestionResult, QualityReport 等核心数据模型

**Files:**
- Create: `apps/port/src/ditto_port/services/models/ingestion_result.py`
- Create: `apps/port/src/ditto_port/services/models/quality_report.py`
- Create: `apps/port/src/ditto_port/services/models/__init__.py`
- Test: `tests/port/services/models/test_*.py`

**Step 1: 编写 IngestionResult 测试**

```python
# tests/port/services/models/test_ingestion_result.py

import pytest
from ditto_port.services.models import IngestionResult, IngestionStatus


def test_ingestion_result_success():
    """测试成功的摄取结果"""
    result = IngestionResult(
        status=IngestionStatus.SUCCESS,
        dataset="stock_daily",
        records_written=1000,
        quality_issues=[],
    )

    assert result.status == IngestionStatus.SUCCESS
    assert result.records_written == 1000
    assert result.is_success()


def test_ingestion_result_failure():
    """测试失败的摄取结果"""
    result = IngestionResult(
        status=IngestionStatus.FAILED,
        dataset="stock_daily",
        error_message="DQ check failed",
        records_written=0,
    )

    assert result.status == IngestionStatus.FAILED
    assert not result.is_success()
    assert "DQ check failed" in result.error_message
```

**Step 2: 运行测试（预期失败）**

```bash
pixi run -e dev pytest tests/port/services/models/test_ingestion_result.py -v
```

**Step 3: 实现 IngestionResult**

```python
# apps/port/src/ditto_port/services/models/ingestion_result.py

from dataclasses import dataclass, field
from enum import Enum


class IngestionStatus(str, Enum):
    """摄取状态"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass(frozen=True)
class QualityIssue:
    """质量问题"""
    severity: str  # "error" | "warning"
    category: str  # "technical" | "business" | "statistical"
    message: str
    row_count: int = 0


@dataclass(frozen=True)
class IngestionResult:
    """摄取结果"""
    status: IngestionStatus
    dataset: str
    records_written: int = 0
    records_skipped: int = 0
    quality_issues: list[QualityIssue] = field(default_factory=list)
    error_message: str = ""
    duration_seconds: float = 0.0

    def is_success(self) -> bool:
        """是否成功"""
        return self.status == IngestionStatus.SUCCESS

    def has_quality_issues(self) -> bool:
        """是否有质量问题"""
        return len(self.quality_issues) > 0
```

**Step 4: 运行测试（预期通过）**

```bash
pixi run -e dev pytest tests/port/services/models/test_ingestion_result.py -v
```

**Step 5: 类似方式实现 QualityReport**

**Step 6: 提交**

```bash
git add apps/port/src/ditto_port/services/models/
git add tests/port/services/models/
git commit -m "feat(port): define IngestionResult and QualityReport models"
```

---

#### 任务 7：实现 data_writer 服务（1 天）

**目标:** 实现统一的数据写入接口

**Files:**
- Create: `apps/port/src/ditto_port/services/data_writer/service.py`
- Create: `apps/port/src/ditto_port/services/data_writer/__init__.py`
- Test: `tests/port/services/data_writer/test_service.py`

**Step 1: 编写测试**

```python
# tests/port/services/data_writer/test_service.py

import pytest
from ditto_data import DataHub
from ditto_port.services.data_writer import DataWriterService
from ditto_port.services.models.common import OnDuplicate
import polars as pl


@pytest.mark.integration
def test_write_stock_bars():
    """测试写入股票 K 线数据"""
    datahub = DataHub()
    writer = DataWriterService(datahub=datahub)

    df = pl.DataFrame({
        "instrument_id": ["600000.SSE"],
        "trade_date": [date(2024, 1, 1)],
        "open": [10.0],
        "high": [11.0],
        "low": [9.5],
        "close": [10.5],
        "volume": [1000000],
    })

    result = writer.write(
        df=df,
        domain="market",
        dataset="stock_bars",
        on_duplicate=OnDuplicate.KEEP_FIRST,
    )

    assert result.rows_inserted == 1
```

**Step 2: 运行测试（预期失败）**

```bash
pixi run -e dev pytest tests/port/services/data_writer/test_service.py -v
```

**Step 3: 实现 DataWriterService**

```python
# apps/port/src/ditto_port/services/data_writer/service.py

from dataclasses import dataclass
from pathlib import Path

from ditto_data import DataHub
from ditto_data.models.common import OnDuplicate, WriteResult
from ditto_port.services.models.common import Domain


@dataclass
class DataWriterService:
    """数据写入服务（Port 层）

    职责：
    - 统一的写入接口
    - 根据 Domain 和 dataset 路由到正确的 Store
    """

    datahub: DataHub

    def write(
        self,
        df: pl.DataFrame,
        domain: Domain,
        dataset: str,
        on_duplicate: OnDuplicate = OnDuplicate.KEEP_FIRST,
    ) -> WriteResult:
        """写入数据

        Args:
            df: 数据
            domain: 域枚举
            dataset: 数据集名称
            on_duplicate: 重复数据处理策略

        Returns:
            WriteResult
        """
        # 根据 Domain 路由到对应的 Store
        if domain == Domain.METADATA:
            return self._write_metadata(df, dataset, on_duplicate)
        elif domain == Domain.MARKET:
            return self._write_market(df, dataset, on_duplicate)
        elif domain == Domain.CAPITAL:
            return self._write_capital(df, dataset, on_duplicate)
        else:
            raise ValueError(f"Unknown domain: {domain}")

    def _write_metadata(
        self,
        df: pl.DataFrame,
        dataset: str,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """写入 Metadata 域数据"""
        if dataset == "instrument":
            return self.datahub.domains.metadata.instrument.write(
                df=df,
                on_duplicate=on_duplicate,
            )
        # ... 其他 dataset
        raise ValueError(f"Unknown dataset: {dataset}")

    def _write_market(
        self,
        df: pl.DataFrame,
        dataset: str,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """写入 Market 域数据"""
        if dataset == "stock_bars":
            return self.datahub.domains.market.stock.bars.write(
                df=df,
                on_duplicate=on_duplicate,
            )
        # ... 其他 dataset
        raise ValueError(f"Unknown dataset: {dataset}")

    def _write_capital(
        self,
        df: pl.DataFrame,
        dataset: str,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        """写入 Capital 域数据"""
        # 类似实现
        raise ValueError(f"Unknown dataset: {dataset}")
```

**Step 4: 运行测试（预期通过）**

**Step 5: 提交**

```bash
git add apps/port/src/ditto_port/services/data_writer/
git add tests/port/services/data_writer/
git commit -m "feat(port): implement DataWriterService"
```

---

#### 任务 8：实现 quality.service（2 天）

**目标:** 实现写入时质量检查服务（技术类 + 业务类）

**Files:**
- Create: `apps/port/src/ditto_port/services/quality/service.py`
- Create: `apps/port/src/ditto_port/services/quality/__init__.py`
- Test: `tests/port/services/quality/test_service.py`

**Step 1: 编写测试**

```python
# tests/port/services/quality/test_service.py

import pytest
from ditto_core.quality import QualityEngine, DQSpec
from ditto_port.services.quality import QualityService
import polars as pl


def test_check_stock_bars_l1():
    """测试股票 K 线 L1 检查"""
    dq_engine = QualityEngine(config=DQSpec())
    service = QualityService(dq_engine=dq_engine)

    # 正常数据
    good_df = pl.DataFrame({
        "instrument_id": ["600000.SSE"],
        "trade_date": [date(2024, 1, 1)],
        "open": [10.0],
        "close": [10.5],
    })

    result = service.check(df=good_df, dataset="stock_daily", levels=["l1"])
    assert result.passed

    # 缺失数据
    bad_df = pl.DataFrame({
        "instrument_id": ["600000.SSE"],
        # 缺少 trade_date
        "open": [10.0],
    })

    result = service.check(df=bad_df, dataset="stock_daily", levels=["l1"])
    assert not result.passed
    assert len(result.l1_issues) > 0


def test_check_stock_bars_l2():
    """测试股票 K 线 L2 检查"""
    # 类似实现
```

**Step 2: 运行测试（预期失败）**

**Step 3: 实现 QualityService**

```python
# apps/port/src/ditto_port/services/quality/service.py

from dataclasses import dataclass
from typing import Any

import polars as pl

from ditto_core.quality import QualityEngine, DQResult, DQIssue
from ditto_port.services.models.quality_report import QualityResult


@dataclass
class QualityService:
    """质量检查服务（Port 层）

    职责：
    - 集成 Core 层的 DQEngine
    - 处理质量检查结果
    - 管理隔离区数据
    """

    dq_engine: QualityEngine

    def check(
        self,
        df: pl.DataFrame,
        dataset: str,
        levels: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> QualityResult:
        """执行质量检查

        Args:
            df: 待检查数据
            dataset: 数据集标识
            levels: 检查级别 ["l1", "l2"]
            context: 额外上下文

        Returns:
            QualityResult
        """
        if levels is None:
            levels = ["l1", "l2"]

        # 调用 Core 层 DQEngine
        dq_result: DQResult = self.dq_engine.check(
            df=df,
            dataset=dataset,
            levels=levels,
            context=context,
        )

        # 转换为 Port 层的 QualityResult
        return self._convert_result(dq_result)

    def _convert_result(self, dq_result: DQResult) -> QualityResult:
        """转换 DQResult 为 QualityResult"""
        l1_issues = [i for i in dq_result.issues if i.severity == "error"]
        l2_issues = [i for i in dq_result.issues if i.severity == "warning"]

        return QualityResult(
            passed=dq_result.passed,
            l1_issues=l1_issues,
            l2_issues=l2_issues,
            total_issues=len(dq_result.issues),
        )
```

**Step 4: 运行测试（预期通过）**

**Step 5: 补充更多测试用例**

**Step 6: 提交**

```bash
git add apps/port/src/ditto_port/services/quality/
git add tests/port/services/quality/
git commit -m "feat(port): implement QualityService"
```

---

#### 任务 9：实现 quality.batch_check_service（1 天）

**目标:** 实现批量检查服务（统计类检查）

**Files:**
- Create: `apps/port/src/ditto_port/services/quality/batch_check_service.py`
- Test: `tests/port/services/quality/test_batch_check_service.py`

**Step 1: 编写测试**

```python
# tests/port/services/quality/test_batch_check_service.py

import pytest
from ditto_port.services.quality import BatchCheckService
from datetime import date


@pytest.mark.integration
def test_batch_check_stock_bars():
    """测试批量检查股票 K 线"""
    service = BatchCheckService()

    result = service.run_batch_check(
        dataset="stock_daily",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        check_types=["zscore", "completeness"],
    )

    assert result.total_records > 0
    assert "zscore" in result.check_results
```

**Step 2: 运行测试（预期失败）**

**Step 3: 实现 BatchCheckService**

```python
# apps/port/src/ditto_port/services/quality/batch_check_service.py

from dataclasses import dataclass
from datetime import date

from ditto_data import DataHub
from ditto_port.services.models.quality_report import BatchCheckResult


@dataclass
class BatchCheckService:
    """批量检查服务（Port 层）

    职责：
    - 定时批量执行统计类检查
    - 生成批量检查报告
    """

    datahub: DataHub

    def run_batch_check(
        self,
        dataset: str,
        start_date: date,
        end_date: date,
        check_types: list[str] | None = None,
    ) -> BatchCheckResult:
        """运行批量检查

        Args:
            dataset: 数据集标识
            start_date: 开始日期
            end_date: 结束日期
            check_types: 检查类型列表

        Returns:
            BatchCheckResult
        """
        # 实现批量检查逻辑
        # 1. 读取指定日期范围的数据
        # 2. 执行统计类检查（Z-score, 完整性等）
        # 3. 生成报告
```

**Step 4: 运行测试（预期通过）**

**Step 5: 提交**

```bash
git add apps/port/src/ditto_port/services/quality/batch_check_service.py
git add tests/port/services/quality/test_batch_check_service.py
git commit -m "feat(port): implement BatchCheckService"
```

---

#### 任务 10：实现 quality.reconciliation（2 天）

**目标:** 实现质量对账服务

**Files:**
- Create: `apps/port/src/ditto_port/services/quality/reconciliation.py`
- Test: `tests/port/services/quality/test_reconciliation.py`

**Step 1: 编写测试**

```python
# tests/port/services/quality/test_reconciliation.py

import pytest
from ditto_port.services.quality import ReconciliationService


@pytest.mark.integration
def test_reconcile_sources():
    """测试跨源对账"""
    service = ReconciliationService()

    result = service.reconcile_sources(
        dataset="stock_daily",
        trade_date="2024-01-01",
        source_a="tushare",
        source_b="akshare",
    )

    assert result.total_records_a > 0
    assert result.differences > 0 or result.differences == 0
```

**Step 2: 运行测试（预期失败）**

**Step 3: 实现 ReconciliationService**

```python
# apps/port/src/ditto_port/services/quality/reconciliation.py

from dataclasses import dataclass
from datetime import date

from ditto_data import DataHub
from ditto_port.services.models.quality_report import ReconciliationResult


@dataclass
class ReconciliationService:
    """质量对账服务（Port 层）

    职责：
    - 跨源数据对账
    - 数据一致性检查
    - 生成对账报告
    """

    datahub: DataHub

    def reconcile_sources(
        self,
        dataset: str,
        trade_date: date,
        source_a: str = "tushare",
        source_b: str = "akshare",
    ) -> ReconciliationResult:
        """跨源对账

        Args:
            dataset: 数据集标识
            trade_date: 交易日期
            source_a: 数据源 A
            source_b: 数据源 B

        Returns:
            ReconciliationResult
        """
        # 实现跨源对账逻辑
        # 1. 从两个数据源获取数据
        # 2. 比较差异
        # 3. 生成报告
```

**Step 4: 运行测试（预期通过）**

**Step 5: 补充更多对账测试**

**Step 6: 提交**

```bash
git add apps/port/src/ditto_port/services/quality/reconciliation.py
git add tests/port/services/quality/test_reconciliation.py
git commit -m "feat(port): implement ReconciliationService"
```

---

### Week 2：摄取服务实现

#### 任务 11：实现 base_ingestion（1 天）

**目标:** 实现基础摄取服务抽象类

**Files:**
- Create: `apps/port/src/ditto_port/services/ingestion/base_ingestion.py`
- Test: `tests/port/services/ingestion/test_base_ingestion.py`

**Step 1: 编写测试**

```python
# tests/port/services/ingestion/test_base_ingestion.py

import pytest
from ditto_port.services.ingestion import BaseIngestionService
from ditto_port.services.models import IngestionResult


def test_base_ingestion_template_method():
    """测试基础摄取服务模板方法"""
    # 测试模板方法流程
```

**Step 2: 运行测试（预期失败）**

**Step 3: 实现 BaseIngestionService**

```python
# apps/port/src/ditto_port/services/ingestion/base_ingestion.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from ditto_data import DataHub
from ditto_port.services.data_writer import DataWriterService
from ditto_port.services.quality import QualityService
from ditto_port.services.models.ingestion_result import IngestionResult


@dataclass
class BaseIngestionService(ABC):
    """基础摄取服务抽象

    职责：
    - 定义统一的摄取流程模板
    - 子类实现具体的数据类型摄取
    """

    datahub: DataHub
    quality: QualityService
    writer: DataWriterService

    @abstractmethod
    async def ingest(
        self,
        data_type: str,
        trade_date: date,
        source: str = "tushare",
    ) -> IngestionResult:
        """执行摄取流程（子类实现）"""

    async def _ingest_template(
        self,
        data_type: str,
        trade_date: date,
        source: str,
        domain: str,
    ) -> IngestionResult:
        """摄取流程模板（Template Method 模式）

        流程：
        1. 调用 DataHub Source 获取原始数据
        2. 调用 QualityService 进行质量检查（L1+L2）
        3. L1 失败则阻断写入
        4. L2 失败则记录警告并继续
        5. 记录质量报告
        6. 隔离异常数据
        7. 写入 DataHub Store
        8. 返回摄取结果
        """
        # 实现通用流程
```

**Step 4: 运行测试（预期通过）**

**Step 5: 提交**

```bash
git add apps/port/src/ditto_port/services/ingestion/base_ingestion.py
git add tests/port/services/ingestion/test_base_ingestion.py
git commit -m "feat(port): implement BaseIngestionService"
```

---

#### 任务 12：实现 metadata_ingestion（1 天）

**目标:** 实现 Metadata 域摄取服务

**Files:**
- Create: `apps/port/src/ditto_port/services/ingestion/metadata_ingestion.py`
- Test: `tests/port/services/ingestion/test_metadata_ingestion.py`

**Step 1: 编写测试**

```python
# tests/port/services/ingestion/test_metadata_ingestion.py

import pytest
from ditto_port.services.ingestion import MetadataIngestionService


@pytest.mark.integration
async def test_ingest_instruments():
    """测试摄入标的数据"""
    service = MetadataIngestionService(...)

    result = await service.ingest_instruments(
        trade_date="2024-01-01",
        source="tushare",
    )

    assert result.is_success()
    assert result.records_written > 0
```

**Step 2: 运行测试（预期失败）**

**Step 3: 实现 MetadataIngestionService**

```python
# apps/port/src/ditto_port/services/ingestion/metadata_ingestion.py

from dataclasses import dataclass
from datetime import date

from ditto_data import DataHub
from ditto_port.services.data_writer import DataWriterService
from ditto_port.services.quality import QualityService
from ditto_port.services.ingestion.base_ingestion import BaseIngestionService
from ditto_port.services.models.ingestion_result import IngestionResult


@dataclass
class MetadataIngestionService(BaseIngestionService):
    """Metadata 域摄取服务

    职责：
    - 摄入标的数据
    - 摄入行业数据
    - 摄入日历数据
    """

    async def ingest_instruments(
        self,
        trade_date: date,
        source: str = "tushare",
    ) -> IngestionResult:
        """摄入标的数据

        完整流程：
        1. 调用 DataHub Source 获取数据
        2. 调用 QualityService 检查
        3. 写入 DataHub Store
        4. 返回结果
        """
        # 1. 获取数据
        raw_data = await self._fetch_instruments(source)

        # 2. 质量检查
        quality_result = self.quality.check(
            df=raw_data,
            dataset="instrument",
            levels=["l1", "l2"],
        )

        if not quality_result.passed:
            return IngestionResult(
                status=IngestionStatus.FAILED,
                dataset="instrument",
                error_message="L1 quality check failed",
            )

        # 3. 写入数据
        write_result = self.writer.write(
            df=raw_data,
            domain=Domain.METADATA,
            dataset="instrument",
        )

        return IngestionResult(
            status=IngestionStatus.SUCCESS,
            dataset="instrument",
            records_written=write_result.rows_inserted,
        )
```

**Step 4: 运行测试（预期通过）**

**Step 5: 提交**

```bash
git add apps/port/src/ditto_port/services/ingestion/metadata_ingestion.py
git add tests/port/services/ingestion/test_metadata_ingestion.py
git commit -m "feat(port): implement MetadataIngestionService"
```

---

#### 任务 13：实现 market_ingestion（2 天）

**目标:** 实现 Market 域摄取服务

**Files:**
- Create: `apps/port/src/ditto_port/services/ingestion/market_ingestion.py`
- Test: `tests/port/services/ingestion/test_market_ingestion.py`

**Step 1-5:** 类似任务 12，实现 MarketIngestionService

包括：
- `ingest_stock_daily()`
- `ingest_etf_daily()`
- `ingest_index_daily()`
- `ingest_adj_factor()`

**提交:**

```bash
git add apps/port/src/ditto_port/services/ingestion/market_ingestion.py
git add tests/port/services/ingestion/test_market_ingestion.py
git commit -m "feat(port): implement MarketIngestionService"
```

---

#### 任务 14：实现 capital_ingestion（1 天）

**目标:** 实现 Capital 域摄取服务

**Files:**
- Create: `apps/port/src/ditto_port/services/ingestion/capital_ingestion.py`
- Test: `tests/port/services/ingestion/test_capital_ingestion.py`

**Step 1-5:** 类似任务 12，实现 CapitalIngestionService

**提交:**

```bash
git add apps/port/src/ditto_port/services/ingestion/capital_ingestion.py
git add tests/port/services/ingestion/test_capital_ingestion.py
git commit -m "feat(port): implement CapitalIngestionService"
```

---

#### 任务 15：实现 coordinator（0.5 天）

**目标:** 实现路由协调器

**Files:**
- Create: `apps/port/src/ditto_port/services/ingestion/coordinator.py`
- Test: `tests/port/services/ingestion/test_coordinator.py`

**Step 1: 编写测试**

```python
# tests/port/services/ingestion/test_coordinator.py

import pytest
from ditto_port.services.ingestion import IngestionCoordinator


@pytest.mark.integration
async def test_coordinator_route():
    """测试路由协调器"""
    coordinator = IngestionCoordinator(...)

    result = await coordinator.ingest(
        domain=Domain.MARKET,
        data_type="stock_daily",
        trade_date="2024-01-01",
    )

    assert result.is_success()
```

**Step 2: 运行测试（预期失败）**

**Step 3: 实现 IngestionCoordinator**

```python
# apps/port/src/ditto_port/services/ingestion/coordinator.py

from dataclasses import dataclass
from datetime import date

from ditto_port.services.ingestion.metadata_ingestion import MetadataIngestionService
from ditto_port.services.ingestion.market_ingestion import MarketIngestionService
from ditto_port.services.ingestion.capital_ingestion import CapitalIngestionService
from ditto_port.services.models.common import Domain
from ditto_port.services.models.ingestion_result import IngestionResult


@dataclass
class IngestionCoordinator:
    """摄取路由协调器（Port 层）

    职责：
    - 根据 Domain 枚举路由到对应的 IngestionService
    - 统一的摄取入口
    """

    metadata: MetadataIngestionService
    market: MarketIngestionService
    capital: CapitalIngestionService

    async def ingest(
        self,
        domain: Domain,
        data_type: str,
        trade_date: date,
        source: str = "tushare",
    ) -> IngestionResult:
        """路由到对应的摄取服务

        Args:
            domain: 域枚举
            data_type: 数据类型
            trade_date: 交易日期
            source: 数据源

        Returns:
            IngestionResult
        """
        if domain == Domain.METADATA:
            return await self.metadata.ingest(data_type, trade_date, source)
        elif domain == Domain.MARKET:
            return await self.market.ingest(data_type, trade_date, source)
        elif domain == Domain.CAPITAL:
            return await self.capital.ingest(data_type, trade_date, source)
        else:
            raise ValueError(f"Unknown domain: {domain}")
```

**Step 4: 运行测试（预期通过）**

**Step 5: 提交**

```bash
git add apps/port/src/ditto_port/services/ingestion/coordinator.py
git add tests/port/services/ingestion/test_coordinator.py
git commit -m "feat(port): implement IngestionCoordinator"
```

---

#### 任务 16：实现 data_service（1 天，可选）

**目标:** 实现跨域查询编排服务

**Files:**
- Create: `apps/port/src/ditto_port/services/data_service/service.py`
- Test: `tests/port/services/data_service/test_service.py`

**Step 1-5:** 类似前面的任务，实现 DataService

**提交:**

```bash
git add apps/port/src/ditto_port/services/data_service/
git add tests/port/services/data_service/
git commit -m "feat(port): implement DataService"
```

---

#### 任务 17：测试与文档（1.5 天）

**目标:** 完善测试覆盖和文档

**Step 1: 运行完整测试套件**

```bash
pixi run -e dev pytest
```

**Step 2: 检查测试覆盖率**

```bash
pixi run -e dev pytest --cov=apps/port/src/ditto_port/services --cov-report=term-missing
```

**Step 3: 补充缺失的测试**

确保覆盖率 ≥ 80%

**Step 4: 更新 README**

```markdown
# apps/port/README.md

## Port 层架构

Port 层负责应用编排，包括以下服务：

### 模块清单

| 模块 | 职责 |
|------|------|
| ingestion | 数据摄取流程编排 |
| quality | 质量检查、对账、报告 |
| data_writer | 统一数据写入接口 |
| data_service | 跨域查询编排 |

### 使用示例

\`\`\`python
from ditto_port.services.ingestion import IngestionCoordinator

# 执行摄取
coordinator = IngestionCoordinator(...)
result = await coordinator.ingest(
    domain=Domain.MARKET,
    data_type="stock_daily",
    trade_date="2024-01-01",
)
\`\`\`
```

**Step 5: 运行类型检查**

```bash
pixi run -e dev type
```

**Step 6: 运行代码质量检查**

```bash
pixi run -e dev lint
pixi run -e dev fmt
```

**Step 7: 最终提交**

```bash
git add apps/port/README.md
git add docs/
git commit -m "docs(port): update documentation"
```

---

## 验收标准

### 代码质量

- [ ] basedpyright 0 errors
- [ ] ruff checks passed
- [ ] 测试覆盖率 ≥ 80%

### 功能完整

- [ ] 所有设计的模块实现
- [ ] 摄取流程完整（source → quality → writer）
- [ ] 质量检查集成（L1+L2 阻断/警告，批量检查）
- [ ] 质量对账功能正常

### 架构清晰

- [ ] DataHub 层纯净（只有读写）
- [ ] Port 层业务编排清晰
- [ ] 模块职责明确

---

## 相关文档

- [三域重构实施计划](./2026-01-29-datahub-three-domain-refactor-implementation.md)
- [数据质量设计](../design/09_data_quality_design.md)
- [Port 层架构设计](../design/11_port_architecture.md)

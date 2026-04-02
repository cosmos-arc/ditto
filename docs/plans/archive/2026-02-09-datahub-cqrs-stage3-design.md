# 阶段 3 CQRS 拆分设计：Fundamental/Capital 域

> **创建日期**: 2026-02-09
> **状态**: 设计完成，待实施
> **相关计划**: [2026-02-09-datahub-cqrs-refactor.md](./2026-02-09-datahub-cqrs-refactor.md)

---

## 概述

将 Fundamental 和 Capital 域的组合 Store 完全拆分为独立的 Reader/Writer 组件，实现 CQRS 模式。

**拆分策略**: 完全拆分，无例外
**执行顺序**: Fundamental → Capital
**测试策略**: 完整测试覆盖

---

## 拆分目标

### Fundamental 域（7 组 Reader/Writer）

| 原 Store | 拆分为 Reader/Writer 对 |
|---------|----------------------|
| `FundamentalStore.balance_sheet` | `balance_sheet_reader.py` + `balance_sheet_writer.py` |
| `FundamentalStore.income_statement` | `income_statement_reader.py` + `income_statement_writer.py` |
| `FundamentalStore.cash_flow` | `cash_flow_reader.py` + `cash_flow_writer.py` |
| `FundamentalStore.dividend` | `dividend_reader.py` + `dividend_writer.py` |
| `FundamentalStore.corporate_actions` | `corporate_actions_reader.py` + `corporate_actions_writer.py` |
| `ForecastStore` | `forecast_reader.py` + `forecast_writer.py` |
| `ExpressStore` | `express_reader.py` + `express_writer.py` |

### Capital 域（5 组 Reader/Writer）

| 原 Store | 拆分为 Reader/Writer 对 |
|---------|----------------------|
| `CapitalStore.valuation_metrics` | `valuation_reader.py` + `valuation_writer.py` |
| `CapitalStore.futures` | `futures_reader.py` + `futures_writer.py` |
| `CapitalStore.index_composition` | `index_composition_reader.py` + `index_composition_writer.py` |
| `MarginTradingStore` | `margin_reader.py` + `margin_writer.py` |
| `PledgeRatioStore` | `pledge_reader.py` + `pledge_writer.py` |

**总计**: 12 组 Reader/Writer

---

## 目录结构

### Fundamental 域

```
stores/
├── fundamental/
│   ├── __init__.py
│   ├── financial/
│   │   ├── __init__.py
│   │   ├── balance_sheet_reader.py      # 新建
│   │   ├── balance_sheet_writer.py      # 新建
│   │   ├── income_statement_reader.py   # 新建
│   │   ├── income_statement_writer.py   # 新建
│   │   ├── cash_flow_reader.py          # 新建
│   │   └── cash_flow_writer.py          # 新建
│   ├── corporate/
│   │   ├── __init__.py
│   │   ├── dividend_reader.py           # 新建
│   │   ├── dividend_writer.py           # 新建
│   │   ├── corporate_actions_reader.py  # 新建
│   │   └── corporate_actions_writer.py  # 新建
│   ├── forecast/
│   │   ├── __init__.py
│   │   ├── forecast_reader.py           # 新建
│   │   ├── forecast_writer.py           # 新建
│   │   ├── express_reader.py            # 新建
│   │   ├── express_writer.py            # 新建
│   └── fundamental_store.py             # 删除
```

### Capital 域

```
stores/
├── capital/
│   ├── __init__.py
│   ├── valuation/
│   │   ├── __init__.py
│   │   ├── valuation_reader.py          # 新建
│   │   └── valuation_writer.py          # 新建
│   ├── futures/
│   │   ├── __init__.py
│   │   ├── futures_reader.py            # 新建
│   │   └── futures_writer.py            # 新建
│   ├── index/
│   │   ├── __init__.py
│   │   ├── index_composition_reader.py  # 新建
│   │   └── index_composition_writer.py  # 新建
│   ├── margin/
│   │   ├── __init__.py
│   │   ├── margin_reader.py             # 新建
│   │   ├── margin_writer.py             # 新建
│   │   └── margin_trading_store.py      # 删除
│   ├── pledge/
│   │   ├── __init__.py
│   │   ├── pledge_reader.py             # 新建
│   │   ├── pledge_writer.py             # 新建
│   │   └── pledge_ratio_store.py        # 删除
│   └── capital_store.py                 # 删除
```

---

## 实现模板

### Reader 模板

```python
"""XXX reader for CQRS pattern."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_infra import traced
from ditto_data.stores.sqlite_client import SQLiteClient


class XXXReader:
    """XXX 数据读取器."""

    def __init__(self, client: SQLiteClient) -> None:
        """初始化 XXXReader."""
        self._client = client

    @traced("data.xxx_query")
    def get(self, instrument_id: str, as_of_date: date) -> pl.DataFrame:
        """查询数据（PIT 查询）."""
        rows = self._client.fetchall(
            "SELECT ... FROM xxx WHERE ...",
            [instrument_id, as_of_date, as_of_date],
        )
        return pl.DataFrame(rows) if rows else pl.DataFrame()
```

### Writer 模板

```python
"""XXX writer for CQRS pattern."""

from __future__ import annotations

import polars as pl
from ditto_infra import M, logger, traced
from ditto_data.stores.sqlite_client import SQLiteClient


class XXXWriter:
    """XXX 数据写入器."""

    def __init__(self, client: SQLiteClient) -> None:
        """初始化 XXXWriter."""
        self._client = client

    @traced("data.xxx_write")
    def write(self, df: pl.DataFrame) -> int:
        """写入数据."""
        logger.info("Starting xxx data write", record_count=len(df))

        try:
            records = df.to_dicts()
            self._client.executemany(
                "INSERT INTO xxx ...",
                [ ... for r in records ],
            )
            self._client.commit()

            logger.info("xxx data written successfully", record_count=len(records))
            M.data_records.add(len(records), {"dataset": "xxx", "status": "success"})
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error("xxx write failed", error=str(e))
            M.data_records.add(len(df), {"dataset": "xxx", "status": "failed"})
            raise
```

---

## Service 层更新

### FundamentalService

```python
def __init__(
    self,
    balance_sheet_reader: BalanceSheetReader,
    balance_sheet_writer: BalanceSheetWriter,
    income_statement_reader: IncomeStatementReader,
    income_statement_writer: IncomeStatementWriter,
    cash_flow_reader: CashFlowReader,
    cash_flow_writer: CashFlowWriter,
    dividend_reader: DividendReader,
    dividend_writer: DividendWriter,
    corporate_actions_reader: CorporateActionsReader,
    corporate_actions_writer: CorporateActionsWriter,
    forecast_reader: ForecastReader,
    forecast_writer: ForecastWriter,
    express_reader: ExpressReader,
    express_writer: ExpressWriter,
) -> None:
    # 初始化所有 Reader/Writer
```

### CapitalService

```python
def __init__(
    self,
    valuation_reader: ValuationReader,
    valuation_writer: ValuationWriter,
    futures_reader: FuturesReader,
    futures_writer: FuturesWriter,
    index_composition_reader: IndexCompositionReader,
    index_composition_writer: IndexCompositionWriter,
    margin_reader: MarginReader,
    margin_writer: MarginWriter,
    pledge_reader: PledgeReader,
    pledge_writer: PledgeWriter,
) -> None:
    # 初始化所有 Reader/Writer
```

---

## 执行计划

### 阶段 3.1：Fundamental 域拆分

| 步骤 | 任务 |
|------|------|
| 3.1.1 | 创建 financial 目录结构 |
| 3.1.2 | 实现 BalanceSheet Reader/Writer + 测试 |
| 3.1.3 | 实现 IncomeStatement Reader/Writer + 测试 |
| 3.1.4 | 实现 CashFlow Reader/Writer + 测试 |
| 3.1.5 | 创建 corporate 目录结构 |
| 3.1.6 | 实现 Dividend Reader/Writer + 测试 |
| 3.1.7 | 实现 CorporateActions Reader/Writer + 测试 |
| 3.1.8 | 拆分 ForecastStore → Reader/Writer + 测试 |
| 3.1.9 | 拆分 ExpressStore → Reader/Writer + 测试 |
| 3.1.10 | 更新 FundamentalService |
| 3.1.11 | 删除旧 Store 文件 |
| 3.1.12 | 更新 __init__.py 导出 |

### 阶段 3.2：Capital 域拆分

| 步骤 | 任务 |
|------|------|
| 3.2.1 | 创建 valuation/futures/index 目录 |
| 3.2.2 | 实现 Valuation Reader/Writer + 测试 |
| 3.2.3 | 实现 Futures Reader/Writer + 测试 |
| 3.2.4 | 实现 IndexComposition Reader/Writer + 测试 |
| 3.2.5 | 拆分 MarginTradingStore → Reader/Writer + 测试 |
| 3.2.6 | 拆分 PledgeRatioStore → Reader/Writer + 测试 |
| 3.2.7 | 更新 CapitalService |
| 3.2.8 | 删除旧 Store 文件 |
| 3.2.9 | 更新 __init__.py 导出 |

---

## 验收标准

```bash
# 完整测试
pixi run -e dev test

# 代码质量
pixi run -e dev check
pixi run -e dev type
pixi run -e dev lint

# 测试覆盖率 ≥ 80%
pixi run -e dev test --cov --cov-report=term-missing
```

---

## 设计原则

1. **Reader 职责**：只读操作，PIT 查询，支持缓存（如适用）
2. **Writer 职责**：写入操作，事务管理，缓存失效（如适用）
3. **共享 SQLiteClient**：Reader/Writer 都接收同一个 client 实例
4. **装饰器保留**：`@traced` 装饰器从原 Store 迁移到对应方法
5. **测试隔离**：每个 Reader/Writer 都有独立的测试文件

---

## 提交策略

- 每完成一个 Reader/Writer 对 → 独立提交
- 每完成一个域（Fundamental/Capital）→ PR 合并
- 最终统一更新 DI 容器（阶段 7）

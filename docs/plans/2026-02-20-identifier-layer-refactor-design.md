# 标识符层重构设计

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 重构摄入入口的标识符设计，用户使用 `ticker`/`standard_ticker`/`instrument_id` 而非 `source_ticker`，Coordinator 层统一转换。

**Architecture:** 在 MetadataService 中新增 `resolve_source_ticker()` 方法，REST API 路径改为显式数据源格式。

---

## 1. 标识符体系

### 层次定义

| 层级 | 名称 | 示例 | 说明 |
|------|------|------|------|
| 用户层 | `ticker` | "000001" | 裸代码，用户最常用 |
| 用户层 | `standard_ticker` | "000001.XSHE" | Ditto 标准格式（Ditto exchange 标准） |
| 用户层 | `instrument_id` | 1000001 | 内部 ID，最精确 |
| 转换后 | `source_ticker` | "000001.SZ" | 数据源特有格式（如 Tushare 的 SZ） |

### 转换规则

```
用户输入（三选一）         转换层              数据源
ticker ─────────────┐
standard_ticker ────┼──► MetadataService.resolve_source_ticker ──► source_ticker ──► Tushare/AKShare
instrument_id ──────┘
```

- **优先级**: instrument_id > standard_ticker > ticker
- **歧义处理**: 裸 ticker 可能匹配多个标的，抛出 `AmbiguousTickerError`

---

## 2. 核心数据结构

### 2.1 InstrumentIngestParams（重命名）

```python
# apps/port/src/ditto_port/services/ingestion/ticker_resolver.py
@dataclass(frozen=True)
class InstrumentIngestParams:
    """按标的摄取的参数."""

    # 标识符（三选一，优先级: instrument_id > standard_ticker > ticker）
    instrument_id: int | None = None
    standard_ticker: str | None = None  # Ditto 标准格式，如 "000001.XSHE"
    ticker: str | None = None           # 裸代码，如 "000001"

    # 时间范围
    start_date: str = ""  # YYYY-MM-DD
    end_date: str = ""    # YYYY-MM-DD
```

### 2.2 MetadataService 扩展

```python
# packages/datahub/src/ditto_datahub/services/metadata_service.py
class MetadataService:
    """元数据服务."""

    # ... 现有方法 ...

    def resolve_source_ticker(
        self,
        ticker: str | None = None,
        standard_ticker: str | None = None,
        instrument_id: int | None = None,
        source: str = "tushare",
    ) -> str:
        """
        将任意标识符解析为 source_ticker.

        优先级: instrument_id > standard_ticker > ticker

        Args:
            ticker: 裸代码（如 "000001"）
            standard_ticker: Ditto 标准格式（如 "000001.XSHE"）
            instrument_id: 内部 ID（如 1000001）
            source: 数据源名称（如 "tushare"）

        Returns:
            source_ticker 字符串

        Raises:
            ValueError: 未提供任何标识符
            AmbiguousTickerError: ticker 不唯一
            NotFoundError: 标识符无效
        """
```

---

## 3. Coordinator 层修改

### 3.1 方法重命名

```python
# apps/port/src/ditto_port/services/ingestion/coordinator.py
class IngestionCoordinator:
    def ingest_by_instrument(
        self,
        dataset: str,
        params: InstrumentIngestParams,
        force: bool = False,
    ) -> IngestionResult:
        """
        按标的+时间段摄取数据.

        Args:
            dataset: 数据集名称
            params: 摄取参数 (instrument_id/standard_ticker/ticker, start_date, end_date)
            force: 是否强制覆盖已有数据
        """
        # 1. 解析标识符
        source_ticker = self._metadata_service.resolve_source_ticker(
            ticker=params.ticker,
            standard_ticker=params.standard_ticker,
            instrument_id=params.instrument_id,
            source=self._source_name,
        )

        # 2. 获取数据（DataSource 层继续使用 source_ticker）
        df = self._source.fetch_stock_daily(
            source_ticker=source_ticker,
            start_date=params.start_date,
            end_date=params.end_date,
        )

        # ... 后续处理
```

---

## 4. REST API 设计

### 4.1 路径结构

```
GET /api/source/{source}/{dataset}
    ?ticker=000001
    &start_date=2024-01-01
    &end_date=2024-01-31
```

**示例:**
```
GET /api/source/tushare/stock_daily?ticker=000001&start_date=2024-01-01&end_date=2024-01-31
GET /api/source/akshare/stock_daily?standard_ticker=000001.XSHE&start_date=2024-01-01&end_date=2024-01-31
GET /api/source/tushare/valuation_metrics?instrument_id=1000001&start_date=2024-01-01&end_date=2024-06-30
```

### 4.2 路由实现

```python
# apps/port/src/ditto_port/api/routes/source.py
from fastapi import APIRouter, Path, Query

router = APIRouter(prefix="/source", tags=["source"])


@router.get("/{source}/{dataset}", response_model=SourceDataResponse)
@inject
async def get_source_data(
    source: str = Path(..., description="数据源名称 (如 tushare)"),
    dataset: str = Path(..., description="数据集名称 (如 stock_daily)"),
    # 标识符（三选一）
    ticker: str | None = Query(None, description="裸代码 (如 000001)"),
    standard_ticker: str | None = Query(None, description="Ditto 标准格式 (如 000001.XSHE)"),
    instrument_id: int | None = Query(None, description="内部 ID"),
    # 时间范围
    start_date: str = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="结束日期 (YYYY-MM-DD)"),
    # 依赖注入
    source_service: Annotated[SourceService, FromComponent()] = ...,
    metadata_service: Annotated[MetadataService, FromComponent()] = ...,
) -> SourceDataResponse:
    """
    查询 Source 层数据.

    用途: 验证 ETL 逻辑、调试适配器、数据探索

    示例:
        GET /api/source/tushare/stock_daily?ticker=000001&start_date=2024-01-01&end_date=2024-01-31
    """
```

---

## 5. 修改范围

### 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| **DataHub 层** | |
| `packages/datahub/.../metadata_service.py` | 新增 `resolve_source_ticker()` 方法 |
| **Port 层** | |
| `apps/port/.../ticker_resolver.py` | 重命名 `TickerIngestParams` → `InstrumentIngestParams`，扩展字段 |
| `apps/port/.../coordinator.py` | `ingest_by_ticker` → `ingest_by_instrument`，内部调用 `resolve_source_ticker()` |
| `apps/port/.../protocols.py` | 保持 `source_ticker` 参数（DataSource 层不变） |
| **API 层** | |
| `apps/port/.../routes/source.py` | 路径改为 `/{source}/{dataset}`，参数改为 `ticker`/`standard_ticker`/`instrument_id` |
| **测试层** | |
| 相关测试文件 | 更新调用方式 |

### 不变的部分

- **DataSource 层** - 继续使用 `source_ticker` 参数
- **Adapter 层** - 内部继续使用数据源特有格式
- **Store 层** - 不涉及

---

## 6. 数据流

```
┌─────────────────────────────────────────────────────────────────┐
│  用户输入                                                        │
│  ticker=000001 / standard_ticker=000001.XSHE / instrument_id=1  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  REST API / CLI / Flow                                          │
│  接收 InstrumentIngestParams                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Coordinator.ingest_by_instrument()                             │
│  调用 metadata_service.resolve_source_ticker()                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  MetadataService.resolve_source_ticker()                        │
│  查询 InstrumentReader → 返回 "000001.SZ"                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  DataSource.fetch_stock_daily(source_ticker="000001.SZ", ...)   │
│  数据源层使用 source_ticker                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 验收标准

- [ ] `InstrumentIngestParams` 支持 `ticker`/`standard_ticker`/`instrument_id`
- [ ] `MetadataService.resolve_source_ticker()` 可用
- [ ] `Coordinator.ingest_by_instrument()` 正确转换标识符
- [ ] REST API 路径为 `/api/source/{source}/{dataset}`
- [ ] 所有测试通过
- [ ] 类型检查通过

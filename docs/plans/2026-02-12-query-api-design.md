# 数据查询 API 协议设计

> 日期：2026-02-12
> 状态：设计完成

## 概述

本文档定义 Ditto 项目的数据查询 API 协议，覆盖 REST API、CLI 和 MCP 三种接入方式。

### 实现优先级

1. **REST API + CLI** - 首批实现
2. **MCP 工具映射** - 后续迭代

### 设计原则

- **REST 优先** - 资源语义清晰，符合 HTTP 规范
- **JSON 为主** - 请求/响应统一使用 JSON
- **混合查询模式** - 简单查询 GET，复杂查询 POST（避免 URL 长度限制）
- **AI Agent 友好** - OpenAPI 规范完善，便于生成 MCP 工具

---

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Presentation Layer                      │
├──────────────────────────┬──────────────────────────────────┤
│      REST API (FastAPI)  │      CLI (Typer)                 │
│  /api/v1/{domain}/*      │  ditto query {domain} {resource} │
└──────────────────────────┴──────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Convertor Layer                          │
├─────────────────────────────────────────────────────────────┤
│  Request Models (Pydantic)  │  Response Models (Pydantic)   │
│  - 验证请求数据              │  - 统一响应结构                 │
│  - 转换到 Service 查询对象   │  - 从 Service 结果转换          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              DataHub Service Layer (现有)                    │
├─────────────────────────────────────────────────────────────┤
│  MetadataService │ MarketService │ FundamentalService       │
│  CapitalService  │ MacroService                               │
└─────────────────────────────────────────────────────────────┘
```

### 目录结构

```
apps/port/src/ditto_port/
├── api/
│   ├── routes/           # 路由处理器 (现有，待实现)
│   │   ├── metadata.py
│   │   ├── market.py
│   │   ├── fundamental.py
│   │   ├── capital.py
│   │   └── macro.py      # 新增
│   ├── models/           # 请求/响应模型 (新增)
│   │   ├── common.py     # 分页、错误响应
│   │   ├── metadata.py
│   │   ├── market.py
│   │   ├── fundamental.py
│   │   ├── capital.py
│   │   └── macro.py
│   ├── convertors/       # 转换器 (新增)
│   │   ├── metadata_convertor.py
│   │   ├── market_convertor.py
│   │   ├── fundamental_convertor.py
│   │   ├── capital_convertor.py
│   │   └── macro_convertor.py
│   └── errors.py         # 统一异常体系 (新增)
├── cli/
│   └── commands/
│       └── query/        # 查询命令组 (新增)
│           ├── metadata.py
│           ├── market.py
│           ├── fundamental.py
│           ├── capital.py
│           └── macro.py
```

---

## API 整体结构

### URL 结构

```
/api/v1/{domain}/{resource}
```

### 领域划分

| Domain | 资源 | 说明 |
|--------|------|------|
| `metadata` | 基础信息 | 标的、行业、交易日历 |
| `market` | 行情数据 | K线、复权因子、股票状态 |
| `fundamental` | 财务数据 | 三大表、分红 |
| `capital` | 资金数据 | 估值、融资融券、质押 |
| `macro` | 宏观数据 | 经济指标、利率、汇率 |

### 命名约定

- **路径**：kebab-case（`/market/adj-factors`）
- **字段**：snake_case（`instrument_id`, `trade_date`）
- **枚举**：小写（`stock`, `etf`, `qfq`）

---

## HTTP 规范

### 请求头

```
Content-Type: application/json
Accept: application/json
X-Request-ID: <uuid>  # 可选，链路追踪
```

### 状态码

| 状态码 | 场景 |
|--------|------|
| `200` | 成功（包括空结果） |
| `400` | 参数错误（格式/语义） |
| `429` | 限流 |
| `500` | 服务端错误 |

**注意**：查询无数据不返回 404，而是返回空结果（`{"data": null}` 或 `{"data": []}`）

### 响应结构

```json
// 成功 - 单资源（可能为 null）
{ "data": { ... } | null }

// 成功 - 列表（可能为空）
{ "data": [...] }

// 成功 - 列表（有分页）
{
  "data": [...],
  "pagination": { "limit": 100 }
}

// 错误
{
  "error": {
    "code": "INVALID_DATE_RANGE",
    "message": "start_date (2024-12-01) cannot be greater than end_date (2024-01-01)"
  }
}
```

### 响应头

```
X-Request-ID: abc-123
Content-Type: application/json
```

---

## 错误码规范

| Code | HTTP | 说明 |
|------|------|------|
| `INVALID_PARAMETER` | 400 | 参数格式错误 |
| `INVALID_DATE_RANGE` | 400 | 日期范围无效 |
| `MISSING_REQUIRED_FIELD` | 400 | 缺少必填字段 |
| `RATE_LIMIT_EXCEEDED` | 429 | 请求频率超限 |
| `INTERNAL_ERROR` | 500 | 服务端错误 |

---

## 分页机制

### 当前实现（简化版）

仅支持 `limit` 参数：

```json
// 请求
{
  "limit": 100
}

// 响应
{
  "data": [...],
  "pagination": { "limit": 100 }
}
```

### TODO: Cursor 分页（后续迭代）

```json
// 请求
{
  "limit": 100,
  "cursor": "eyJpZCI6MTAwfQ=="
}

// 响应
{
  "data": [...],
  "pagination": {
    "cursor": "eyJpZCI6MjAwfQ==",
    "has_more": true,
    "limit": 100
  }
}
```

### 适用端点

| 端点 | 是否分页 | 说明 |
|------|---------|------|
| `/market/bars` | ✅ | 时序数据量大 |
| `/fundamental/*` | ✅ | 按报告期分页 |
| `/capital/*` | ✅ | 时序数据 |
| `/macro/indicators` | ✅ | 时序数据 |
| `/metadata/instruments` | 可选 | 列表较长时分页 |

---

## 请求/响应模型

### 通用模型

```python
# api/models/common.py

class PaginationRequest(BaseModel):
    """分页请求（简化版）"""
    limit: int = Field(default=100, ge=1, le=1000)

class PaginationResponse(BaseModel):
    """分页响应（简化版）"""
    limit: int
    # TODO: cursor, has_more

class ErrorResponse(BaseModel):
    """统一错误响应"""
    code: str
    message: str

class APIResponse(BaseModel, Generic[T]):
    """统一成功响应"""
    data: T
    pagination: PaginationResponse | None = None
```

### 命名约定

| 层级 | 命名 | 示例 |
|------|------|------|
| 请求模型 | `{Resource}Request` | `BarsRequest` |
| 响应模型 | `{Resource}Response` | `BarsResponse` |
| 单资源 | `{Resource}` (单数) | `Bar`, `Instrument` |
| 字段 | snake_case | `instrument_id`, `trade_date` |

---

## 统一异常体系

### 异常类层次

```python
# api/errors.py

class APIError(Exception):
    """API 错误基类"""
    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "Internal server error"

class ValidationError(APIError):
    """参数验证错误"""
    status_code = 400
    code = "INVALID_PARAMETER"

class DateRangeError(APIError):
    """日期范围错误"""
    status_code = 400
    code = "INVALID_DATE_RANGE"

class RateLimitError(APIError):
    """限流错误"""
    status_code = 429
    code = "RATE_LIMIT_EXCEEDED"
```

### 全局异常处理器

```python
# api/exception_handlers.py

async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
        headers={"X-Request-ID": request.headers.get("X-Request-ID", "")},
    )
```

---

## Metadata 域

### 端点设计

```
GET  /api/v1/metadata/instruments/{instrument_id}
GET  /api/v1/metadata/instruments?asset_class=stock&exchange=sh
POST /api/v1/metadata/instruments/query
GET  /api/v1/metadata/industries
GET  /api/v1/metadata/industries/{industry_id}/instruments?asof=2024-06-01
GET  /api/v1/metadata/calendar/{year}
```

### Instrument 资源结构

```json
{
  "instrument_id": 1000001,
  "ticker": "600000",
  "name": "浦发银行",
  "asset_class": "stock",
  "exchange": "sh",
  "list_date": "1999-11-10",
  "is_active": true
}
```

### Asset Class 枚举

| 值 | 说明 | instrument_id 区间 |
|----|------|-------------------|
| `stock` | 股票 | 1,000,000 - 1,999,999 |
| `etf` | ETF | 2,000,000 - 2,999,999 |
| `index` | 指数 | 3,000,000 - 3,999,999 |

### Instruments 查询请求

```json
// POST /api/v1/metadata/instruments/query
{
  "asset_class": "stock",
  "exchanges": ["sh", "sz"],
  "is_active": true,
  "asof": "2024-06-01"
}
```

### Industry 资源结构

```json
{
  "industry_id": 800001,
  "name": "银行",
  "level": 1,
  "parent_id": null,
  "is_active": true
}
```

### Calendar 资源结构

```json
{
  "year": 2024,
  "trading_days": ["2024-01-02", "2024-01-03", ...],
  "holidays": ["2024-01-01", "2024-02-10", ...]
}
```

---

## Market 域

### 端点设计

```
POST /api/v1/market/bars
GET /api/v1/market/bars/daily/{trade_date}?asset_class=stock
POST /api/v1/market/adj-factors
POST /api/v1/market/status
```

### Bar 资源结构

```json
{
  "instrument_id": 1000001,
  "trade_date": "2024-06-01",
  "open": 10.5,
  "high": 10.8,
  "low": 10.3,
  "close": 10.6,
  "volume": 12345678,
  "amount": 130567890.12,
  "turnover_rate": 0.85
}
```

### Bars 查询请求

```json
// POST /api/v1/market/bars
{
  "instrument_ids": [1000001, 1000002],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "adjustment": "qfq",
  "limit": 1000
}
```

### Adjustment 枚举

| 值 | 说明 |
|----|------|
| `none` | 不复权（原始价格） |
| `qfq` | 前复权 |
| `hfq` | 后复权 |

### AdjFactor 资源结构

```json
{
  "instrument_id": 1000001,
  "trade_date": "2024-06-01",
  "adj_factor": 1.0523
}
```

### Status 资源结构

```json
{
  "instrument_id": 1000001,
  "trade_date": "2024-06-01",
  "is_suspended": false,
  "is_st": false
}
```

---

## Fundamental 域

### 端点设计

```
POST /api/v1/fundamental/balance-sheet
POST /api/v1/fundamental/income-statement
POST /api/v1/fundamental/cash-flow
POST /api/v1/fundamental/dividends
```

### 通用请求结构

```json
{
  "instrument_ids": [1000001],
  "start_date": "2023-01-01",
  "end_date": "2024-12-31",
  "report_type": "report",
  "asof": "2024-06-01",
  "limit": 100
}
```

### Report Type 枚举

| 值 | 说明 |
|----|------|
| `report` | 报告期（财报上的日期） |
| `announce` | 公告日（实际发布日期） |

### Balance Sheet 资源结构

```json
{
  "instrument_id": 1000001,
  "report_date": "2024-03-31",
  "announce_date": "2024-04-28",
  "total_assets": 8500000000000,
  "total_liabilities": 7600000000000,
  "total_equity": 900000000000,
  "current_assets": 3200000000000,
  "current_liabilities": 2800000000000
}
```

### Income Statement 资源结构

```json
{
  "instrument_id": 1000001,
  "report_date": "2024-03-31",
  "announce_date": "2024-04-28",
  "revenue": 50000000000,
  "operating_profit": 8000000000,
  "net_profit": 6000000000,
  "eps": 0.5
}
```

### Cash Flow 资源结构

```json
{
  "instrument_id": 1000001,
  "report_date": "2024-03-31",
  "announce_date": "2024-04-28",
  "operating_cf": 3000000000,
  "investing_cf": -1500000000,
  "financing_cf": -500000000,
  "free_cf": 2000000000
}
```

### Dividend 资源结构

```json
{
  "instrument_id": 1000001,
  "announce_date": "2024-03-15",
  "ex_date": "2024-04-10",
  "cash_dividend": 0.5,
  "stock_dividend": 0.1
}
```

---

## Capital 域

### 端点设计

```
POST /api/v1/capital/valuations
POST /api/v1/capital/margin
POST /api/v1/capital/pledge
```

### Valuation 资源结构

```json
{
  "instrument_id": 1000001,
  "trade_date": "2024-06-01",
  "pe_ttm": 8.5,
  "pe_lyr": 9.2,
  "pb": 0.85,
  "ps_ttm": 1.2,
  "total_mv": 250000000000,
  "circ_mv": 180000000000
}
```

### Valuations 查询请求

```json
// POST /api/v1/capital/valuations
{
  "instrument_ids": [1000001],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "metrics": ["pe_ttm", "pb", "ps_ttm"],
  "limit": 1000
}
```

### Margin 资源结构

```json
{
  "instrument_id": 1000001,
  "trade_date": "2024-06-01",
  "fin_buy_amount": 12345678.90,
  "fin_balance": 987654321.00,
  "sec_sell_volume": 1234567,
  "sec_balance": 98765432
}
```

### Pledge 资源结构

```json
{
  "instrument_id": 1000001,
  "trade_date": "2024-06-01",
  "pledge_ratio": 0.15,
  "pledge_share": 50000000,
  "unpledge_share": 280000000
}
```

---

## Macro 域

### 端点设计

```
POST /api/v1/macro/indicators
GET  /api/v1/macro/indicators/metadata
```

### 请求/响应模型

```python
class MacroCategory(str, Enum):
    economic = "economic"
    interest_rate = "interest_rate"
    exchange_rate = "exchange_rate"
    money_supply = "money_supply"

class MacroFrequency(str, Enum):
    daily = "daily"
    monthly = "monthly"
    quarterly = "quarterly"

class IndicatorsRequest(BaseModel):
    indicators: list[int] | list[str] | None = None
    start_date: date
    end_date: date
    category: MacroCategory | None = None
    frequency: MacroFrequency | None = None
    limit: int = Field(default=1000, ge=1, le=5000)
```

### Indicator 资源结构

```json
{
  "indicator_id": 1,
  "code": "gdp_cpi",
  "name": "GDP同比",
  "date": "2024-03-31",
  "value": 5.3,
  "category": "economic",
  "frequency": "quarterly",
  "unit": "%"
}
```

### IndicatorMetadata 资源结构

```json
{
  "indicator_id": 1,
  "code": "gdp_cpi",
  "name": "GDP同比",
  "category": "economic",
  "frequency": "quarterly",
  "unit": "%",
  "source": "国家统计局",
  "description": "国内生产总值同比增长率"
}
```

---

## CLI 查询设计

### 设计原则

- **共享 Service 层** - CLI 和 API 都直接调用 DataHub Service
- **共享模型** - 复用 API 层的 Pydantic 模型和 Convertor
- **JSON 优先** - 默认输出 JSON，便于 Agent 解析

### 命令结构

```bash
ditto query <domain> <resource> [options]
```

### 全局选项

| 选项 | 说明 |
|------|------|
| `--format <json\|table>` | 输出格式，默认 json |
| `--compact` | 紧凑 JSON（无缩进） |
| `--limit <n>` | 分页限制 |

### CLI 命令示例

```bash
# Metadata
ditto query metadata instruments --id 1000001
ditto query metadata instruments --asset-class stock --exchange sh
ditto query metadata industries
ditto query metadata calendar 2024

# Market
ditto query market bars --ids 1000001,1000002 --start 2024-01-01 --end 2024-12-31 --adj qfq
ditto query market adj-factors --ids 1000001 --start 2024-01-01
ditto query market status --ids 1000001 --start 2024-06-01

# Fundamental
ditto query fundamental balance-sheet --ids 1000001 --start 2023-01-01
ditto query fundamental income-statement --ids 1000001 --start 2023-01-01
ditto query fundamental cash-flow --ids 1000001 --start 2023-01-01
ditto query fundamental dividends --ids 1000001 --start 2023-01-01

# Capital
ditto query capital valuations --ids 1000001 --metrics pe_ttm,pb
ditto query capital margin --ids 1000001 --start 2024-01-01
ditto query capital pledge --ids 1000001 --start 2024-01-01

# Macro
ditto query macro indicators --codes gdp_cpi --start 2024-01-01 --end 2024-12-31
ditto query macro indicators --category interest_rate --start 2024-01-01
ditto query macro metadata --category economic
```

### 输出格式

```bash
# 默认 JSON（带缩进）
ditto query metadata instruments --id 1000001

# 紧凑 JSON（Agent 友好）
ditto query metadata instruments --id 1000001 --compact

# 表格格式（人类友好，后续迭代）
ditto query metadata instruments --asset-class stock --format table
```

---

## MCP 工具映射（后续迭代）

OpenAPI 规范可自动生成 MCP 工具，每个 POST 端点对应一个工具。

### Metadata 工具

| 工具名 | 端点 | 说明 |
|--------|------|------|
| `query_instruments` | POST /metadata/instruments/query | 标的列表查询 |

### Market 工具

| 工具名 | 端点 | 说明 |
|--------|------|------|
| `query_bars` | POST /market/bars | K线查询 |
| `query_adj_factors` | POST /market/adj-factors | 复权因子查询 |
| `query_status` | POST /market/status | 股票状态查询 |

### Fundamental 工具

| 工具名 | 端点 | 说明 |
|--------|------|------|
| `query_balance_sheet` | POST /fundamental/balance-sheet | 资产负债表 |
| `query_income_statement` | POST /fundamental/income-statement | 利润表 |
| `query_cash_flow` | POST /fundamental/cash-flow | 现金流量表 |
| `query_dividends` | POST /fundamental/dividends | 分红送转 |

### Capital 工具

| 工具名 | 端点 | 说明 |
|--------|------|------|
| `query_valuations` | POST /capital/valuations | 估值指标 |
| `query_margin` | POST /capital/margin | 融资融券 |
| `query_pledge` | POST /capital/pledge | 股权质押 |

### Macro 工具

| 工具名 | 端点 | 说明 |
|--------|------|------|
| `query_indicators` | POST /macro/indicators | 宏观指标查询 |

---

## API 端点总览

| Domain | Method | Endpoint | 说明 |
|--------|--------|----------|------|
| **metadata** | GET | `/instruments/{id}` | 获取单个标的 |
| | GET | `/instruments` | 简单筛选 |
| | POST | `/instruments/query` | 复杂查询 |
| | GET | `/industries` | 行业列表 |
| | GET | `/industries/{id}/instruments` | 行业成分股 |
| | GET | `/calendar/{year}` | 交易日历 |
| **market** | POST | `/bars` | K线查询 |
| | GET | `/bars/daily/{date}` | 全市场日线 |
| | POST | `/adj-factors` | 复权因子 |
| | POST | `/status` | 股票状态 |
| **fundamental** | POST | `/balance-sheet` | 资产负债表 |
| | POST | `/income-statement` | 利润表 |
| | POST | `/cash-flow` | 现金流量表 |
| | POST | `/dividends` | 分红送转 |
| **capital** | POST | `/valuations` | 估值指标 |
| | POST | `/margin` | 融资融券 |
| | POST | `/pledge` | 股权质押 |
| **macro** | POST | `/indicators` | 宏观指标查询 |
| | GET | `/indicators/metadata` | 指标元数据 |

---

## 测试策略

### 单元测试

测试适配器转换逻辑：

```python
# tests/unit/api/convertors/test_market_convertor.py
def test_to_bars_query():
    request = BarsRequest(
        instrument_ids=[1000001],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        adjustment=Adjustment.qfq,
    )
    query = MarketConvertor.to_bars_query(request)
    assert query.instrument_ids == [1000001]
    assert query.adjustment == "qfq"
```

### 集成测试

测试 Router 与 Service 的接缝：

```python
# tests/integration/api/test_market_router.py
def test_bars_endpoint_calls_service_correctly():
    mock_service = MagicMock()
    mock_service.find_bars.return_value = pl.DataFrame([...])

    client = TestClient(app_with_overrides(mock_service))
    response = client.post("/api/v1/market/bars", json={...})

    assert response.status_code == 200
    mock_service.find_bars.assert_called_once()
```

---

## 待办事项

| 优先级 | 项目 | 说明 |
|--------|------|------|
| P1 | REST API 实现 | 5 域 19 端点 |
| P1 | CLI query 命令 | 5 域 15 命令 |
| P2 | Cursor 分页 | 完整实现 cursor-based 分页 |
| P2 | MCP 工具映射 | 基于 OpenAPI 生成 MCP 工具 |
| P3 | 限流 | 实现 RateLimitError |
| P3 | Table 输出格式 | CLI 人类友好输出 |

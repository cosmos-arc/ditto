# Query API 设计方案（已验证）

> **设计日期**: 2026-02-12
> **状态**: 已验证，准备实施

## 设计决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 参数传递风格 | Query Object 模式 | 与 Service 层保持一致，参数多时更清晰 |
| Convertor 风格 | 函数式模块 | 更 Pythonic，避免只有静态方法的类 |
| 模型位置 | `models/{domain}.py` | API 和 CLI 共用，与 api/ 同级 |
| 模型与转换器 | 放在一起 | 职责集中，易于查找 |
| API 响应格式 | 统一包装（`APIResponse[T]`） | 一致的响应格式，前端处理更简单 |
| CLI 输出格式 | 表格输出（默认）+ `--json` 选项 | 用户体验好，也支持脚本处理 |
| 日期校验位置 | Pydantic `@model_validator` | 校验逻辑复用，更 DRY |
| 实现范围 | 全部 5 个域 | 完整实现 |

---

## 目录结构

```
apps/port/src/ditto_port/
├── models/                      # 共享模型（API + CLI）
│   ├── __init__.py
│   ├── common.py               # PaginationRequest/Response, APIResponse
│   ├── metadata.py             # Instrument, InstrumentQuery, to_instrument()
│   ├── market.py               # Bar, BarsQuery, to_bar()
│   ├── fundamental.py          # Financial, Dividend, CorporateAction...
│   ├── capital.py              # Margin, Valuation, Futures...
│   └── macro.py                # Indicator, IndicatorQuery...
│
├── api/
│   ├── routes/                 # 路由（修改现有文件）
│   │   ├── metadata.py
│   │   ├── market.py
│   │   ├── fundamental.py      # 新增
│   │   ├── capital.py          # 新增
│   │   └── macro.py            # 新增
│   └── errors.py               # API 专用异常（DateRangeError 等）
│
└── cli/
    └── commands/
        └── query/              # 新增查询命令组
            ├── __init__.py
            ├── metadata.py
            ├── market.py
            ├── fundamental.py
            ├── capital.py
            └── macro.py
```

---

## 端点设计

### Metadata 域（5 个端点）

| 端点 | 方法 | 对应 Service 方法 | 说明 |
|------|------|-------------------|------|
| `/instruments/{id}` | GET | `get_instrument()` | 获取单个标的 |
| `/instruments` | GET | `find_securities()` | 查询标的列表 |
| `/industries` | GET | `find_industries()` | 行业列表 |
| `/calendar` | GET | `list_calendar_range()` | 交易日历 |
| `/universe/{id}` | GET | `get_universe()` | 标的池 |

### Market 域（2 个端点）

| 端点 | 方法 | 对应 Service 方法 | 说明 |
|------|------|-------------------|------|
| `/bars` | POST | `find_bars()` | K线查询 |
| `/constituents/{index_id}` | GET | `get_constituents()` | 指数成分 |

### Fundamental 域（3 个端点）

| 端点 | 方法 | 对应 Service 方法 | 说明 |
|------|------|-------------------|------|
| `/financials/{type}` | GET | `get_balance_sheet/income_statement/cash_flow()` | 财务报表 |
| `/dividend` | GET | `get_dividend()` | 分红数据 |
| `/corporate-actions` | GET | `list_corporate_actions()` | 公司行动 |

### Capital 域（3 个端点）

| 端点 | 方法 | 对应 Service 方法 | 说明 |
|------|------|-------------------|------|
| `/margin` | GET | `get_margin_trading()` | 融资融券 |
| `/valuation` | GET | `get_valuation_metrics()` | 估值指标 |
| `/futures` | GET | `get_futures()` | 期货持仓 |

### Macro 域（2 个端点）

| 端点 | 方法 | 对应 Service 方法 | 说明 |
|------|------|-------------------|------|
| `/indicators` | GET | `find_indicators()` | 宏观指标 |
| `/indicators/metadata` | GET | - | 指标元数据 |

**总计: 15 个端点**

---

## 模型层设计

每个域的模型文件包含三类内容：

```python
# models/metadata.py 示例结构

# ========== Query Object ==========
class AssetClass(str, Enum): ...
class InstrumentQuery(BaseModel): ...

# ========== Response Model ==========
class Instrument(BaseModel): ...

# ========== Convertor 函数 ==========
def to_instrument(row: dict[str, Any]) -> Instrument: ...
def to_instrument_list(df: pl.DataFrame) -> list[Instrument]: ...
```

### 公共模型

```python
# models/common.py

class PaginationRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)

class PaginationResponse(BaseModel):
    limit: int

class APIResponse(BaseModel, Generic[T]):
    data: T
    pagination: PaginationResponse | None = None
```

### 日期校验

```python
# models/market.py

class BarsQuery(BaseModel):
    instrument_ids: list[int] = Field(..., min_length=1, max_length=100)
    start_date: date
    end_date: date
    adjustment: Adjustment = Adjustment.none
    limit: int = Field(default=1000, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.start_date > self.end_date:
            raise ValueError(
                f"start_date ({self.start_date}) cannot be greater than "
                f"end_date ({self.end_date})"
            )
        return self
```

---

## API 路由层设计

```python
# api/routes/metadata.py

@router.get("/instruments/{instrument_id}")
async def get_instrument(
    instrument_id: int,
    service: MetadataService = Depends(get_metadata_service),
) -> APIResponse[Instrument | None]:
    result = service.get_instrument(instrument_id)
    if result is None:
        return APIResponse(data=None)
    return APIResponse(data=to_instrument(result))

@router.get("/instruments")
async def list_instruments(
    query: InstrumentQuery = Depends(),
    service: MetadataService = Depends(get_metadata_service),
) -> APIResponse[list[Instrument]]:
    df = service.find_securities(...)
    instruments = to_instrument_list(df)
    return APIResponse(
        data=instruments,
        pagination=PaginationResponse(limit=query.limit),
    )
```

---

## CLI 查询命令设计

```python
# cli/commands/query/metadata.py

@app.command("instruments")
def query_instruments(
    asset_class: str | None = typer.Option(None, "--asset-class", "-a"),
    exchange: str | None = typer.Option(None, "--exchange", "-e"),
    limit: int = typer.Option(100, "--limit", "-l"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    # 构建查询对象（复用 API 模型）
    query = InstrumentQuery(...)

    # 调用 Service
    service = get_service("metadata")
    df = service.find_securities(...)
    instruments = to_instrument_list(df)  # 复用 Convertor

    # 输出
    if json_output:
        console.print(orjson.dumps([i.model_dump() for i in instruments]).decode())
    else:
        # Rich 表格输出
        table = Table(title="Instruments")
        ...
```

---

## 测试策略

| 测试类型 | 位置 | 职责 |
|---------|------|------|
| 单元测试 | `tests/unit/models/test_{domain}_unit.py` | 测试 Query Object 校验、Convertor 函数 |
| 集成测试 | `tests/integration/api/test_{domain}_router_unit.py` | 测试路由端点，Mock Service |

---

## 下一步

设计方案已验证完成，可以进入实施阶段。

参考实施计划: `docs/plans/2026-02-12-query-api-impl.md`

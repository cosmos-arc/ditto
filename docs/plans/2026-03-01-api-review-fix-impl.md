# API Review 修复实施计划

Date: 2026-03-01

## 概述

本文档描述 PR #57 审查发现的四个问题的修复实施步骤。

## 实施任务

### 任务 1: 参数重命名 (P1-1)

**目标**: 将 `pairs`/`symbols` 重命名为 `currency_pairs`/`commodity_codes`

**文件变更**:
| 文件 | 变更 |
|-----|-----|
| `apps/port/src/ditto_port/models/fx.py` | `FxQuery.pairs` → `FxQuery.currency_pairs`<br>` `FxBar.pair` → `FxBar.currency_pair` |
| `apps/port/src/ditto_port/api/routes/fx.py` | `query.pairs` → `query.currency_pairs`<br>` 变量命名更新 |
| `apps/port/src/ditto_port/models/commodity.py` | `CommodityQuery.symbols` → `CommodityQuery.commodity_codes`<br>` `CommodityBar.symbol` → `CommodityBar.commodity_code` |
| `apps/port/src/ditto_port/api/routes/commodity.py` | `query.symbols` → `query.commodity_codes`<br>` 变量命名更新 |

| `packages/datahub/src/ditto_datahub/sources/tushare/adapters/fx.py` | `FX_CODE_TO_INSTRUMENT_ID` 命名更新（如需要） |
| `packages/datahub/src/ditto_datahub/sources/fred/adapters/commodity.py` | `COMMODITY_CODE_TO_INSTRUMENT_ID` 命名更新（如需要） |

**测试**:
- 更新 `tests/unit/models/test_fx_models.py`
- 更新 `tests/unit/models/test_commodity_models.py`
- 更新 `tests/integration/test_main_routes_integration.py`

---

### 任务 2: 鷻加非法参数严格校验 (P1-1)

**目标**: 对非法 `currency_pairs`/`commodity_codes` 返回 400 错误

**文件变更**:
| 文件 | 变更 |
|-----|-----|
| `apps/port/src/ditto_port/api/routes/fx.py` | 添加参数校验逻辑 |
| `apps/port/src/ditto_port/api/routes/commodity.py` | 添加参数校验逻辑 |
| `apps/port/src/ditto_port/api/errors.py` | 添加 `InvalidParameterError` 异常（如已存在则复用） |

**实现代码**:
```python
# fx.py
from fastapi import HTTPException

from ditto_port.api.errors import InvalidParameterError  # 如果存在

# 在 post_bars() 中
if query.currency_pairs:
    invalid_pairs = [
        p for p in query.currency_pairs
        if p not in FX_CODE_TO_INSTRUMENT_ID
    ]
    if invalid_pairs:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_currency_pairs",
                "invalid": invalid_pairs,
                "valid": list(FX_CODE_TO_INSTRUMENT_ID.keys()),
            }
        )
    instrument_ids = [
        FX_CODE_TO_INSTRUMENT_ID[p]
        for p in query.currency_pairs
    ]
```

**测试**:
- 添加单元测试验证 400 错误
- 添加集成测试验证 API 响应

---

### 任务 3: limit 参数下推 (P1-2)

**目标**: 将 limit 参数从 API 层下推到 Service 层 DataFrame 处理

**文件变更**:
| 文件 | 变更 |
|-----|-----|
| `packages/datahub/src/ditto_datahub/services/market_service.py` | `MarketBarsQuery` 添加 `limit` 字段 |
| `packages/datahub/src/ditto_datahub/services/market_service.py` | `list_bars()` 添加 `limit` 参数 |
| `packages/datahub/src/ditto_datahub/services/market_service.py` | `_load_bars_core()` 添加 `limit` 参数并在读取后应用 `df.head(limit)` |
| `apps/port/src/ditto_port/api/routes/fx.py` | 传递 `limit` 参数，移除内存切片 |
| `apps/port/src/ditto_port/api/routes/commodity.py` | 传递 `limit` 参数，移除内存切片 |
| `apps/port/src/ditto_port/api/routes/market.py` | 传递 `limit` 参数，移除内存切片 |

**实现代码**:
```python
# MarketBarsQuery
@dataclass(frozen=True)
class MarketBarsQuery:
    # ... 现有字段
    limit: int | None = None  # 新增

# MarketService.list_bars()
def list_bars(
    self,
    instrument_ids: list[int],
    start: str | None = None,
    end: str | None = None,
    # ... 其他参数
    limit: int | None = None,  # 新增
) -> pl.DataFrame:
    query = MarketBarsQuery(
        instrument_ids=instrument_ids,
        start=start,
        end=end,
        limit=limit,  # 传递
    )
    return self._query_bars(query)

# MarketService._load_bars_core()
def _load_bars_core(
    self,
    instrument_ids: list[int],
    start: date | None,
    end: date | None,
    asset_class: str,
    limit: int | None = None,  # 新增
) -> pl.DataFrame:
    # ... 现有逻辑
    df = reader.read(...)

    # 在 DataFrame 层应用 limit
    if limit is not None:
        df = df.head(limit)

    return df
```

**测试**:
- 单元测试验证 limit 下推
- 鷻加集成测试验证 API 层 limit 生效

---

### 任务 4: trade_date_utc 字段语义修复 (P2-1)

**目标**: 将 `trade_date_utc` 改为 `trade_date`，移除 `dt.date()` 截断

**文件变更**:
| 文件 | 变更 |
|-----|-----|
| `apps/port/src/ditto_port/models/fx.py` | `FxBar.trade_date_utc` → `FxBar.trade_date` |
| `apps/port/src/ditto_port/models/commodity.py` | `CommodityBar.trade_date_utc` → `CommodityBar.trade_date` |
| `apps/port/src/ditto_port/api/routes/fx.py` | 移除 `dt.date()` 截断，直接使用字符串 |
| `apps/port/src/ditto_port/api/routes/commodity.py` | 移除 `dt.date()` 截断，直接使用字符串 |

**注意**: 需要确认数据源中 `trade_date_utc` 的真实类型。如果存储的是 datetime 类型，需要调整转换逻辑。
**测试**:
- 更新模型测试
- 添加 API 响应测试
---

### 任务 5: Bond Yield 日期解析增强 (P2-2)
**目标**: 添加浮点数校验,拒绝带小数的日期值

**文件变更**:
| 文件 | 变更 |
|-----|-----|
| `packages/datahub/src/ditto_datahub/sources/tushare/adapters/bond_yield.py` | 在 `_parse_trade_date()` 中添加浮点数校验 |

**实现代码**:
```python
def _parse_trade_date(trade_date: object) -> date | None:
    try:
        date_str = str(trade_date)
        if len(date_str) == _DATE_STR_LENGTH:
            return date_str
        elif isinstance(trade_date, (int, float)):
            # 检查是否为整数值或有小数
            if isinstance(trade_date, float) and not trade_date.is_integer():
                logger.warning(
                    "Invalid trade_date with decimal, skipping",
                    event="bond_yield_invalid_date",
                    trade_date=trade_date,
                )
                return None
            date_val = str(int(trade_date))
        else:
            return None
    except (ValueError, TypeError):
        return None
```

**测试**:
- 添加单元测试验证浮点数拒绝
- 添加边界情况测试

---

## 实施顺序

1. 任务 1 (参数重命名) - 无依赖
2. 任务 5 (Bond Yield 日期解析) - 无依赖
3. 任务 4 (trade_date 字段) - 无依赖
4. 任务 2 (严格校验) - 依赖任务 1
5. 任务 3 (limit 下推) - 可独立进行

**建议并行执行**: 任务 1 + 5 + 4 可以并行，任务 2 依赖任务 1 完成后开始，任务 3 可独立进行

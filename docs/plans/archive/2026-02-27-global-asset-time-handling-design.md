# 全球资产标的时间处理设计

> 汇率、大宗商品日线数据的摄取与存储时间处理规则

## 1. 设计目标

| 需求 | 决策 |
|------|------|
| 时间精度 | UTC 时间戳 + 本地 trade_date |
| 数据对齐 | 存储层独立，查询时动态对齐 |
| 结算日 | 仅存储 trade_date（外汇 T+2 在应用层计算） |
| 摄取时机 | 次日批量摄取 |

---

## 2. 时间戳约定

### 2.1 双时间戳设计

日线数据采用**双时间戳**设计：

| 字段 | 类型 | 含义 | 用途 |
|------|------|------|------|
| `trade_date` | `date` | 交易日期（交易所本地） | 分区键、日历查询 |
| `trade_date_utc` | `datetime[UTC]` | UTC 午夜时间戳 | 跨时区对齐 |

```python
# Schema 定义
DAILY_BAR_SCHEMA = {
    "instrument_id": pl.Int64,
    "trade_date": pl.Date,                    # 本地交易日期
    "trade_date_utc": pl.Datetime("ms"),      # UTC 00:00:00 时间戳
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
}
```

### 2.2 UTC 时间戳锚定规则

**采用 UTC 午夜（UTC 00:00:00）作为日线锚定时间**：

```
trade_date = 2026-02-27 (本地)
trade_date_utc = 2026-02-27T00:00:00Z (UTC)
```

**理由**：
- 全球统一标准，消除时区歧义
- 便于跨市场数据对齐
- 与 Parquet 分区策略兼容（年分区）

### 2.3 各市场时区映射

| 市场/资产 | 本地时区 | trade_date 含义 |
|----------|---------|----------------|
| A股 | Asia/Shanghai (UTC+8) | 北京时间 00:00-23:59 |
| 美股 | America/New_York (UTC-5/-4) | 纽约时间 00:00-23:59 |
| 外汇 | 无固定（24h） | 按 NY 收盘界定（17:00 ET） |
| LME商品 | Europe/London (UTC+0/+1) | 伦敦时间 00:00-23:59 |
| CME商品 | America/Chicago (UTC-6/-5) | 芝加哥时间 00:00-23:59 |

**外汇特殊处理**：
- 外汇市场 24 小时运行，以 **纽约时间 17:00** 作为日分割点
- NY 17:00 = UTC 22:00（夏令时）/ 21:00（冬令时）
- 存储时统一映射到 UTC 午夜

---

## 3. 数据摄取规则

### 3.1 摄取时间窗口

**次日批量摄取**，确保数据完整：

| 资产类型 | 数据源 | 摄取时间窗口（北京时间） |
|---------|--------|----------------------|
| A股 | Tushare | T+1 08:00 后 |
| 美股 | TBD | T+1 06:00 后（考虑夏令时） |
| 外汇 | Tushare/FRED | T+1 07:00 后 |
| 商品 | FRED | T+1 07:00 后 |

### 3.2 摄取流程

```
┌─────────────────────────────────────────────────────────────┐
│                    次日批量摄取流程                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 确定摄取日期 T-1                                        │
│     └─ 根据各市场交易日历判断 T-1 是否为交易日               │
│                                                             │
│  2. 从数据源拉取 T-1 日数据                                 │
│     └─ 源数据通常使用本地日期格式                           │
│                                                             │
│  3. 时间戳转换                                              │
│     └─ trade_date: 保持本地日期                             │
│     └─ trade_date_utc: 转换为 UTC 午夜时间戳                │
│                                                             │
│  4. 写入存储                                                │
│     └─ 按年份分区（year=trade_date.year）                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 时间戳转换代码

```python
from datetime import date, datetime, timezone
from typing import Literal

import pytz


def convert_to_utc_timestamp(
    trade_date: date,
    market: Literal["SSE", "NYSE", "LME", "CME", "FX"],
) -> datetime:
    """
    将本地交易日期转换为 UTC 午夜时间戳.

    Args:
        trade_date: 本地交易日期
        market: 市场代码

    Returns:
        UTC 午夜时间戳（datetime with UTC timezone）

    """
    # 时区映射
    TZ_MAP = {
        "SSE": "Asia/Shanghai",
        "NYSE": "America/New_York",
        "LME": "Europe/London",
        "CME": "America/Chicago",
        "FX": "UTC",  # 外汇直接使用 UTC
    }

    tz = pytz.timezone(TZ_MAP[market])

    # 创建本地午夜时间，然后转换为 UTC
    local_midnight = tz.localize(
        datetime(trade_date.year, trade_date.month, trade_date.day, 0, 0, 0)
    )

    return local_midnight.astimezone(timezone.utc)
```

---

## 4. 存储层设计

### 4.1 分区策略

**年分区**（当前项目已采用）：

```
data_root/
  market/
    fx/
      bars/
        2024.parquet
        2025.parquet
        2026.parquet
    commodity/
      bars/
        2024.parquet
        2025.parquet
        2026.parquet
```

### 4.2 Schema 扩展

**现有 Schema**：
```python
FX_SOURCE_SCHEMA = SourceSchema(
    dataset="fx_daily",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    },
)
```

**建议扩展**：
```python
FX_SOURCE_SCHEMA = SourceSchema(
    dataset="fx_daily",
    key_columns=("instrument_id", "trade_date"),
    schema={
        "instrument_id": pl.Int64,
        "trade_date": pl.Date,
        "trade_date_utc": pl.Datetime("ms"),  # 新增：UTC 时间戳
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
    },
)
```

### 4.3 元数据管理

每个数据集需要关联交易日历：

```python
# 交易日历注册
INSTRUMENT_CALENDAR = {
    # 汇率 - 4M 范围
    4_000_001: "FX",  # USDCNH
    4_000_002: "FX",  # EURUSD
    # 商品 - 5M 范围
    5_000_001: "CME",  # WTI
    5_000_002: "ICE",  # Brent
    5_000_003: "LME",  # Gold（伦敦金）
}
```

---

## 5. 查询层对齐策略

### 5.1 设计原则

**存储层独立，查询时对齐**：
- 每个资产按各自的交易日历存储
- 查询时根据分析需求选择对齐策略

### 5.2 对齐策略实现

```python
from enum import Enum
from typing import Literal

import polars as pl


class AlignMethod(str, Enum):
    """多资产数据对齐策略"""

    INTERSECTION = "intersection"  # 交集：只保留共同交易日
    UNION_FFill = "union_ffill"    # 并集 + 前值填充
    UNION_NULL = "union_null"       # 并集 + 保留空值


def align_multi_asset_data(
    dfs: dict[str, pl.DataFrame],
    method: AlignMethod = AlignMethod.UNION_FFill,
    date_col: str = "trade_date_utc",
) -> pl.DataFrame:
    """
    对齐多资产日线数据.

    Args:
        dfs: {资产名: DataFrame} 字典
        method: 对齐策略
        date_col: 时间戳列名（用于对齐）

    Returns:
        对齐后的合并 DataFrame

    """
    # 收集所有时间戳
    all_timestamps = set()
    for df in dfs.values():
        all_timestamps.update(df[date_col].to_list())

    # 创建完整时间索引
    full_index = sorted(all_timestamps)

    aligned_dfs = []
    for name, df in dfs.items():
        if method == AlignMethod.INTERSECTION:
            # 交集：只保留共同时间点
            common = df.filter(pl.col(date_col).is_in(full_index))
            aligned_dfs.append(common.sort(date_col))

        elif method == AlignMethod.UNION_FFill:
            # 并集 + 前值填充
            # 创建完整时间序列并连接
            full_df = pl.DataFrame({date_col: full_index})
            aligned = full_df.join(df, on=date_col, how="left")
            # 前值填充（排除时间戳列）
            fill_cols = [c for c in aligned.columns if c != date_col]
            aligned = aligned.with_columns([
                pl.col(c).forward_fill().alias(c) for c in fill_cols
            ])
            aligned_dfs.append(aligned)

        else:  # UNION_NULL
            full_df = pl.DataFrame({date_col: full_index})
            aligned = full_df.join(df, on=date_col, how="left")
            aligned_dfs.append(aligned)

    # 横向合并所有资产
    # ... 实现细节省略

    return pl.concat(aligned_dfs, how="horizontal")
```

### 5.3 对齐策略选择指南

| 使用场景 | 推荐策略 | 原因 |
|---------|---------|------|
| 相关性分析 | `INTERSECTION` | 避免填充数据干扰统计 |
| 回测（严格） | `INTERSECTION` | 确保信号有效 |
| 日常 PnL | `UNION_FFill` | 休市日持仓不变 |
| 风险指标 | `UNION_FFill` | 连续序列便于计算 |
| 数据审计 | `UNION_NULL` | 明确显示缺失 |

---

## 6. 外汇结算日处理

### 6.1 T+2 规则说明

外汇现货交易采用 T+2 结算：
- **Trade Date (T)**：交易日
- **Value Date (T+2)**：资金交割日（交易日后 2 个工作日）

### 6.2 应用层计算

结算日在**应用层**按需计算，不存储：

```python
from datetime import date, timedelta


def calculate_fx_settlement_date(
    trade_date: date,
    base_currency: str,
    quote_currency: str,
    calendars: dict[str, set[date]],
) -> date:
    """
    计算外汇结算日（T+2）.

    Args:
        trade_date: 交易日期
        base_currency: 基础货币（ISO 4217）
        quote_currency: 报价货币（ISO 4217）
        calendars: {货币代码: 该国工作日集合}

    Returns:
        结算日期

    Note:
        - USD/CAD 使用 T+1
        - 结算日必须是双边货币国家的共同工作日

    """
    # 特殊处理：USD/CAD 使用 T+1
    if {base_currency, quote_currency} == {"USD", "CAD"}:
        offset = 1
    else:
        offset = 2

    # 获取双边工作日日历
    base_calendar = calendars.get(base_currency, set())
    quote_calendar = calendars.get(quote_currency, set())
    valid_days = base_calendar & quote_calendar  # 交集

    # 向前推进 offset 个工作日
    current = trade_date
    days_added = 0
    while days_added < offset:
        current += timedelta(days=1)
        if current.weekday() < 5 and current in valid_days:  # 工作日 + 在日历中
            days_added += 1

    return current
```

---

## 7. 交易日历管理

### 7.1 日历来源

| 市场 | 数据源 | 更新频率 |
|------|--------|---------|
| A股 | Tushare/AkShare | 每年更新 |
| 美股 | exchange_calendars | 每年更新 |
| 外汇 | 周一至周五（排除主要假期） | 静态规则 |
| LME | exchange_calendars | 每年更新 |
| CME | exchange_calendars | 每年更新 |

### 7.2 日历缓存策略

```python
from datetime import date
from functools import lru_cache


class TradingCalendarRegistry:
    """交易日历注册表"""

    def __init__(self) -> None:
        self._calendars: dict[str, set[date]] = {}

    def load_calendar(self, market: str, year: int) -> set[date]:
        """加载指定市场的交易日历"""
        if market not in self._calendars:
            self._calendars[market] = self._fetch_calendar(market, year)
        return self._calendars[market]

    def _fetch_calendar(self, market: str, year: int) -> set[date]:
        """从数据源获取交易日历"""
        if market == "SSE":
            # 使用 Tushare/AkShare
            ...
        elif market in ("NYSE", "LME", "CME"):
            # 使用 exchange_calendars 库
            ...
        elif market == "FX":
            # 外汇：周一至周五，排除主要假期
            ...
        return set()

    @lru_cache(maxsize=1024)
    def is_trading_day(self, market: str, check_date: date) -> bool:
        """检查是否为交易日（带缓存）"""
        calendar = self.load_calendar(market, check_date.year)
        return check_date in calendar
```

---

## 8. 完整数据流

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           完整数据流                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [数据源]                                                               │
│    Tushare (A股/外汇)  │  FRED (商品/宏观)  │  其他                      │
│         │                     │                    │                    │
│         ▼                     ▼                    ▼                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      摄取层 (Ingestion)                          │   │
│  │  • 次日批量拉取                                                   │   │
│  │  • 本地日期 → UTC 时间戳转换                                      │   │
│  │  • Schema 验证                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      存储层 (Store)                              │   │
│  │  • Parquet 格式，年分区                                          │   │
│  │  • 各资产独立交易日历                                             │   │
│  │  • key: (instrument_id, trade_date)                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      查询层 (Query)                              │   │
│  │  • 按日期范围/标的筛选                                            │   │
│  │  • 多资产对齐（交集/并集+填充）                                    │   │
│  │  • 时区转换（UTC → 本地）                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      应用层 (Application)                        │   │
│  │  • 回测引擎                                                       │   │
│  │  • 风险分析                                                       │   │
│  │  • 结算日计算（外汇 T+2）                                         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 9. 实施建议

### 9.1 Schema 变更

1. 扩展 `fx_schemas.py` 和 `commodity_schemas.py`，添加 `trade_date_utc` 字段
2. 更新 Adapter 层，在摄取时生成 UTC 时间戳
3. 保持向后兼容：`trade_date_utc` 可为可选字段

### 9.2 新增组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `TradingCalendarRegistry` | `datahub/runtime/` | 交易日历管理 |
| `DataAligner` | `datahub/services/` | 多资产数据对齐 |
| `utc_timestamp()` | `datahub/helpers/` | UTC 时间戳转换工具 |

### 9.3 测试要点

- [ ] UTC 时间戳转换正确性（夏令时/冬令时）
- [ ] 跨年数据分区
- [ ] 多资产对齐策略
- [ ] 外汇 T+2 结算日计算
- [ ] 交易日历边界（假期前后）

---

## 参考资料

- [量化数据库设计](https://www.cnblogs.com/LazyTiming/p/15118712.html)
- [多资产数据对齐指南](https://m.toutiao.com/article/7087890675064111627/)
- [DolphinDB 交易日历](https://blog.csdn.net/qq_41996852/article/details/146975486)
- [FX T+2 结算规则](https://www.investopedia.com/terms/f/forex-spot-rate.asp)

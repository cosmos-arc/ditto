# DataHub 数据集字段映射详细说明

> 生成时间: 2026-01-23
> 目的: 展示从 Tushare API 到 DataFrame 再到存储的完整转换链路

## 数据流转路径

```
Tushare API → Transformer → Enrichment → Store → Parquet/SQLite
```

| 阶段 | 说明 | 关键操作 |
|------|------|----------|
| **Tushare API** | 原始 API 字段 | `ts_code`, `trade_date`, `open`, `high`, `low`, `close` |
| **Transformer** | 列重命名、类型转换 | `ts_code` → `src_code`, `vol` → `volume` |
| **Enrichment** | SID 解析、source 添加 | 添加 `sid`, `source` 列 |
| **Store** | 最终存储 | Parquet 文件或 SQLite 表 |

---

## 1. stock_daily（股票日线行情）

### 存储结构
- **文件路径**: `data_root/stock_daily/{year}.parquet`
- **键列**: `(sid, trade_date, source)`

### 字段映射表

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| sid | 证券内部标识符 | int32 | sid | - | 通过 `securities.resolve_or_create_batch(src_code)` 解析得到 |
| trade_date | 交易日期 | date | trade_date | trade_date | 字符串转日期（格式 `%Y%m%d`） |
| source | 数据源标识 | string | source | - | 固定值 `"tushare"`，在 Enrichment 阶段添加 |
| src_code | 数据源原始代码 | string | src_code | ts_code | 重命名：`ts_code` → `src_code` |
| open | 开盘价 | float64 | open | open | 直接转换，保留 null |
| high | 最高价 | float64 | high | high | 直接转换，保留 null |
| low | 最低价 | float64 | low | low | 直接转换，保留 null |
| close | 收盘价 | float64 | close | close | 直接转换，保留 null |
| pre_close | 昨收价 | float64 | pre_close | pre_close | 直接转换，保留 null |
| volume | 成交量（手） | float64 | volume | vol | 重命名：`vol` → `volume` |
| amount | 成交额（元） | float64 | amount | amount | 直接转换，保留 null |
| pct_change | 涨跌幅（%） | float64 | pct_change | pct_chg | 重命名：`pct_chg` → `pct_change` |
| turnover | 换手率（%） | float64 | turnover | - | 待实现（当前未从 Tushare 获取） |
| is_suspended | 是否停牌 | boolean | is_suspended | - | 通过 `enrich_with_status` 从 stock_status 合并 |
| suspend_timing | 停牌时机 | string | suspend_timing | suspend_timing | 从 stock_status 合并，值：`"开盘停牌"/"盘中停牌"/"复盘"` |
| is_st | 是否 ST 股 | boolean | is_st | - | 通过 `enrich_with_status` 从 stock_status 合并 |
| st_type | ST 类型 | string | st_type | name | 从 stock_status 合并，值：`"ST"/"*ST"/"SST"` 等 |
| list_status | 上市状态 | string | list_status | list_status | 从 stock_basic 合并，值：`"L"`上市/`"D"`退市/`"P"`暂停 |
| is_limit_up | 是否涨停 | boolean | is_limit_up | - | 计算字段：`close == up_limit` |
| is_limit_down | 是否跌停 | boolean | is_limit_down | - | 计算字段：`close == down_limit` |
| up_limit | 涨停价 | float64 | up_limit | up_limit | 从 `fetch_stock_limit` 合并 |
| down_limit | 跌停价 | float64 | down_limit | down_limit | 从 `fetch_stock_limit` 合并 |

### API 调用
```python
# Tushare API: daily
fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg"
```

---

## 2. adj_factor（复权因子）

### 存储结构
- **文件路径**: `data_root/adj_factor/{year}.parquet`
- **键列**: `(sid, trade_date)` ⚠️ 需改为包含 source

### 字段映射表

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| sid | 证券内部标识符 | int32 | sid | - | 通过 `securities.resolve_or_create_batch(src_code)` 解析得到 |
| trade_date | 交易日期 | date | trade_date | trade_date | 字符串转日期（格式 `%Y%m%d`） |
| source | 数据源标识 | string | source | - | 固定值 `"tushare"` |
| src_code | 数据源原始代码 | string | src_code | ts_code | 重命名：`ts_code` → `src_code` |
| adj_factor | 复权因子 | float64 | adj_factor | adj_factor | 直接转换，用于计算复权价格 |
| knowledge_date | 知识生效日期 | date | knowledge_date | - | **计算列**：复制 `trade_date` 值（PIT 安全：数据即日可用） |

### 复权计算说明
- **前复权**：复权价格 = 原始价格 × 当日复权因子
- **后复权**：复权价格 = 原始价格 × 最新复权因子 / 当日复权因子

### API 调用
```python
# Tushare API: adj_factor
fields="ts_code,trade_date,adj_factor"
```

---

## 3. stock_status（股票状态）

### 存储结构
- **文件路径**: `data_root/stock_status/{year}.parquet`
- **键列**: `(sid, trade_date)`

### 字段映射表

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| sid | 证券内部标识符 | int32 | sid | - | 通过 `securities.resolve_or_create_batch(src_code)` 解析得到 |
| trade_date | 交易日期 | date | trade_date | - | 从参数传入，字符串转日期 |
| is_suspended | 是否停牌 | boolean | is_suspended | - | **合并字段**：从 `suspend_d` API 计算得到（有 suspend_timing 则为 True） |
| suspend_timing | 停牌时机 | string | suspend_timing | suspend_timing | 从 `suspend_d` API 获取，空值填充为 `""` |
| is_st | 是否 ST 股 | boolean | is_st | - | **合并字段**：从 `stock_st` API 计算得到（有 st_type 则为 True） |
| st_type | ST 类型 | string | st_type | name | 从 `stock_st` API 获取，重命名 `name` → `st_type` |
| list_status | 上市状态 | string | list_status | list_status | 从 `stock_basic` API 获取，空值填充为 `"L"` |
| source | 数据源标识 | string | source | - | 固定值 `"tushare"` |
| src_code | 数据源原始代码 | string | src_code | ts_code | 重命名：`ts_code` → `src_code` |

### API 调用（合并 3 个接口）
```python
# 1. suspend_d（停牌数据）
fields="ts_code,suspend_timing"

# 2. stock_st（ST 股票）
fields="ts_code,name"

# 3. stock_basic（基本信息）
fields="ts_code,list_status"
```

---

## 4. security（证券主数据）

### 存储结构
- **表名**: `securities`（SQLite，主表）
- **表名**: `security_mapping`（SQLite，PIT 支持）

### 字段映射表

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| sid | 证券内部标识符 | int32 | sid | - | **自动分配**：根据 `asset_class` 从范围池分配，stock 为 1_000_000-1_999_999 |
| src_code | 数据源原始代码 | string | src_code | ts_code | 重命名：`ts_code` → `src_code` |
| symbol | 证券代码（展示用） | string | symbol | symbol | 直接使用，如 `600000` |
| name | 证券名称 | string | name | name | 直接使用，如 `平安银行` |
| exchange | 交易所 | string | exchange | exchange | 直接使用，值：`SSE`上交所/`SZSE`深交所 |
| asset_class | 资产类别 | string | asset_class | - | 固定值 `"stock"`，可选：`stock`/`etf`/`index` |
| list_date | 上市日期 | date | list_date | list_date | 字符串转日期（格式 `%Y%m%d`） |
| delist_date | 退市日期 | date | delist_date | - | 待实现 |
| is_active | 是否活跃 | boolean | is_active | - | 计算字段：`delist_date IS NULL` |
| is_st | 是否 ST 股 | boolean | is_st | - | 从 stock_st 合并 |
| display_name | 展示名称 | string | display_name | - | 计算字段：`{name}({symbol})` |
| source | 数据源标识 | string | source | - | 固定值 `"tushare"` |

### security_mapping 表（PIT 支持）
| df 列 | 含义 | 类型 | 说明 |
|-------|------|------|------|
| sid | 证券内部标识符 | int32 | 外键关联 securities 表 |
| source | 数据源标识 | string | 数据源名称，如 `tushare` |
| src_code | 数据源原始代码 | string | 该数据源的原始代码 |
| effective_from | 生效开始日期 | date | 映射关系开始日期 |
| effective_to | 生效结束日期 | date | 映射关系结束日期，NULL 表示当前有效 |
| is_primary | 是否主标识符 | boolean | 是否优先使用该映射 |

### API 调用
```python
# Tushare API: stock_basic
fields="ts_code,symbol,name,exchange,list_date"
list_status="L"  # 只获取上市股票
```

---

## 5. etf_daily（ETF 日线行情）

### 存储结构
- **文件路径**: `data_root/etf_daily/{year}.parquet`
- **键列**: `(sid, trade_date, source)`

### 字段映射表

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| sid | 证券内部标识符 | int32 | sid | - | 解析得到，范围 2_000_000-2_999_999 |
| trade_date | 交易日期 | date | trade_date | trade_date | 字符串转日期（格式 `%Y%m%d`） |
| source | 数据源标识 | string | source | - | 固定值 `"tushare"` |
| src_code | 数据源原始代码 | string | src_code | ts_code | 重命名：`ts_code` → `src_code` |
| open | 开盘价 | float64 | open | open | 直接转换 |
| high | 最高价 | float64 | high | high | 直接转换 |
| low | 最低价 | float64 | low | low | 直接转换 |
| close | 收盘价 | float64 | close | close | 直接转换 |
| pre_close | 昨收价 | float64 | pre_close | pre_close | 直接转换 |
| volume | 成交量（手） | float64 | volume | vol | 重命名：`vol` → `volume` |
| amount | 成交额（元） | float64 | amount | amount | 直接转换 |
| pct_change | 涨跌幅（%） | float64 | pct_change | pct_chg | 重命名：`pct_chg` → `pct_change` |

### API 调用
```python
# Tushare API: fund_daily
fields="ts_code,trade_date,open,high,low,close,pre_close,vol,amount,pct_chg"
```

---

## 6. fund_adj（ETF/基金复权因子）

### 存储结构
- **文件路径**: `data_root/fund_adj/{year}.parquet`
- **键列**: `(sid, trade_date)` ⚠️ 需改为包含 source

### 字段映射表

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| sid | 证券内部标识符 | int32 | sid | - | 解析得到 |
| trade_date | 交易日期 | date | trade_date | trade_date | 字符串转日期（格式 `%Y%m%d`） |
| source | 数据源标识 | string | source | - | 固定值 `"tushare"` |
| src_code | 数据源原始代码 | string | src_code | ts_code | 重命名：`ts_code` → `src_code` |
| adj_factor | 复权因子 | float64 | adj_factor | adj_factor | 直接转换 |
| knowledge_date | 知识生效日期 | date | knowledge_date | - | **计算列**：复制 `trade_date` 值（PIT 安全） |

### API 调用
```python
# Tushare API: fund_adj
fields="ts_code,trade_date,adj_factor"
```

---

## 7. etf_basic（ETF 基本信息）

### 存储结构
- **表名**: `securities`（SQLite）
- **表名**: `security_mapping`（SQLite）

### 字段映射表

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| sid | 证券内部标识符 | int32 | sid | - | **自动分配**：范围 2_000_000-2_999_999 |
| src_code | 数据源原始代码 | string | src_code | ts_code | 重命名：`ts_code` → `src_code`，如 `510300.SH` |
| symbol | 证券代码（展示用） | string | symbol | - | **计算列**：从 `src_code` 提取，如 `510300.SH` → `510300` |
| name | 基金名称 | string | name | name | 直接使用 |
| exchange | 交易所 | string | exchange | - | **计算列**：从 `src_code` 提取并转换，`SH`→`SSE`, `SZ`→`SZSE` |
| asset_class | 资产类别 | string | asset_class | - | 固定值 `"etf"` |
| list_date | 上市日期 | date | list_date | list_date | 字符串转日期（格式 `%Y%m%d`） |
| source | 数据源标识 | string | source | - | 固定值 `"tushare"` |

### 计算列逻辑
```python
# symbol: 从 src_code 提取点号前的部分
symbol = src_code.split(".")[0]  # "510300.SH" → "510300"

# exchange: 转换交易所代码
exchange = {"SH": "SSE", "SZ": "SZSE"}.get(src_code.split(".")[1])
```

### API 调用
```python
# Tushare API: fund_basic
fields="ts_code,name,list_date"
```

---

## 8. calendar（交易日历）

### 存储结构
- **表名**: `trading_calendar`（SQLite）
- **缓存**: 全部加载到内存（~7500 条记录，~1MB）

### 字段映射表

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| trade_date | 交易日期 | date | trade_date | cal_date | 重命名：`cal_date` → `trade_date`，字符串转日期 |
| is_open | 是否开市 | boolean | is_open | is_open | 整数 0/1 转换为 Boolean |
| prev_trade_date | 前一交易日 | date | prev_trade_date | - | **计算字段**：查找上一个 `is_open=True` 的日期 |
| next_trade_date | 后一交易日 | date | next_trade_date | - | **计算字段**：查找下一个 `is_open=True` 的日期 |
| week_of_year | 年内周数 | int | week_of_year | - | **计算字段**：从 date 计算，范围 1-53 |
| month | 月份 | int | month | - | **计算字段**：从 date 计算，范围 1-12 |
| quarter | 季度 | int | quarter | - | **计算字段**：从 date 计算，范围 1-4 |
| year | 年份 | int | year | - | **计算字段**：从 date 计算 |
| is_week_end | 是否周末 | boolean | is_week_end | - | **计算字段**：判断是否为周日（weekday=6） |
| is_month_end | 是否月末 | boolean | is_month_end | - | **计算字段**：判断是否为月内最后一个交易日 |
| is_quarter_end | 是否季末 | boolean | is_quarter_end | - | **计算字段**：判断是否为季内最后一个交易日 |

### API 调用
```python
# Tushare API: trade_cal
fields="cal_date,is_open"
exchange="SSE"  # 上交所日历
```

---

## 9. stock_limit（涨跌停价格）

### 说明
此数据集不单独存储，而是**合并到 `stock_daily`** 中作为扩展列。

### 字段映射表

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| src_code | 数据源原始代码 | string | - | ts_code | 重命名：`ts_code` → `src_code` |
| trade_date | 交易日期 | date | - | trade_date | 字符串转日期（格式 `%Y%m%d`） |
| up_limit | 涨停价 | float64 | up_limit | up_limit | 直接转换，合并到 stock_daily |
| down_limit | 跌停价 | float64 | down_limit | down_limit | 直接转换，合并到 stock_daily |

### 涨跌停计算规则
- **主板**：±10%
- **科创板/创业板**：±20%
- **ST 股**：±5%
- **新股**：前 5 日无涨跌幅限制

### API 调用
```python
# Tushare API: stk_limit
fields="ts_code,trade_date,up_limit,down_limit"
```

---

## 待实现数据集

### index_weight（指数权重）

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| index_sid | 指数内部标识符 | int32 | index_sid | - | 待实现：从 index_code 解析 |
| con_sid | 成分股内部标识符 | int32 | con_sid | - | 待实现：从 con_code 解析 |
| trade_date | 交易日期 | date | trade_date | trade_date | 待实现 |
| weight | 权重（%） | float64 | weight | weight | 待实现 |
| source | 数据源标识 | string | source | - | 固定值 `"tushare"` |
| index_code | 指数代码 | string | index_code | index_code | 待实现，如 `000300.SH` |
| con_code | 成分股代码 | string | con_code | con_code | 待实现，如 `600000.SH` |

### universe_constituent（标的池成分股）

| df 列 | 含义 | 类型 | 存储列 | tushare 字段 | 加工逻辑 |
|-------|------|------|--------|-------------|----------|
| universe_id | 标的池标识符 | string | universe_id | - | 自定义标识符，如 `csi300` |
| sid | 成分股内部标识符 | int32 | sid | - | 待实现：从 code 解析 |
| source | 数据源标识 | string | source | - | 固定值 `"tushare"` |
| src_code | 数据源原始代码 | string | src_code | con_code | 待实现 |
| effective_from | 生效开始日期 | date | effective_from | - | 待实现（PIT 支持） |
| effective_to | 生效结束日期 | date | effective_to | - | 待实现（PIT 支持，NULL 表示当前有效） |
| weight | 权重 | float64 | weight | weight | 待实现 |

---

## 关键技术细节

### SID 分配范围
```python
# packages/data/src/ditto_data/models/common.py
stock: (1_000_000, 1_999_999)  # 股票
etf:   (2_000_000, 2_999_999)  # ETF/基金
index: (3_000_000, 3_999_999)  # 指数
```

### Transformer 配置示例
```python
# packages/data/src/ditto_data/sources/tushare/processors/transformer.py
DAILY_OHLCV_MAPPING = ColumnMapping(
    rename={"ts_code": "src_code", "vol": "volume", "pct_chg": "pct_change"},
    date_columns={"trade_date": "%Y%m%d"},
    float_columns=["open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change"],
    output_columns=("src_code", "trade_date", "open", "high", "low", "close",
                   "pre_close", "volume", "amount", "pct_change")
)
```

### Enrichment 流程
```python
# packages/data/src/ditto_data/accessors/internal/enrichment.py
def enrich_with_sid(df, sid_mapping, src_code_col, source):
    """添加 sid 和 source 列"""
    return df.with_columns(
        pl.Series([sid_mapping.get(code) for code in df[src_code_col]]).alias("sid"),
        pl.lit(source).alias("source")
    )

def enrich_with_status(df, status_df, on=["sid", "trade_date"]):
    """添加状态列"""
    return df.join(status_df, on=on, how="left").fill_null(defaults)
```

### PIT（Point-in-Time）查询
```python
# security_mapping 表查询逻辑
SELECT sid FROM security_mapping
WHERE source = 'tushare' AND src_code = '600000.SH'
  AND effective_from <= '2024-01-15'
  AND (effective_to IS NULL OR effective_to > '2024-01-15')
ORDER BY effective_from DESC
LIMIT 1
```

---

## 相关文件

| 组件 | 路径 |
|------|------|
| Schema 定义 | `packages/data/src/ditto_data/meta/schemas.py` |
| Transformer 配置 | `packages/data/src/ditto_data/sources/tushare/processors/transformer.py` |
| Stock Adapter | `packages/data/src/ditto_data/sources/tushare/adapters/stock.py` |
| ETF Adapter | `packages/data/src/ditto_data/sources/tushare/adapters/etf.py` |
| Calendar Adapter | `packages/data/src/ditto_data/sources/tushare/adapters/calendar.py` |
| Status Merger | `packages/data/src/ditto_data/sources/tushare/processors/merger.py` |
| Enrichment | `packages/data/src/ditto_data/accessors/internal/enrichment.py` |
| Data Writer | `apps/port/src/ditto_port/services/ingestion/data_writer.py` |

# V1 数据就绪度审计报告

- 审计日期: 2026-04-11
- 审计范围: V1 Enhancement Batch 1 所需数据链路

## 审计结果

| # | 数据项 | 状态 | 说明 |
|---|--------|------|------|
| 1 | ETF 日线数据 | **就绪** | Tushare 数据源 + Parquet 存储 + 完整 DQ 规则 |
| 2 | 因子列 | **就绪** | 表达式编译器支持 `market.*` 和 `fundamentals.*`，内置因子库覆盖技术/基本面/Alpha |
| 3 | Universe (CSI300/500) | **就绪** | UniverseService + IndexCompositionReader PIT 查询 |
| 4 | Regime 指标 | **就绪** | MA/volatility 底层列均有数据支持 |
| 5 | 基准数据 | **就绪** | 指数日线存储 + DataFeed 基准消费 |
| 6 | 行业分类 | **就绪** | 申万(L1/L2/L3) + 证监会双来源，PIT 支持 |

## 详细说明

### 1. ETF 日线数据

- 数据源: `ETFTushareAdapter.fetch_etf_daily()`
- Schema: `ETF_DAILY_SOURCE_SCHEMA` — open/high/low/close/volume/amount/pct_change + knowledge_date
- 存储: `market/etf/bars/` 年度分区 Parquet，CQRS 读写分离
- DQ 规则: `config/default/dq_rules/etf_daily.yml`（技术+业务+统计 3 类检查）
- 摄入: 已在 `SUPPORTED_INSTRUMENT_DATASETS` 中注册

### 2. 因子列

- 表达式引擎: `dataset.column` 格式列引用（`ColumnRefNode`），AST 解析 + 语义分析 + Polars 代码生成
- 覆盖列: `market.close/open/high/low/volume` + `fundamentals.*`（EPS/BPS/营收/负债/净利润/权益/营收）
- 内置因子: `primitives.py`(returns_1/prev_close/tr) + `technical.py`(ma/ema/rsi/macd/atr/bbands/volatility) + `alpha.py`(momentum/reversal/value/quality/liquidity)

### 3. Universe

- `UniverseService.get_universe(universe_id, asof)` — 成分查询
- `sync_index_universe(index_code, asof_date)` — 从指数数据同步
- `IndexCompositionReader` — SQLite PIT 查询
- CSI300 (`000300.SH`) 在默认列表中

### 4. Regime 指标

- `MA_CROSS`: 依赖 `ma_short`/`ma_long` 列 → 内置因子 `ma_N`
- `VOLATILITY_THRESHOLD`: 依赖 `volatility` 列 → 内置因子 `volatility_20`
- 底层数据: `market.close`，在 ETF/Stock 日线 schema 中完整覆盖

### 5. 基准数据

- 数据源: `IndexTushareAdapter.fetch_daily()`
- 存储: `IndexBarsReader` → `market/index/bars/` 年度分区 Parquet
- 消费: `ProviderBackedDataFeed.get_slice()` 提取 `benchmark_close`
- 解析: `resolve_benchmark()` 从 StrategySpec.benchmark 解析
- 默认基准: `"000300.SH"` (沪深300)

### 6. 行业分类

- 数据源: `IndustryTushareAdapter` — 申万(L1/L2/L3) + 证监会
- 存储: SQLite CQRS — `IndustryReader` + `IndustryMappingReader`（PIT 查询）
- 策略集成: `stock_sector_rotation` 模板使用 `sector_id`/`is_sector` 列

## 待补项

无硬性缺失。中证500指数代码 `000905.SH` 未在 `MARKET_INDEX_CODES` 默认列表中，需在摄取时手动指定或加入列表。

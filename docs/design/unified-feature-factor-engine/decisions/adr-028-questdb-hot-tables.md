# ADR-028: QuestDB 热表与物化视图 DDL

**状态**: 已决策（2026-03-10）

---

## 背景

QuestDB 作为盘中热层，需要明确：
1. 哪些表需要存储（热表设计）
2. 数据保留多久（TTL 策略）
3. 哪些聚合可以预计算（物化视图）

根据核心原则"热层只存够用的 lookback"，热表不做全量镜像，只保留业务所需的回看窗口。

> **2026-03-13 对齐说明**: 默认 TTL 口径已由 [ADR-040](adr-040-hot-cold-retention-state-namespace-policy.md) 收敛。本文中的 QuestDB 热表与视图默认归入 `intraday_hot` profile；长 TTL 仅作为 benchmark profile 示例，不再视为默认值。

---

## 热表设计总览

| 表名 | 数据类型 | 分区 | TTL | 说明 |
|------|---------|------|-----|------|
| `bar_1m_hot` | 分钟 K 线 | `DAY` | 5 天 | `intraday_hot` 默认 profile |
| `bar_5m_mv` | 5 分钟聚合 | `MONTH` | 5 天 | 从 1m 聚合，物化视图 |
| `bar_15m_mv` | 15 分钟聚合 | `MONTH` | 5 天 | 从 1m 聚合，物化视图 |
| `bar_60m_mv` | 60 分钟聚合 | `MONTH` | 5 天 | 从 1m 聚合，物化视图 |
| `lob_5s_hot` | 5 秒盘口摘要 | `DAY` | 5 天 | `intraday_hot` 默认 profile |
| `lob_1m_mv` | 1 分钟盘口摘要 | `MONTH` | 5 天 | 从 5s 聚合，物化视图 |
| `lob_1s_hot` | 1 秒盘口摘要 | `DAY` | 5 天 | 仅重点标的（可选） |
| `f_1m_hot` | 热点分钟因子 | `DAY` | 5 天 | A 类因子热序列 |

---

## DDL 定义

### 1. 分钟 K 线热表（bar_1m_hot）

```sql
-- 分钟 K 线热表
CREATE TABLE IF NOT EXISTS bar_1m_hot (
    symbol SYMBOL INDEX,
    instrument_id SYMBOL INDEX,
    trade_date DATE,
    trade_time TIMESTAMP,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    amount DOUBLE,
    vwap DOUBLE,
    trades INT,
    ts TIMESTAMP TIME INDEX,
    PRIMARY KEY (instrument_id, trade_date)
) TIMESTAMP(ts) PARTITION BY DAY;

-- TTL 配置（intraday_hot: 5 天）
ALTER TABLE bar_1m_hot SET TTL 5 DAYS;
```

### 2. 分钟聚合物化视图

```sql
-- 5 分钟聚合
CREATE MATERIALIZED VIEW IF NOT EXISTS bar_5m_mv AS
SELECT
    symbol,
    instrument_id,
    trade_date,
    date_trunc('hour', ts) + INTERVAL '5' MINUTE * FLOOR(EXTRACT(MINUTE FROM ts) / 5) AS bar_time,
    FIRST(open) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close) AS close,
    SUM(volume) AS volume,
    SUM(amount) AS amount,
    SUM(amount) / NULLIF(SUM(volume), 0) AS vwap,
    SUM(trades) AS trades
FROM bar_1m_hot
SAMPLE BY 5m;

-- TTL 配置（默认 5 天）
-- 注：物化视图默认与 intraday_hot profile 对齐；长 TTL 仅用于 benchmark profile

-- 15 分钟聚合
CREATE MATERIALIZED VIEW IF NOT EXISTS bar_15m_mv AS
SELECT
    symbol,
    instrument_id,
    trade_date,
    date_trunc('hour', ts) + INTERVAL '15' MINUTE * FLOOR(EXTRACT(MINUTE FROM ts) / 15) AS bar_time,
    FIRST(open) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close) AS close,
    SUM(volume) AS volume,
    SUM(amount) AS amount,
    SUM(amount) / NULLIF(SUM(volume), 0) AS vwap,
    SUM(trades) AS trades
FROM bar_1m_hot
SAMPLE BY 15m;

-- 60 分钟聚合
CREATE MATERIALIZED VIEW IF NOT EXISTS bar_60m_mv AS
SELECT
    symbol,
    instrument_id,
    trade_date,
    date_trunc('hour', ts) AS bar_time,
    FIRST(open) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close) AS close,
    SUM(volume) AS volume,
    SUM(amount) AS amount,
    SUM(amount) / NULLIF(SUM(volume), 0) AS vwap,
    SUM(trades) AS trades
FROM bar_1m_hot
SAMPLE BY 1h;
```

### 3. 盘口热表（lob_5s_hot）

```sql
-- 5 秒盘口摘要
CREATE TABLE IF NOT EXISTS lob_5s_hot (
    symbol SYMBOL INDEX,
    instrument_id SYMBOL INDEX,
    trade_date DATE,
    snap_time TIMESTAMP,

    -- 第一档
    bid1_price DOUBLE,
    bid1_volume DOUBLE,
    ask1_price DOUBLE,
    ask1_volume DOUBLE,

    -- 前五档汇总
    bid5_volume_sum DOUBLE,
    ask5_volume_sum DOUBLE,

    -- 计算字段
    spread DOUBLE,               -- 价差
    mid DOUBLE,                  -- 中间价
    top1_imbalance DOUBLE,       -- 第一档不平衡
    top5_imbalance DOUBLE,       -- 前五档不平衡
    book_pressure_ratio DOUBLE,  -- 买卖压力比

    ts TIMESTAMP TIME INDEX,
    PRIMARY KEY (instrument_id, trade_date)
) TIMESTAMP(ts) PARTITION BY DAY;

-- TTL 配置（intraday_hot: 5 天）
ALTER TABLE lob_5s_hot SET TTL 5 DAYS;
```

### 4. 盘口分钟物化视图（lob_1m_mv）

```sql
-- 1 分钟盘口摘要（从 5s 聚合）
CREATE MATERIALIZED VIEW IF NOT EXISTS lob_1m_mv AS
SELECT
    symbol,
    instrument_id,
    trade_date,
    date_trunc('minute', ts) AS bar_time,

    -- 平均值
    AVG(spread) AS avg_spread,
    AVG(mid) AS avg_mid,
    AVG(top1_imbalance) AS avg_top1_imbalance,
    AVG(top5_imbalance) AS avg_top5_imbalance,
    AVG(book_pressure_ratio) AS avg_book_pressure,

    -- 极值
    MIN(spread) AS min_spread,
    MAX(spread) AS max_spread,
    MIN(top1_imbalance) AS min_top1_imbalance,
    MAX(top1_imbalance) AS max_top1_imbalance,

    -- 深度
    AVG(bid5_volume_sum) AS avg_bid5_depth,
    AVG(ask5_volume_sum) AS avg_ask5_depth

FROM lob_5s_hot
SAMPLE BY 1m;
```

### 5. 热点分钟因子表（f_1m_hot）

```sql
-- 热点分钟因子表（A 类因子）
CREATE TABLE IF NOT EXISTS f_1m_hot (
    factor_id SYMBOL INDEX,
    instrument_id SYMBOL INDEX,
    trade_date DATE,
    bar_time TIMESTAMP,

    -- 因子值
    raw_value DOUBLE,
    exposure DOUBLE,

    -- 元信息
    serve_mode SYMBOL,      -- SERIES/STATE/DERIVE/OFFLINE
    spec_hash SYMBOL,
    asof_ts TIMESTAMP,      -- 计算时间戳
    calc_ver INT,           -- 计算版本

    ts TIMESTAMP TIME INDEX,
    PRIMARY KEY (factor_id, instrument_id, trade_date)
) TIMESTAMP(ts) PARTITION BY DAY;

-- TTL 配置（intraday_hot: 5 天）
ALTER TABLE f_1m_hot SET TTL 5 DAYS;
```

### 6. 1 秒盘口热表（可选，仅重点标的）

```sql
-- 1 秒盘口摘要（仅重点标的）
CREATE TABLE IF NOT EXISTS lob_1s_hot (
    symbol SYMBOL INDEX,
    instrument_id SYMBOL INDEX,
    trade_date DATE,
    snap_time TIMESTAMP,

    spread DOUBLE,
    mid DOUBLE,
    top1_imbalance DOUBLE,

    ts TIMESTAMP TIME INDEX,
    PRIMARY KEY (instrument_id, trade_date)
) TIMESTAMP(ts) PARTITION BY DAY;

-- TTL 配置（5 天）
ALTER TABLE lob_1s_hot SET TTL 5 DAYS;
```

---

## TTL 策略详解

### 设计原则

1. **TTL 是配置参数，不是硬编码常量**
   - 通过 profile 配置统一管理
   - 不同环境（开发/测试/生产）可使用不同 profile

2. **TTL 与业务窗口匹配**
   - `intraday_hot` 默认 5 天，覆盖盘中 lookback 与短周期恢复窗口
   - 日线热数据统一由 `daily_hot` profile 管理，默认 30 天
   - 超出热层窗口的恢复由 Parquet 冷回放窗口或上游重放承担

3. **物化视图 TTL ≥ 基表 TTL**
   - 避免物化视图数据不完整

4. **长 TTL 只作为压测 profile**
   - `120/180/365 天` 可以保留给 benchmark / stress 环境
   - 默认规范值仍以 5 天 / 30 天 profile 为准

### TTL 配置模板

```conf
# deploy/derived/questdb/server.conf

# 默认 profile TTL（单位：天）
questdb.ttl.profile.intraday_hot=5
questdb.ttl.profile.daily_hot=30

# 可选 benchmark profile（非默认）
questdb.ttl.profile.benchmark.bar_1m_hot=120
questdb.ttl.profile.benchmark.bar_5m_mv=180
questdb.ttl.profile.benchmark.bar_15m_mv=180
questdb.ttl.profile.benchmark.bar_60m_mv=365
```

---

## 盘口因子窗口设计

盘口因子的典型使用场景：

| 窗口 | 用途 | 典型因子 |
|------|------|---------|
| **15 秒** | 极短执行/风控 | spread 扩张、扫单后恢复、进场过滤 |
| **60 秒** | 短时确认 | 平滑确认、过滤假信号 |
| **5 分钟** | 和 1m/5m K 线协同 | 盘口强弱与价量融合 |
| **15 分钟** | 背景分位/上下文 | 当前值相对历史分位判断异常 |

**首版盘口因子列表**：

| 因子 | 说明 | 窗口 |
|------|------|------|
| `spread` | bid-ask 价差 | 实时 |
| `mid` | 中间价 | 实时 |
| `top1_imbalance` | 第一档不平衡 | 实时 |
| `top5_imbalance` | 前五档不平衡 | 实时 |
| `top5_depth_sum` | 前五档深度和 | 实时 |
| `book_pressure_ratio` | 买卖压力比 | 实时 |
| `depth_slope_proxy` | 深度斜率代理 | 实时 |

---

## 索引策略

### SYMBOL 列索引

```sql
-- 高频查询列建立 SYMBOL INDEX
symbol SYMBOL INDEX,
instrument_id SYMBOL INDEX,
factor_id SYMBOL INDEX,
serve_mode SYMBOL INDEX,
```

**索引选择原则**：
- 高基数列（symbol, instrument_id）：必须索引
- 低基数列（serve_mode）：选择性索引
- 时间列（ts）：QuestDB 默认时间索引

### 查询优化示例

```sql
-- 高效查询：利用 SYMBOL INDEX + 时间索引
SELECT *
FROM bar_1m_hot
WHERE instrument_id = '000001.SZ'
  AND ts >= dateadd('h', -2, now());

-- 低效查询：全表扫描
SELECT *
FROM bar_1m_hot
WHERE volume > 1000000;  -- 无索引
```

---

## 数据写入路径

### ILP 高速写入

```python
# packages/datahub/src/ditto_datahub/stores/derived/questdb_writer.py

from questdb.ingress import Sender

class QuestDBWriter:
    def __init__(self, host: str, port: int = 9009):
        self.sender = Sender(host, port)

    async def write_bar_1m(self, bars: list[Bar]) -> None:
        """写入分钟 K 线"""
        for bar in bars:
            self.sender.row(
                'bar_1m_hot',
                symbols={
                    'symbol': bar.symbol,
                    'instrument_id': bar.instrument_id,
                },
                columns={
                    'trade_date': bar.trade_date.isoformat(),
                    'trade_time': bar.trade_time.isoformat(),
                    'open': bar.open,
                    'high': bar.high,
                    'low': bar.low,
                    'close': bar.close,
                    'volume': bar.volume,
                    'amount': bar.amount,
                    'vwap': bar.vwap,
                    'trades': bar.trades,
                },
                at=bar.ts
            )
        await self.sender.flush()

    async def write_factor(self, factors: list[FactorValue]) -> None:
        """写入热点因子"""
        for f in factors:
            self.sender.row(
                'f_1m_hot',
                symbols={
                    'factor_id': f.factor_id,
                    'instrument_id': f.instrument_id,
                    'serve_mode': f.serve_mode,
                    'spec_hash': f.spec_hash,
                },
                columns={
                    'trade_date': f.trade_date.isoformat(),
                    'bar_time': f.bar_time.isoformat(),
                    'raw_value': f.raw_value,
                    'exposure': f.exposure,
                    'asof_ts': f.asof_ts.isoformat(),
                    'calc_ver': f.calc_ver,
                },
                at=f.ts
            )
        await self.sender.flush()
```

---

## 回补机制

### 盘后批量回补

```python
# 盘后从 Parquet 回补 QuestDB
async def backfill_questdb_from_parquet(
    start_date: date,
    end_date: date,
) -> None:
    """从 Parquet 回补 QuestDB 热层"""

    # 1. 读取 Parquet 数据
    df = pl.read_parquet("data/market/cn/bar_1d/*.parquet").filter(
        pl.col("trade_date").is_between(start_date, end_date)
    )

    # 2. 转换并写入 QuestDB
    writer = QuestDBWriter(host="localhost", port=9009)
    await writer.write_bar_1m(df_to_bars(df))

    logger.info(f"Backfilled QuestDB: {start_date} to {end_date}")
```

### 定时回补调度

```python
# 每日盘前自动回补最近 N 天
@flow(name="questdb_daily_backfill")
async def daily_backfill_flow() -> None:
    """每日盘前回补 QuestDB"""

    # 回补最近 5 天（容错）
    end_date = date.today()
    start_date = end_date - timedelta(days=5)

    await backfill_questdb_from_parquet(start_date, end_date)
```

---

## 相关 ADR

- [ADR-020: 部署与运维设计](adr-020-deployment-ops.md) - QuestDB Docker 配置
- [ADR-023: 灾备恢复策略](adr-023-disaster-recovery.md) - 热层恢复策略
- [ADR-027: 表达式 Pushdown 策略](adr-027-pushdown-strategy.md) - 下推到 QuestDB
- [ADR-029: 盘中实时路径与盘后批量路径](adr-029-intraday-postmarket-paths.md) - 数据写入路径
- [ADR-030: Online Data Access Boundary](adr-030-online-data-access-boundary.md) - 在线查询边界

# Ditto 数据设计文档

**版本：v2.0 Final（Phase 0–1：ETF 行业轮动）**

**日期：2025-12-08**

---

## 1. 设计目标与范围

本数据设计文档用于回答：

> "Ditto 系统里，所有数据从哪里来、存到哪里、长成什么结构、如何保证质量？"

### 1.1 核心设计原则

1. **复权分离存储**：只存不复权价格 + 复权因子，运行时动态计算
2. **Point-in-Time (PIT) 安全**：所有因子和衍生数据必须有 `knowledge_date`
3. **数据版本化**：关键数据集有版本号，保证回测可复现
4. **双源校验**：Tushare 主力 + AkShare 校验，异常时标记而非静默使用

### 1.2 本版本覆盖范围

- **外部数据源**：Tushare Pro（主）、AkShare（备）
- **内部存储**：DuckDB（研究 & 因子 & 回测）+ SQLite（账本 & 状态）
- **核心表结构**：K 线（不复权）、复权因子、因子、Regime、轮动得分、回测结果、调仓计划、风控事件等
- **数据质量**：Sanity Check、双源交叉校验、**涨跌停状态**、**停牌状态**

---

## 2. 外部数据源与获取策略

### 2.1 数据源概览

**当前使用：**

| 数据源 | 角色 | 优点 | 限制 |
|--------|------|------|------|
| Tushare Pro | 主力 | 结构化良好、稳定、文档清晰 | 积分 & 调用频率 |
| AkShare | 校验 & 降级 | 免费、来源多样 | 部分字段质量不稳定 |

**未来预留：**

| 数据源 | 角色 | 阶段 |
|--------|------|------|
| MiniQMT / 券商 API | 实盘行情与交易 | Phase 2+ |
| 东方财富/同花顺 | 数据质量验证 | 手工抽查 |

### 2.2 Tushare Pro 使用策略

**订阅等级**：10000 积分

#### 2.2.1 核心接口

| 接口 | 用途 | 关键字段 |
|------|------|----------|
| `pro.fund_daily()` | ETF 日线行情 | ts_code, trade_date, open, high, low, close, vol, amount |
| `pro.fund_adj()` | **复权因子** | ts_code, trade_date, adj_factor |
| `pro.fund_basic()` | ETF 基本信息 | ts_code, name, fund_type, list_date |
| `pro.index_daily()` | 指数日线 | ts_code, trade_date, open, high, low, close |
| `pro.trade_cal()` | 交易日历 | cal_date, is_open |

#### 2.2.2 频率与配额控制

```python
class TushareRateLimiter:
    """Tushare 限流器"""
    
    def __init__(self, calls_per_minute: int = 180):
        self.calls_per_minute = calls_per_minute
        self.call_history: list[float] = []
    
    async def acquire(self) -> None:
        """获取调用许可"""
        now = time.time()
        # 清理 1 分钟前的记录
        self.call_history = [t for t in self.call_history if now - t < 60]
        
        if len(self.call_history) >= self.calls_per_minute:
            wait_time = 60 - (now - self.call_history[0])
            await asyncio.sleep(wait_time)
        
        self.call_history.append(time.time())
```

### 2.3 AkShare 使用策略

**目标角色**：永远的"第二意见医生"——只做校验 & 降级，不做主力

#### 2.3.1 校验场景

```python
class CrossSourceValidator:
    """双源交叉校验器"""
    
    PRICE_DIFF_THRESHOLD = 0.002  # 0.2%
    
    async def validate(
        self,
        symbol: str,
        trade_date: date,
        tushare_data: dict,
        akshare_data: dict
    ) -> ValidationResult:
        """交叉验证两个数据源"""
        
        ts_close = tushare_data["close"]
        ak_close = akshare_data["close"]
        
        price_diff = abs(ts_close - ak_close) / ts_close
        
        if price_diff > self.PRICE_DIFF_THRESHOLD:
            return ValidationResult(
                valid=False,
                severity="CRITICAL",
                message=f"Price diff {price_diff:.4%} exceeds threshold",
                action="MARK_SUSPICIOUS"  # 标记为可疑，禁止自动下单
            )
        
        return ValidationResult(valid=True)
```

#### 2.3.2 降级场景

```python
class DataFallbackStrategy:
    """数据源降级策略"""
    
    MAX_CONSECUTIVE_FAILURES = 3
    
    async def fetch_with_fallback(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> tuple[pl.DataFrame, str]:
        """带降级的数据获取
        
        Returns:
            (data, source): 数据和来源标识
        """
        # 1. 尝试主力源
        try:
            data = await self.tushare_client.fetch(symbol, start_date, end_date)
            self.failure_count["tushare"] = 0
            return data, "tushare"
        except Exception as e:
            self.failure_count["tushare"] += 1
            logger.error("tushare_fetch_failed", symbol=symbol, error=str(e))
        
        # 2. 连续失败 N 次后降级
        if self.failure_count["tushare"] >= self.MAX_CONSECUTIVE_FAILURES:
            logger.warning("degrading_to_akshare", symbol=symbol)
            try:
                data = await self.akshare_client.fetch(symbol, start_date, end_date)
                return data, "akshare"
            except Exception as e:
                logger.critical("all_sources_failed", symbol=symbol)
                raise DataSourceException("All data sources failed")
        
        raise DataSourceException("Primary source failed")
```

---

## 3. 内部数据模型与存储架构

### 3.1 总体存储策略

```
┌─────────────────────────────────────────────────────────────────┐
│                      DuckDB (warehouse.duckdb)                  │
│  - K线数据（不复权）                                            │
│  - 复权因子                                                     │
│  - 因子数据（带 knowledge_date）                                │
│  - Regime 数据                                                  │
│  - 轮动得分                                                     │
│  - 回测结果                                                     │
│  - Universe 历史                                                │
│  - 因子墓地                                                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      SQLite (trading.db)                        │
│  - 调仓计划                                                     │
│  - 模拟/实盘持仓                                                │
│  - 订单记录                                                     │
│  - 风控事件                                                     │
│  - 运行状态                                                     │
│  - 策略实例                                                     │
│  - 心跳记录                                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 数据版本与 Data Contract

```python
@dataclass
class DataContract:
    """数据契约 - 定义数据质量 SLO"""
    dataset_id: str
    version: str
    
    # 质量 SLO
    max_missing_days: int           # 最大允许缺失天数
    max_price_jump_pct: float       # 最大允许价格跳变
    cross_source_diff_threshold: float  # 双源价差阈值
    
    # 时效性 SLO
    max_staleness_hours: int        # 最大允许延迟小时数
    
    def check_violation(self, metrics: DataQualityMetrics) -> list[str]:
        """检查是否违反 SLO"""
        violations = []
        if metrics.missing_days > self.max_missing_days:
            violations.append(f"Missing days {metrics.missing_days} > {self.max_missing_days}")
        if metrics.max_price_jump > self.max_price_jump_pct:
            violations.append(f"Price jump {metrics.max_price_jump:.2%} > {self.max_price_jump_pct:.2%}")
        return violations

# 预定义的数据契约
ETF_DAILY_CONTRACT = DataContract(
    dataset_id="etf_daily",
    version="v1",
    max_missing_days=3,
    max_price_jump_pct=0.15,
    cross_source_diff_threshold=0.002,
    max_staleness_hours=36
)
```

---

## 4. DuckDB Schema 设计

### 4.1 数据库文件

- 路径：`data/warehouse.duckdb`
- 备份：`backups/warehouse_YYYYMMDD.duckdb`

### 4.2 表结构定义（DDL）

#### 4.2.1 ETF 基本信息表

```sql
CREATE TABLE IF NOT EXISTS etf_info (
    symbol         VARCHAR PRIMARY KEY,  -- 内部统一编码，如 '510300.SH'
    ts_code        VARCHAR,              -- Tushare 原始代码
    name           VARCHAR,
    fund_type      VARCHAR,              -- 如 '股票型', '指数型'
    list_date      DATE,
    delist_date    DATE,                 -- 退市日期（如有）
    fund_size      DECIMAL(15,2),        -- 最新规模（亿）
    expense_ratio  DECIMAL(8,4),
    category       VARCHAR,              -- 'core'/'growth'/'defensive'
    is_active      BOOLEAN DEFAULT TRUE,
    management     VARCHAR,
    benchmark      VARCHAR,              -- 跟踪指数名称
    last_updated   TIMESTAMP
);
```

#### 4.2.2 ETF 日线 K 线表（不复权）

```sql
-- 核心设计：只存不复权价格，复权在运行时计算
CREATE TABLE IF NOT EXISTS etf_kline_daily (
    symbol         VARCHAR,
    trade_date     DATE,
    open           DECIMAL(12,4),        -- 不复权开盘价
    high           DECIMAL(12,4),        -- 不复权最高价
    low            DECIMAL(12,4),        -- 不复权最低价
    close          DECIMAL(12,4),        -- 不复权收盘价
    prev_close     DECIMAL(12,4),        -- 前收盘价（用于涨跌停判断）
    volume         BIGINT,
    amount         DECIMAL(18,2),
    status         VARCHAR DEFAULT 'NORMAL',  -- 'NORMAL'/'SUSPENDED'/'LIMIT_UP'/'LIMIT_DOWN'
    source         VARCHAR,              -- 'tushare'/'akshare'
    is_suspicious  BOOLEAN DEFAULT FALSE, -- 双源校验异常标记
    ingest_batch   VARCHAR,
    last_updated   TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

-- 涨跌停状态索引
CREATE INDEX idx_kline_status ON etf_kline_daily(trade_date, status);
```

#### 4.2.3 复权因子表（关键！）

```sql
-- 复权因子独立存储，避免分红配股后重刷历史
CREATE TABLE IF NOT EXISTS etf_adj_factor (
    symbol         VARCHAR,
    trade_date     DATE,
    adj_factor     DECIMAL(10,6),        -- 复权因子
    source         VARCHAR,
    last_updated   TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);

-- 使用方式：后复权价 = 不复权价 * adj_factor
-- 前复权价 = 不复权价 * adj_factor / latest_adj_factor
```

#### 4.2.4 指数日线 K 线表

```sql
CREATE TABLE IF NOT EXISTS index_kline_daily (
    index_code     VARCHAR,
    trade_date     DATE,
    open           DECIMAL(12,4),
    high           DECIMAL(12,4),
    low            DECIMAL(12,4),
    close          DECIMAL(12,4),
    prev_close     DECIMAL(12,4),
    volume         BIGINT,
    amount         DECIMAL(18,2),
    last_updated   TIMESTAMP,
    PRIMARY KEY (index_code, trade_date)
);
```

#### 4.2.5 交易日历表

```sql
CREATE TABLE IF NOT EXISTS trading_calendar (
    trade_date     DATE PRIMARY KEY,
    is_open        BOOLEAN,
    market         VARCHAR DEFAULT 'CN',
    last_updated   TIMESTAMP
);
```

#### 4.2.6 Universe 历史表（消除幸存者偏差）

```sql
-- 记录 ETF 池的历史变更，用于回测时获取当期 Universe
CREATE TABLE IF NOT EXISTS etf_universe_history (
    effective_date DATE,
    symbol         VARCHAR,
    action         VARCHAR,              -- 'ADD' / 'REMOVE'
    reason         VARCHAR,              -- 变更原因
    PRIMARY KEY (effective_date, symbol, action)
);

-- 获取某日 Universe 的查询示例：
-- WITH adds AS (
--     SELECT symbol FROM etf_universe_history
--     WHERE effective_date <= $trade_date AND action = 'ADD'
-- ),
-- removes AS (
--     SELECT symbol FROM etf_universe_history
--     WHERE effective_date <= $trade_date AND action = 'REMOVE'
-- )
-- SELECT symbol FROM adds EXCEPT SELECT symbol FROM removes
```

#### 4.2.7 Regime 识别结果表

```sql
CREATE TABLE IF NOT EXISTS regime_daily (
    trade_date       DATE PRIMARY KEY,
    regime_type      VARCHAR,            -- 'bull'/'osc'/'bear'
    regime_score     DECIMAL(8,4),
    trend_score      DECIMAL(8,4),
    momentum_score   DECIMAL(8,4),
    volatility_score DECIMAL(8,4),
    width_score      DECIMAL(8,4),
    -- 自适应阈值
    bull_threshold   DECIMAL(8,4),       -- 当期 bull 阈值
    bear_threshold   DECIMAL(8,4),       -- 当期 bear 阈值
    -- 元数据
    knowledge_date   DATE,               -- PIT: 数据可知日期
    last_updated     TIMESTAMP
);
```

#### 4.2.8 因子表（PIT 安全）

```sql
-- 核心设计：knowledge_date 保证 Point-in-Time 安全
CREATE TABLE IF NOT EXISTS etf_factor_daily (
    symbol         VARCHAR,
    trade_date     DATE,
    factor_name    VARCHAR,              -- 'rs_20d'/'value_pe_252d'/'vol_20d'/...
    factor_value   DOUBLE,
    factor_z_score DOUBLE,
    knowledge_date DATE,                 -- PIT: 该因子值何时可知
    source_date    DATE,                 -- 源数据日期（如财报期末日）
    source         VARCHAR,              -- 'calculated'/'external'
    last_updated   TIMESTAMP,
    PRIMARY KEY (symbol, trade_date, factor_name)
);

-- PIT 查询示例：
-- SELECT * FROM etf_factor_daily
-- WHERE trade_date = $trade_date
--   AND knowledge_date <= $as_of_date  -- 只使用当时可知的数据

-- 因子元信息
CREATE TABLE IF NOT EXISTS factor_metadata (
    factor_name    VARCHAR PRIMARY KEY,
    description    VARCHAR,
    params         VARCHAR,              -- JSON 格式参数
    category       VARCHAR,              -- 'momentum'/'value'/'volatility'/'crowding'
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMP,
    updated_at     TIMESTAMP
);
```

#### 4.2.9 因子健康度表

```sql
CREATE TABLE IF NOT EXISTS factor_health_daily (
    factor_name    VARCHAR,
    calc_date      DATE,
    ic_1m          DOUBLE,               -- 1个月 Rank IC
    ic_3m          DOUBLE,               -- 3个月 Rank IC
    ic_6m          DOUBLE,               -- 6个月 Rank IC
    ic_12m         DOUBLE,               -- 12个月 Rank IC
    ic_ir          DOUBLE,               -- IC 的 Information Ratio
    health_status  VARCHAR,              -- 'HEALTHY'/'CAUTION'/'WARNING'/'CRITICAL'
    last_updated   TIMESTAMP,
    PRIMARY KEY (factor_name, calc_date)
);
```

#### 4.2.10 因子墓地（记录失效因子）

```sql
CREATE TABLE IF NOT EXISTS factor_graveyard (
    factor_name    VARCHAR,
    deprecated_date DATE,
    reason         VARCHAR,              -- 失效原因
    ic_at_death    DOUBLE,               -- 下线时的 IC
    peak_ic        DOUBLE,               -- 历史最佳 IC
    notes          VARCHAR,
    PRIMARY KEY (factor_name, deprecated_date)
);
```

#### 4.2.11 行业轮动 Score 表

```sql
CREATE TABLE IF NOT EXISTS rotation_score_daily (
    symbol         VARCHAR,
    trade_date     DATE,
    total_score    DOUBLE,
    rs_score       DOUBLE,
    value_score    DOUBLE,
    vol_score      DOUBLE,
    crowding_score DOUBLE,
    rank           INT,
    is_top_n       BOOLEAN,
    knowledge_date DATE,                 -- PIT
    last_updated   TIMESTAMP,
    PRIMARY KEY (symbol, trade_date)
);
```

#### 4.2.12 回测结果表

```sql
CREATE TABLE IF NOT EXISTS backtest_results (
    backtest_id    VARCHAR PRIMARY KEY,
    strategy_type  VARCHAR,
    start_date     DATE,
    end_date       DATE,
    initial_capital DECIMAL(18,2),
    final_capital  DECIMAL(18,2),
    total_return   DECIMAL(10,6),
    annual_return  DECIMAL(10,6),
    max_drawdown   DECIMAL(10,6),
    sharpe_ratio   DECIMAL(10,4),
    calmar_ratio   DECIMAL(10,4),
    win_rate       DECIMAL(10,4),
    total_trades   INT,
    turnover_annual DECIMAL(10,4),
    cost_ratio     DECIMAL(10,6),        -- 成本占毛收益比例
    config_snapshot VARCHAR,             -- JSON: 完整配置快照
    config_hash    VARCHAR,              -- 配置 hash，用于查重
    data_version   VARCHAR,              -- 使用的数据版本
    engine_type    VARCHAR,              -- 'fast'/'production'
    created_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS backtest_equity_curve (
    backtest_id    VARCHAR,
    trade_date     DATE,
    equity         DECIMAL(18,2),
    daily_return   DECIMAL(10,6),
    drawdown       DECIMAL(10,6),
    position_count INT,
    PRIMARY KEY (backtest_id, trade_date)
);

-- 每日持仓明细（用于对齐测试）
CREATE TABLE IF NOT EXISTS backtest_daily_holdings (
    backtest_id    VARCHAR,
    trade_date     DATE,
    symbol         VARCHAR,
    weight         DECIMAL(10,6),
    quantity       INT,
    PRIMARY KEY (backtest_id, trade_date, symbol)
);
```

#### 4.2.13 数据版本表

```sql
CREATE TABLE IF NOT EXISTS data_versions (
    version_id     VARCHAR PRIMARY KEY,
    dataset_name   VARCHAR,              -- 'etf_daily'/'factor_core'
    version_tag    VARCHAR,              -- 'v1_2020_2024q4'
    start_date     DATE,
    end_date       DATE,
    row_count      BIGINT,
    checksum       VARCHAR,              -- 数据校验和
    created_at     TIMESTAMP,
    notes          VARCHAR
);
```

---

## 5. SQLite Schema 设计

### 5.1 数据库文件

- 路径：`ledger/trading.db`
- 模式：WAL（Write-Ahead Logging）
- 备份：每日备份到 `backups/trading_YYYYMMDD.db`

### 5.2 表结构定义

#### 5.2.1 策略实例表

```sql
CREATE TABLE IF NOT EXISTS strategy_instances (
    strategy_id    TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    strategy_type  TEXT NOT NULL,        -- 'rotation'/'enhancement'/'cb_double_low'
    lifecycle_state TEXT NOT NULL,       -- 'research'/'paper'/'live_small'/'live_full'/'deprecated'
    risk_budget_pct REAL NOT NULL,       -- 风险预算百分比
    config         TEXT NOT NULL,        -- JSON
    created_at     TEXT NOT NULL,
    last_updated   TEXT NOT NULL
);
```

#### 5.2.2 调仓计划表

```sql
CREATE TABLE IF NOT EXISTS rebalance_plans (
    plan_id        TEXT PRIMARY KEY,
    strategy_id    TEXT NOT NULL,
    trade_date     TEXT NOT NULL,
    regime_type    TEXT,
    status         TEXT NOT NULL,        -- 'DRAFT'/'CONFIRMED'/'EXECUTED'/'CANCELLED'
    total_buy_amount REAL,
    total_sell_amount REAL,
    estimated_cost REAL,
    notes          TEXT,
    created_at     TEXT NOT NULL,
    confirmed_at   TEXT,
    executed_at    TEXT
);

CREATE TABLE IF NOT EXISTS rebalance_details (
    detail_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id        TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    current_weight REAL,
    target_weight  REAL,
    current_quantity INTEGER,
    target_quantity INTEGER,
    action         TEXT NOT NULL,        -- 'BUY'/'SELL'/'HOLD'
    reason         TEXT,
    limit_status   TEXT,                 -- 涨跌停状态
    FOREIGN KEY (plan_id) REFERENCES rebalance_plans(plan_id)
);
```

#### 5.2.3 模拟持仓表

```sql
CREATE TABLE IF NOT EXISTS simulated_positions (
    position_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id    TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    quantity       INTEGER NOT NULL,
    cost_basis     REAL NOT NULL,
    market_value   REAL,
    unrealized_pnl REAL,
    weight         REAL,
    last_updated   TEXT NOT NULL,
    UNIQUE(strategy_id, symbol)
);
```

#### 5.2.4 订单记录表

```sql
CREATE TABLE IF NOT EXISTS orders (
    order_id       TEXT PRIMARY KEY,
    strategy_id    TEXT NOT NULL,
    plan_id        TEXT,
    trade_date     TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    direction      TEXT NOT NULL,        -- 'BUY'/'SELL'
    quantity       INTEGER NOT NULL,
    price          REAL,
    order_type     TEXT NOT NULL,        -- 'MARKET'/'LIMIT'
    status         TEXT NOT NULL,        -- 'PENDING'/'FILLED'/'PARTIAL'/'CANCELLED'
    filled_quantity INTEGER DEFAULT 0,
    filled_price   REAL,
    commission     REAL,
    slippage       REAL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
```

#### 5.2.5 风控事件表

```sql
CREATE TABLE IF NOT EXISTS risk_events (
    event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type     TEXT NOT NULL,        -- 'kill_switch'/'position_limit'/'cost_alert'/'factor_degradation'
    severity       TEXT NOT NULL,        -- 'INFO'/'WARN'/'HIGH'/'CRITICAL'
    strategy_id    TEXT,                 -- 可以是全局事件
    trade_date     TEXT,
    current_value  REAL,
    threshold_value REAL,
    message        TEXT NOT NULL,
    action_taken   TEXT,
    created_at     TEXT NOT NULL,
    resolved_at    TEXT
);
```

#### 5.2.6 运行状态表

```sql
CREATE TABLE IF NOT EXISTS runtime_state (
    key            TEXT PRIMARY KEY,
    value          TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

-- 初始化状态
INSERT OR IGNORE INTO runtime_state (key, value, updated_at) VALUES
    ('system_mode', 'NORMAL', datetime('now')),
    ('kill_switch_active', 'false', datetime('now')),
    ('kill_switch_level', '0', datetime('now')),
    ('kill_switch_reason', '', datetime('now')),
    ('current_drawdown', '0.0', datetime('now')),
    ('drawdown_3d', '0.0', datetime('now')),      -- 3日回撤（速度检测）
    ('peak_equity', '0.0', datetime('now')),
    ('total_position', '0.0', datetime('now')),
    ('last_data_date', '', datetime('now')),
    ('last_heartbeat', '', datetime('now'));
```

#### 5.2.7 心跳记录表

```sql
CREATE TABLE IF NOT EXISTS heartbeat_log (
    heartbeat_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    status         TEXT NOT NULL,        -- 'OK'/'DEGRADED'/'ERROR'
    data_latest_date TEXT,
    kill_switch_active INTEGER,
    last_error     TEXT,
    details        TEXT,                 -- JSON
    sent_to        TEXT                  -- 发送目标
);
```

#### 5.2.8 执行日志
```sql

CREATE TABLE IF NOT EXISTS execution_log (
    log_id          VARCHAR PRIMARY KEY,
    plan_id         VARCHAR,
    order_id        VARCHAR,
    sub_order_id    VARCHAR,
    
    -- 订单信息
    symbol          VARCHAR,
    direction       VARCHAR,
    quantity        INTEGER,
    
    -- 执行信息
    strategy_type   VARCHAR,      -- MARKET/TWAP/VWAP
    execute_time    TIMESTAMP,
    fill_time       TIMESTAMP,
    
    -- 成交信息
    fill_price      DECIMAL(12, 4),
    fill_quantity   INTEGER,
    fill_status     VARCHAR,      -- FILLED/PARTIAL/FAILED
    
    -- 成本
    commission      DECIMAL(10, 6),
    slippage        DECIMAL(10, 6),
    market_impact   DECIMAL(10, 6),
    
    -- 质量指标
    implementation_shortfall DECIMAL(10, 6),
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_execution_plan ON execution_log(plan_id);
CREATE INDEX idx_execution_symbol ON execution_log(symbol, execute_time);
```

---

## 6. 数据质量保证设计

### 6.1 增强版校验器

```python
from dataclasses import dataclass
from typing import Callable
import polars as pl

@dataclass
class ValidationRule:
    name: str
    check_func: Callable
    severity: str  # 'ERROR'/'WARN'/'CRITICAL'

class EnhancedETFKlineValidator:
    """增强版 ETF 日线数据校验器"""
    
    def __init__(self):
        self.rules = [
            # 基础校验
            ValidationRule("price_range", self._check_price_range, "ERROR"),
            ValidationRule("volume_positive", self._check_volume, "ERROR"),
            ValidationRule("ohlc_relationship", self._check_ohlc, "ERROR"),
            
            # 增强校验
            ValidationRule("price_jump", self._check_price_jump, "WARN"),
            ValidationRule("trading_suspension", self._check_suspension, "WARN"),
            ValidationRule("split_adjustment", self._check_split, "CRITICAL"),
            ValidationRule("cross_source", self._check_cross_source, "CRITICAL"),
        ]
    
    def _check_price_range(self, df: pl.DataFrame) -> pl.DataFrame:
        """检查价格为正"""
        return df.filter(
            (pl.col("open") <= 0) |
            (pl.col("high") <= 0) |
            (pl.col("low") <= 0) |
            (pl.col("close") <= 0)
        )
    
    def _check_ohlc(self, df: pl.DataFrame) -> pl.DataFrame:
        """检查 OHLC 合理性"""
        return df.filter(
            (pl.col("high") < pl.col("low")) |
            (pl.col("close") > pl.col("high")) |
            (pl.col("close") < pl.col("low")) |
            (pl.col("open") > pl.col("high")) |
            (pl.col("open") < pl.col("low"))
        )
    
    def _check_volume(self, df: pl.DataFrame) -> pl.DataFrame:
        """检查成交量非负"""
        return df.filter(pl.col("volume") < 0)
    
    def _check_price_jump(self, df: pl.DataFrame) -> pl.DataFrame:
        """检查价格跳变（排除涨跌停的异常跳变）"""
        df_sorted = df.sort(["symbol", "trade_date"])
        df_with_ret = df_sorted.with_columns(
            (pl.col("close") / pl.col("close").shift(1) - 1).abs().alias("abs_return")
        )
        # 单日涨跌幅 > 15% 且非涨跌停
        return df_with_ret.filter(
            (pl.col("abs_return") > 0.15) &
            (pl.col("status") == "NORMAL")
        )
    
    def _check_suspension(self, df: pl.DataFrame) -> pl.DataFrame:
        """检测停牌数据异常（成交量为0但有价格变动）"""
        return df.filter(
            (pl.col("volume") == 0) &
            (pl.col("close") != pl.col("prev_close"))
        )
    
    def _check_split(self, df: pl.DataFrame) -> pl.DataFrame:
        """检测可能的复权错误"""
        df_sorted = df.sort(["symbol", "trade_date"])
        df_with_ret = df_sorted.with_columns(
            (pl.col("close") / pl.col("close").shift(1) - 1).abs().alias("abs_return")
        )
        # 单日跳变 8-9.5%（可能是未处理的除权）
        return df_with_ret.filter(
            (pl.col("abs_return") > 0.08) &
            (pl.col("abs_return") < 0.095)
        )
    
    def _check_cross_source(
        self,
        df_primary: pl.DataFrame,
        df_secondary: pl.DataFrame
    ) -> pl.DataFrame:
        """交叉验证两个数据源"""
        merged = df_primary.join(
            df_secondary.select(["symbol", "trade_date", "close"]),
            on=["symbol", "trade_date"],
            suffix="_secondary"
        )
        merged = merged.with_columns(
            ((pl.col("close") - pl.col("close_secondary")).abs() / pl.col("close"))
            .alias("price_diff_pct")
        )
        return merged.filter(pl.col("price_diff_pct") > 0.002)
    
    def validate(
        self,
        df: pl.DataFrame,
        df_secondary: pl.DataFrame = None
    ) -> tuple[pl.DataFrame, list[str]]:
        """执行所有校验，返回清洗后数据和告警"""
        warnings = []
        clean_df = df.clone()
        suspicious_symbols = set()
        
        for rule in self.rules:
            if rule.name == "cross_source":
                if df_secondary is not None:
                    invalid = rule.check_func(clean_df, df_secondary)
                    if len(invalid) > 0:
                        warnings.append(f"[{rule.severity}] {rule.name}: {len(invalid)} rows")
                        # 标记可疑标的
                        suspicious_symbols.update(invalid["symbol"].unique().to_list())
                continue
            
            invalid = rule.check_func(clean_df)
            if len(invalid) > 0:
                warnings.append(f"[{rule.severity}] {rule.name}: {len(invalid)} rows")
                
                if rule.severity in ("ERROR", "CRITICAL"):
                    # 删除错误行
                    clean_df = clean_df.join(
                        invalid.select(["symbol", "trade_date"]),
                        on=["symbol", "trade_date"],
                        how="anti"
                    )
        
        # 标记可疑数据
        if suspicious_symbols:
            clean_df = clean_df.with_columns(
                pl.when(pl.col("symbol").is_in(suspicious_symbols))
                .then(True)
                .otherwise(pl.col("is_suspicious"))
                .alias("is_suspicious")
            )
        
        return clean_df, warnings
```

### 6.2 涨跌停状态计算

```python
def calc_limit_status(
    close: float,
    prev_close: float,
    high: float,
    low: float,
    volume: int
) -> str:
    """计算涨跌停状态"""
    if volume == 0:
        return "SUSPENDED"
    
    change_pct = (close - prev_close) / prev_close
    
    # 一字板判断：最高=最低=收盘
    if high == low == close:
        if change_pct > 0.09:
            return "LIMIT_UP"
        elif change_pct < -0.09:
            return "LIMIT_DOWN"
    
    return "NORMAL"
```

### 6.3 数据时效性检查

```python
class DataStalenessChecker:
    """数据时效性检查器"""
    
    def check_staleness(
        self,
        latest_data_date: date,
        expected_date: date,
        max_staleness_days: int = 2
    ) -> tuple[bool, str]:
        """检查数据是否过期
        
        Returns:
            (is_stale, message)
        """
        staleness_days = (expected_date - latest_data_date).days
        
        if staleness_days <= 0:
            return False, "Data is up to date"
        elif staleness_days <= max_staleness_days:
            return False, f"Data is {staleness_days} day(s) behind (within tolerance)"
        else:
            return True, f"Data is {staleness_days} day(s) behind (exceeds {max_staleness_days})"
```

---

## 7. 动态复权计算

```python
class AdjustmentCalculator:
    """复权价格计算器"""
    
    @staticmethod
    def calc_adjusted_price(
        df: pl.DataFrame,
        adjust_type: str = "hfq"
    ) -> pl.DataFrame:
        """计算复权价格
        
        Args:
            df: 包含 open/high/low/close/adj_factor 的 DataFrame
            adjust_type: 'hfq'(后复权) / 'qfq'(前复权) / 'none'
        
        Returns:
            添加了复权价格列的 DataFrame
        """
        if adjust_type == "none":
            return df
        
        if adjust_type == "hfq":
            # 后复权：价格 * 复权因子
            return df.with_columns([
                (pl.col("open") * pl.col("adj_factor")).alias("open_adj"),
                (pl.col("high") * pl.col("adj_factor")).alias("high_adj"),
                (pl.col("low") * pl.col("adj_factor")).alias("low_adj"),
                (pl.col("close") * pl.col("adj_factor")).alias("close_adj"),
            ])
        
        elif adjust_type == "qfq":
            # 前复权：价格 * 复权因子 / 最新复权因子
            latest_adj = df.select(pl.col("adj_factor").last()).item()
            return df.with_columns([
                (pl.col("open") * pl.col("adj_factor") / latest_adj).alias("open_adj"),
                (pl.col("high") * pl.col("adj_factor") / latest_adj).alias("high_adj"),
                (pl.col("low") * pl.col("adj_factor") / latest_adj).alias("low_adj"),
                (pl.col("close") * pl.col("adj_factor") / latest_adj).alias("close_adj"),
            ])
        
        raise ValueError(f"Unknown adjust_type: {adjust_type}")
```

---

## 8. 数据生命周期与分层

### 8.1 数据分层

| 层 | 位置 | 说明 |
|----|------|------|
| Raw | `data/raw/*.parquet` | 原始数据（可选，用于审计） |
| Warehouse | `data/warehouse.duckdb` | 清洗后的规范化数据 |
| Feature | DuckDB 中的因子表 | 衍生特征数据 |

### 8.2 数据保留策略

| 数据类型 | 保留期限 | 备份频率 |
|----------|----------|----------|
| K线数据 | 永久 | 每周 |
| 因子数据 | 永久 | 每周 |
| 回测结果 | 1年 | 每月 |
| 调仓计划 | 永久 | 每日 |
| 风控事件 | 永久 | 每日 |
| 运行状态 | 30天 | N/A |

---

## 9. Golden Dataset（基准数据集）

### 9.1 目的

在正式开发前，建立一个**手工核验**的基准数据集，用于：

1. 验证数据采集管道的正确性
2. 作为单元测试的基准
3. 验证复权计算的正确性

### 9.2 选取标准

选取 3 只代表性 ETF + 1 个指数：

| 标的 | 代码 | 特点 |
|------|------|------|
| 沪深300 ETF | 510300.SH | 流动性最好 |
| 游戏 ETF | 516010.SH | 流动性较差 |
| 纳指 ETF | 513100.SH | 跨境 ETF，有溢价 |
| 沪深300 指数 | 000300.SH | Regime 基准 |

### 9.3 核验内容

对每个标的，手工核验以下内容（与东方财富/同花顺对比）：

- [ ] 100 个交易日的收盘价
- [ ] 复权因子（找到有分红的日期）
- [ ] 涨跌停状态
- [ ] 停牌日期

### 9.4 存储位置

```
data/golden/
  510300_SH_golden.parquet
  516010_SH_golden.parquet
  513100_SH_golden.parquet
  000300_SH_golden.parquet
  validation_report.md
```

---

## 10. 性能与容量评估

### 10.1 假设

- ETF Universe：50–200 只
- 历史区间：5 年（日线 ~1250 条/标的）
- 总 K 线条数：200 × 1250 ≈ 25 万条
- 因子数：4–10 个

### 10.2 建议
DuckDB与Polars 场景分析

```python
"""
DuckDB用于复杂分析查询
与Polars完美配合
"""

import duckdb
import polars as pl

class DataWarehouse:
    """数据仓库层 - OLAP分析"""
    
    def __init__(self, db_path: str = "data/ditto.duckdb"):
        self.conn = duckdb.connect(db_path)
    
    # 场景1：因子IC分析（多表Join + 窗口函数）
    def analyze_factor_ic(
        self,
        factor_data: pl.DataFrame,
        price_data: pl.DataFrame
    ) -> pl.DataFrame:
        """分析因子IC
        
        SQL比Polars表达式更清晰
        """
        self.conn.register('factors', factor_data)
        self.conn.register('prices', price_data)
        
        return self.conn.execute("""
            WITH forward_returns AS (
                SELECT 
                    symbol,
                    date,
                    LEAD(close, 1) OVER (PARTITION BY symbol ORDER BY date) / close - 1 AS return_1d,
                    LEAD(close, 5) OVER (PARTITION BY symbol ORDER BY date) / close - 1 AS return_5d,
                    LEAD(close, 20) OVER (PARTITION BY symbol ORDER BY date) / close - 1 AS return_20d
                FROM prices
            )
            SELECT 
                f.date,
                corr(f.factor_value, fr.return_1d) AS ic_1d,
                corr(f.factor_value, fr.return_5d) AS ic_5d,
                corr(f.factor_value, fr.return_20d) AS ic_20d
            FROM factors f
            JOIN forward_returns fr ON f.date = fr.date AND f.symbol = fr.symbol
            WHERE fr.return_1d IS NOT NULL
            GROUP BY f.date
            ORDER BY f.date
        """).pl()
    
    # 场景2：分位数收益分析
    def analyze_quantile_returns(
        self,
        factor_data: pl.DataFrame,
        price_data: pl.DataFrame
    ) -> pl.DataFrame:
        """计算分位数收益"""
        
        self.conn.register('factors', factor_data)
        self.conn.register('prices', price_data)
        
        return self.conn.execute("""
            WITH forward_returns AS (
                SELECT 
                    symbol,
                    date,
                    LEAD(close, 1) OVER (PARTITION BY symbol ORDER BY date) / close - 1 AS return_1d
                FROM prices
            ),
            factor_quantiles AS (
                SELECT 
                    f.*,
                    NTILE(5) OVER (PARTITION BY f.date ORDER BY f.factor_value) AS quantile
                FROM factors f
            )
            SELECT 
                fq.quantile,
                AVG(fr.return_1d) AS mean_return,
                STDDEV(fr.return_1d) AS std_return,
                COUNT(*) AS count
            FROM factor_quantiles fq
            JOIN forward_returns fr ON fq.date = fr.date AND fq.symbol = fr.symbol
            WHERE fr.return_1d IS NOT NULL
            GROUP BY fq.quantile
            ORDER BY fq.quantile
        """).pl()
    
    # 场景3：回测结果统计
    def analyze_backtest_by_period(
        self,
        trades: pl.DataFrame
    ) -> pl.DataFrame:
        """按时间周期统计回测结果"""
        
        self.conn.register('trades', trades)
        
        return self.conn.execute("""
            SELECT 
                strftime('%Y-%m', date) AS month,
                COUNT(*) AS num_trades,
                SUM(pnl) AS total_pnl,
                AVG(pnl) AS avg_pnl,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::FLOAT / COUNT(*) AS win_rate,
                MAX(pnl) AS max_win,
                MIN(pnl) AS max_loss
            FROM trades
            GROUP BY month
            ORDER BY month
        """).pl()
    
    # 场景4：数据质量检查
    def detect_price_anomalies(
        self,
        price_data: pl.DataFrame
    ) -> pl.DataFrame:
        """检测价格异常（跳空、成交量异常）"""
        
        self.conn.register('prices', price_data)
        
        return self.conn.execute("""
            WITH price_stats AS (
                SELECT 
                    *,
                    close / LAG(close, 1) OVER (PARTITION BY symbol ORDER BY date) - 1 AS pct_change,
                    volume / AVG(volume) OVER (
                        PARTITION BY symbol 
                        ORDER BY date 
                        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                    ) AS volume_ratio
                FROM prices
            )
            SELECT 
                date,
                symbol,
                close,
                pct_change,
                volume_ratio,
                CASE 
                    WHEN ABS(pct_change) > 0.10 THEN 'Price Jump'
                    WHEN volume_ratio > 5 THEN 'Volume Spike'
                    WHEN volume_ratio < 0.1 THEN 'Volume Drop'
                END AS anomaly_type
            FROM price_stats
            WHERE ABS(pct_change) > 0.10 OR volume_ratio > 5 OR volume_ratio < 0.1
            ORDER BY date, symbol
        """).pl()
```

**DuckDB vs Polars 使用原则**：

| 场景 | 推荐 | 原因 |
|------|------|------|
| 数据持久化 | DuckDB | 主数据库 |
| ETL处理 | Polars | API友好，性能好 |
| 简单查询 | Polars | 表达式简洁 |
| **复杂SQL** | **DuckDB** | **SQL更清晰** |
| **多表Join** | **DuckDB** | **窗口函数强** |
| **OLAP聚合** | **DuckDB** | **专业引擎** |
| 向量化计算 | Polars | 回测、因子计算 |


### 10.3 结论

- DuckDB 单文件完全轻松应对
- 数据体积在数十 MB 级别
- 备份简单，迁移方便

---

*本数据设计文档与 `01_system_design_v2.md`、`03_engine_design_v2.md` 紧密配合。Phase 2+ 扩展到分钟线、可转债、实盘订单时，可在本结构基础上增量扩展。*

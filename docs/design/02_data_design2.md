# Ditto 数据层设计文档

> **版本**: v1.4
> **定位**: Solo Quant 量化系统数据基础设施
> **原则**: 正确性优先、可复现、可增量、80%场景优先

## 修订记录

| 版本 | 日期 | 变更内容 |
|-----|------|---------|
| v1.4 | - | **P0修正**: (1) src_code 替代 ts_code，支持多数据源（tushare/ricequant/akshare）；(2) (source, src_code) 作为主映射通道；(3) 移除 fundamental_pit.ingest_ts 保证幂等；(4) _atomic_write 改用 os.replace 避免竞态；(5) checksum 统一使用 file_md5_stream；(6) 移除 securities.industry_l1/l2 单一真相。**P1优化**: (1) list_days 改为 O(1)：open_seq 序号算法；(2) symbol_changes 约束收敛到 sid 维度；(3) Reader watermark 裁剪使用 _get_next_trade_date 避免 off-by-one；(4) resolve_sid 历史查询不短路当前映射 |
| v1.3 | - | DQ动态涨跌幅阈值（制度口径感知）；name_changes表分离；复权因子强校验；SQLite锁重试装饰器；compaction_state路径裁剪；行业Unknown兜底 |
| v1.2 | - | 新增 Classification 子域（申万行业 + 概念/主题）；行业SCD2有效期；taxonomy版本化 |
| v1.1 | - | 移除事实表运行态字段；三段式原子提交；SecurityMaster API重构；Reader derived优先读取 |
| v1.0 | - | 初始版本 |

---

## 一、设计原则

### 1.1 核心约束

| 原则 | 说明 |
|-----|------|
| **Point-in-Time (PIT)** | 任何时点的回测只能看到该时点已公开的信息，杜绝未来信息泄露 |
| **身份不可变** | Security ID (sid) 一经分配永不改变，外部代码变更不影响数据连续性 |
| **幂等可重跑** | 同一任务对同一日期重跑，产出结果完全一致 |
| **写入时处理** | 数据标准化、ID映射等在写入时完成，查询时零负担 |
| **事实与元数据分离** | Parquet 存事实数据，SQLite 存元数据与治理信息 |

### 1.2 介质分工

```
┌─────────────────────────────────────────────────────────────────┐
│                        存储介质分工                              │
├─────────────┬───────────────────┬───────────────────────────────┤
│   Parquet   │   事实数据主存储   │ 行情、复权、财务、特征、标签     │
│   SQLite    │   控制塔          │ Security Master、日历、治理元数据│
│   DuckDB    │   查询引擎        │ SQL装配、分析、研究缓存          │
└─────────────┴───────────────────┴───────────────────────────────┘
```

---

## 二、数据目录结构

```
$DITTO_DATA_ROOT/
│
├── raw/                              # [可选] 原始快照层（排障回放用）
│   └── tushare/
│       └── daily/
│           └── year=YYYY/
│               └── data.parquet
│
├── curated/                          # 清洗标准化层（核心事实）
│   ├── market/
│   │   └── daily/
│   │       └── dt=YYYY-MM-DD/
│   │           └── data.parquet
│   │
│   ├── adjustment/
│   │   └── factor/
│   │       └── dt=YYYY-MM-DD/
│   │           └── data.parquet
│   │
│   ├── fundamental/
│   │   ├── income/
│   │   │   └── data.parquet
│   │   ├── balance/
│   │   │   └── data.parquet
│   │   └── cashflow/
│   │       └── data.parquet
│   │
│   ├── universe/
│   │   ├── index=000300.SH/
│   │   │   └── data.parquet
│   │   └── etf_pool/
│   │       └── data.parquet
│   │
│   └── classification/               # 行业/概念分类（新增）
│       ├── sw_industry/
│       │   ├── taxonomy/             # 申万行业目录（层级树）
│       │   │   └── version=SW2021/
│       │   │       └── data.parquet
│       │   ├── membership/           # 个股-行业归属（SCD2有效期）
│       │   │   └── version=SW2021/
│       │   │       └── data.parquet
│       │   └── daily/                # 回测加速快照
│       │       └── version=SW2021/
│       │           └── dt=YYYY-MM-DD/
│       │               └── data.parquet
│       │
│       └── theme/
│           ├── taxonomy/             # 概念/主题板块目录
│           │   ├── source=ths/
│           │   │   └── data.parquet
│           │   └── source=dc/
│           │       └── data.parquet
│           ├── membership_daily/     # 概念每日成分（白名单）
│           │   └── source=dc/
│           │       └── dt=YYYY-MM-DD/
│           │           └── data.parquet
│           └── signals/              # 热度/资金流信号
│               ├── source=ths_hot/
│               │   └── dt=YYYY-MM-DD/
│               │       └── data.parquet
│               └── source=dc_moneyflow/
│                   └── dt=YYYY-MM-DD/
│                       └── data.parquet
│
├── derived/                          # 派生加速层（可重建）
│   ├── market/
│   │   └── daily/
│   │       └── year=YYYY/
│   │           └── data.parquet
│   └── sw_industry/                  # 行业每日快照（年度归档）
│       └── version=SW2021/
│           └── year=YYYY/
│               └── data.parquet
│
├── features/                         # 特征工程产出
│   └── <feature_set_id>/
│       └── dt=YYYY-MM-DD/
│           └── data.parquet
│
├── labels/                           # 标签数据
│   └── <label_set_id>/
│       └── dt=YYYY-MM-DD/
│           └── data.parquet
│
└── meta/
    └── ditto.sqlite                  # 元数据库（控制塔）
```

### 2.1 分区策略

| 数据域 | 写入分区 | 读取优化 | 说明 |
|-------|---------|---------|------|
| 日线行情 | `dt=YYYY-MM-DD` | `year=YYYY`（compaction产出） | 写入增量友好，读取批量友好 |
| 复权因子 | `dt=YYYY-MM-DD` | 同上 | 与行情对齐 |
| 财务数据 | 不分区 | - | 数据量小，单文件即可 |
| 指数成分 | `index=CODE` | - | 按指数分区 |
| 特征/标签 | `dt=YYYY-MM-DD` | - | 与行情日期对齐 |

---

## 三、Security Master 设计

### 3.1 核心理念

```
┌────────────────────────────────────────────────────────────────┐
│  sid (Security ID) = 内部唯一身份标识，永不改变                  │
│  src_code          = 数据源原始代码，外部稳定键                  │
│  source            = 数据源标识（tushare/ricequant/akshare）    │
│  symbol            = 展示/交易代码，可能变更（仅UI用）           │
│                                                                │
│  所有事实表以 sid 作为主键                                       │
│  Ingestion 以 (source, src_code) -> sid 作为主映射通道          │
│  symbol 仅用于展示，不参与数据对接                               │
└────────────────────────────────────────────────────────────────┘

多数据源代码示例：
┌───────────┬────────────────┬─────────────────┐
│  数据源    │   src_code     │   symbol        │
├───────────┼────────────────┼─────────────────┤
│  tushare  │  600000.SH     │  600000         │
│  ricequant│  600000.XSHG   │  600000         │
│  akshare  │  sh600000      │  600000         │
└───────────┴────────────────┴─────────────────┘
```

### 3.2 表结构

#### securities（证券主表）

```sql
CREATE TABLE securities (
    -- 身份标识（永不改变）
    sid             INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 数据源标识（支持多数据源）
    source          TEXT NOT NULL DEFAULT 'tushare',  -- tushare/ricequant/akshare
    src_code        TEXT NOT NULL,              -- 数据源原始代码（600000.SH / 600000.XSHG）

    -- 展示/交易代码（可能变更，仅UI用）
    symbol          TEXT NOT NULL,              -- 当前交易代码（600000）

    -- 基础信息
    name            TEXT,                       -- 证券全称
    display_name    TEXT,                       -- 当前展示名/简称（如：浦发银行）

    -- 上市信息
    exchange        TEXT NOT NULL,              -- SZ/SH/BJ
    board           TEXT,                       -- 主板/创业板/科创板/北交所
    market          TEXT,                       -- 原始market字段（可选）
    list_date       DATE NOT NULL,              -- 上市日期
    list_open_seq   INTEGER,                    -- 上市日交易日序号（用于O(1)计算list_days）
    delist_date     DATE,                       -- 退市日期（NULL=在市）

    -- 分类信息（v1.4：移除industry_l1/l2，统一由security_sw_industry管理）
    asset_class     TEXT DEFAULT 'equity',      -- equity/etf/bond/fund

    -- 状态标记
    is_st           BOOLEAN DEFAULT FALSE,      -- 是否ST
    is_active       BOOLEAN DEFAULT TRUE,       -- 是否可交易

    -- 审计字段
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP,

    -- 唯一约束：同一数据源内代码唯一
    UNIQUE(source, src_code)
);

-- 索引
CREATE INDEX idx_securities_src_code ON securities(source, src_code);
CREATE INDEX idx_securities_symbol ON securities(symbol);
CREATE INDEX idx_securities_exchange ON securities(exchange);
CREATE INDEX idx_securities_board ON securities(board);
CREATE INDEX idx_securities_active ON securities(is_active);
CREATE INDEX idx_securities_list_date ON securities(list_date);
```

#### symbol_changes（代码变更历史）

> 仅记录真正的代码变更（A股每年<10次），与名称变更分离
> v1.4：唯一约束收敛到 sid 维度，避免符号复用冲突

```sql
CREATE TABLE symbol_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 身份关联（永不改变）
    sid             INTEGER NOT NULL,

    -- 代码信息
    source          TEXT NOT NULL,              -- 数据源
    src_code        TEXT NOT NULL,              -- 该数据源的代码（通常不变）
    symbol          TEXT NOT NULL,              -- 当时使用的交易代码

    -- 有效期
    effective_from  DATE NOT NULL,              -- 生效起始日
    effective_to    DATE,                       -- 生效结束日（NULL=当前）

    -- 变更信息
    change_type     TEXT,                       -- code_change/restructure/relisting
    change_reason   TEXT,

    -- 审计字段
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (sid) REFERENCES securities(sid),

    -- v1.4：约束收敛到 sid 维度，保证一个 sid 的区间不重叠
    UNIQUE(sid, effective_from)
);

-- 索引（用于反向查找）
CREATE INDEX idx_symbol_changes_sid ON symbol_changes(sid);
CREATE INDEX idx_symbol_changes_src_code ON symbol_changes(source, src_code, effective_from, effective_to);
CREATE INDEX idx_symbol_changes_symbol ON symbol_changes(symbol, effective_from, effective_to);
```

#### name_changes（名称变更历史）

> 与代码变更分离，A股改名频繁（每年~200次），但不影响交易代码

```sql
CREATE TABLE name_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    sid             INTEGER NOT NULL,

    -- 名称信息
    name            TEXT NOT NULL,              -- 曾用名
    display_name    TEXT,                       -- 曾用简称

    -- 有效期
    effective_from  DATE NOT NULL,
    effective_to    DATE,                       -- NULL=当前

    -- 变更原因
    reason          TEXT,                       -- ST/摘帽/重组/更名等

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (sid) REFERENCES securities(sid),

    -- 保证一个 sid 的区间不重叠
    UNIQUE(sid, effective_from)
);

CREATE INDEX idx_name_changes_sid ON name_changes(sid);
CREATE INDEX idx_name_changes_dt ON name_changes(effective_from, effective_to);
```

### 3.3 代码变更处理流程

```
代码变更发生时（如 A → B）：

1. symbol_changes 表：
   - 更新旧记录：effective_to = change_date
   - 插入新记录：symbol=B, effective_from=change_date

2. securities 表：
   - 更新 symbol = B
   - src_code 通常不变（数据源自己的代码体系）

3. Parquet 数据：
   - 无需任何修改（因为存储的是 sid，不是 symbol）

名称变更发生时（如"浦发银行"→"上海浦发"）：

1. name_changes 表：
   - 更新旧记录：effective_to = change_date
   - 插入新记录：name=新名称, effective_from=change_date

2. securities 表：
   - 更新 display_name = 新名称

3. 其他表：无影响

┌─────────────────────────────────────────────────────────────┐
│  关键优势：                                                  │
│  - src_code 数据源无关，支持多数据源接入                      │
│  - 代码变更/名称变更分离，语义清晰                           │
│  - 历史数据无需回刷（sid 是真正的主键）                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、交易日历

### 4.1 表结构

```sql
CREATE TABLE trading_calendar (
    trade_date      DATE PRIMARY KEY,

    -- 状态
    is_open         BOOLEAN NOT NULL,           -- 是否交易日

    -- v1.4：交易日序号（用于 O(1) 计算 list_days）
    open_seq        INTEGER,                    -- 交易日递增序号（仅开市日有值）

    -- 导航字段（便于快速查询前后交易日）
    prev_trade_date DATE,                       -- 上一交易日
    next_trade_date DATE,                       -- 下一交易日

    -- 扩展信息
    week_of_year    INTEGER,
    month           INTEGER,
    quarter         INTEGER,
    year            INTEGER,
    is_week_end     BOOLEAN,                    -- 是否周末最后交易日
    is_month_end    BOOLEAN,                    -- 是否月末最后交易日
    is_quarter_end  BOOLEAN,                    -- 是否季末最后交易日

    -- 审计
    updated_at      TIMESTAMP
);

-- 索引
CREATE INDEX idx_calendar_open ON trading_calendar(is_open);
CREATE INDEX idx_calendar_open_seq ON trading_calendar(open_seq);
CREATE INDEX idx_calendar_month ON trading_calendar(year, month);
```

### 4.2 open_seq 的计算与用途

```python
def compute_open_seq(conn: sqlite3.Connection):
    """
    计算交易日序号（一次性或增量更新）

    open_seq 从 1 开始递增，仅交易日有值
    用于 O(1) 计算上市交易日天数
    """
    conn.execute("""
        WITH ranked AS (
            SELECT
                trade_date,
                ROW_NUMBER() OVER (ORDER BY trade_date) as seq
            FROM trading_calendar
            WHERE is_open = TRUE
        )
        UPDATE trading_calendar
        SET open_seq = (SELECT seq FROM ranked WHERE ranked.trade_date = trading_calendar.trade_date)
        WHERE is_open = TRUE
    """)
    conn.commit()


def compute_list_days_o1(trade_open_seq: int, list_open_seq: int) -> int:
    """
    O(1) 计算上市交易日天数

    替代原来的 COUNT(*) SQL 查询
    """
    if list_open_seq is None or trade_open_seq is None:
        return 999999
    return trade_open_seq - list_open_seq + 1
```

---

## 五、Curated 层数据协议（Schema）

### 5.1 market_daily（日线行情）

**主键**: `(sid, trade_date)`

```python
MARKET_DAILY_SCHEMA = {
    # 主键
    "sid":              pl.Int64,       # Security ID（身份标识）
    "trade_date":       pl.Date,        # 交易日期

    # 数据源标识（v1.4：用于调试和多数据源溯源）
    "src_code":         pl.Utf8,        # 数据源原始代码（600000.SH）

    # OHLCV
    "open":             pl.Float64,     # 开盘价（未复权）
    "high":             pl.Float64,     # 最高价
    "low":              pl.Float64,     # 最低价
    "close":            pl.Float64,     # 收盘价
    "volume":           pl.Float64,     # 成交量（股）
    "amount":           pl.Float64,     # 成交额（元）

    # 衍生字段
    "vwap":             pl.Float64,     # 成交均价（可选）
    "pct_change":       pl.Float64,     # 涨跌幅（%）
    "turnover":         pl.Float64,     # 换手率（%）

    # 状态标记
    "is_suspended":     pl.Boolean,     # 是否停牌
    "is_limit_up":      pl.Boolean,     # 是否涨停
    "is_limit_down":    pl.Boolean,     # 是否跌停
    "is_st":            pl.Boolean,     # 是否ST（当日状态）

    # 数据溯源（仅保留不变字段，运行态信息进pipeline_runs）
    "source":           pl.Utf8,        # 数据源（tushare/ricequant/akshare）
}

# 注意：fetch_ts 等运行态字段不进入事实表
# 由 pipeline_runs.started_at 和 data_versions.created_at 记录
# 这保证了同日期重跑产出完全一致（幂等性）
```

### 5.2 adjustment_factor（复权因子）

**主键**: `(sid, trade_date)`

```python
ADJUSTMENT_FACTOR_SCHEMA = {
    "sid":              pl.Int64,
    "trade_date":       pl.Date,
    "src_code":         pl.Utf8,        # v1.4：数据源原始代码

    # 复权因子
    "adj_factor":       pl.Float64,     # 累计复权因子（后复权）

    # 数据溯源（不含运行态字段）
    "source":           pl.Utf8,
}
```

**复权价格计算**:
```python
# 后复权价格（研究/回测用）
close_adj = close * adj_factor

# 前复权价格（展示用，需要基准日）
close_adj_forward = close * adj_factor / adj_factor_base
```

### 5.3 fundamental_pit（财务数据 Point-in-Time）

**主键**: `(sid, report_period, announce_date)`

```python
FUNDAMENTAL_PIT_SCHEMA = {
    # 身份
    "sid":              pl.Int64,
    "src_code":         pl.Utf8,        # v1.4：数据源原始代码

    # PIT 两时间戳（v1.4：移除 ingest_ts，保证幂等性）
    "report_period":    pl.Date,        # 报告期末（如 2023-12-31）
    "announce_date":    pl.Date,        # 公告日期（市场可见日）- v1使用Date
    "announce_ts":      pl.Datetime,    # 公告时间戳（预留，v1可为空）
    # 注意：ingest_ts 移除，入库时间由 pipeline_runs/data_versions 记录

    # 财务指标（示例）
    "revenue":          pl.Float64,     # 营业收入
    "net_profit":       pl.Float64,     # 净利润
    "roe":              pl.Float64,     # ROE
    "roa":              pl.Float64,     # ROA
    "gross_margin":     pl.Float64,     # 毛利率
    "debt_ratio":       pl.Float64,     # 资产负债率

    # 同比增长
    "revenue_yoy":      pl.Float64,     # 营收同比
    "profit_yoy":       pl.Float64,     # 净利润同比

    # 数据质量
    "report_type":      pl.Utf8,        # 报告类型（1=合并报表）
    "source":           pl.Utf8,
}

# PIT 语义说明（v1）：
# - announce_date 当日收盘后即视为可用
# - 适用于日线频率策略
# - 若需更精细控制，启用 announce_ts 字段
#
# v1.4 幂等性保证：
# - 移除 ingest_ts，同一数据重跑结果完全一致
# - 如需延迟分析，建 fundamental_ingest_log 放 SQLite
```

**PIT 查询核心逻辑**:
```python
def query_pit_fundamental(
    sid: int,
    as_of_date: str,      # 回测时点
    metric: str,
    periods: int = 1      # 最近N期
) -> pl.DataFrame:
    """
    获取某时点能看到的财务数据
    关键：只返回 announce_date <= as_of_date 的数据
    """
    return (
        pl.scan_parquet("curated/fundamental/income/data.parquet")
        .filter(pl.col("sid") == sid)
        .filter(pl.col("announce_date") <= as_of_date)  # PIT 约束
        .sort("report_period", descending=True)
        .head(periods)
        .collect()
    )
```

### 5.4 universe_constituent（指数/组合成分）

**主键**: `(universe_id, sid, effective_from)`

```python
UNIVERSE_CONSTITUENT_SCHEMA = {
    # 组合标识
    "universe_id":      pl.Utf8,        # 000300.SH / etf_pool / custom
    "universe_name":    pl.Utf8,        # 沪深300 / ETF池

    # 成分股
    "sid":              pl.Int64,
    "src_code":         pl.Utf8,        # v1.4：数据源原始代码

    # 有效期（避免幸存者偏差的关键）
    "effective_from":   pl.Date,        # 纳入日期
    "effective_to":     pl.Date,        # 剔除日期（NULL=当前成分）

    # 权重（可选）
    "weight":           pl.Float64,     # 成分权重

    # 数据溯源
    "source":           pl.Utf8,        # tushare/ricequant/akshare
}
```

---

## 六、Pipeline 治理元数据

### 6.0 SQLite 初始化与并发控制

```python
import time
import random
import sqlite3
from functools import wraps

def init_meta_db(db_path: str) -> sqlite3.Connection:
    """初始化元数据库（带并发优化配置）"""
    conn = sqlite3.connect(db_path, check_same_thread=False)

    # 性能与并发配置
    conn.execute("PRAGMA journal_mode=WAL")      # Write-Ahead Logging
    conn.execute("PRAGMA synchronous=NORMAL")    # 平衡安全与性能
    conn.execute("PRAGMA busy_timeout=5000")     # 锁等待超时5秒
    conn.execute("PRAGMA cache_size=-64000")     # 64MB缓存

    # 创建表结构
    _create_tables(conn)

    return conn


def retry_sqlite_locked(max_retries: int = 8, base_sleep: float = 0.05, max_sleep: float = 1.0):
    """
    SQLite "database is locked" 重试装饰器（指数退避 + 随机抖动）

    用于包装所有写入操作，避免多任务并发时锁竞争导致失败
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for i in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    msg = str(e).lower()
                    if "database is locked" not in msg:
                        raise
                    # 指数退避 + 随机抖动
                    sleep = min(max_sleep, base_sleep * (2 ** i)) * (0.8 + 0.4 * random.random())
                    time.sleep(sleep)
            # 最后一次仍失败：直接执行（会抛出原始异常）
            return fn(*args, **kwargs)
        return wrapper
    return decorator


@retry_sqlite_locked()
def safe_execute(conn: sqlite3.Connection, sql: str, params: list = None):
    """安全执行单条SQL（带重试）"""
    conn.execute(sql, params or [])
    conn.commit()


@retry_sqlite_locked()
def safe_executemany(conn: sqlite3.Connection, sql: str, rows: list[dict]):
    """安全批量执行（带重试）"""
    conn.executemany(sql, rows)
    conn.commit()
```

### 6.1 表结构

```sql
-- ============================================================
-- 待处理证券（防止运行时污染 Security Master）
-- v1.4：使用 src_code + data_source 作为主键，支持多数据源
-- ============================================================
CREATE TABLE pending_symbols (
    data_source     TEXT NOT NULL,              -- 数据源（tushare/ricequant/akshare）
    src_code        TEXT NOT NULL,              -- 数据源原始代码
    first_seen_date DATE NOT NULL,              -- 首次发现日期
    discovered_by   TEXT NOT NULL,              -- 发现来源（ingest_daily/sync_theme_member等）
    status          TEXT DEFAULT 'pending',     -- pending/processed/ignored
    processed_at    TIMESTAMP,
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (data_source, src_code)
);

CREATE INDEX idx_pending_status ON pending_symbols(status);
CREATE INDEX idx_pending_source ON pending_symbols(data_source);


-- ============================================================
-- Pipeline 运行记录
-- ============================================================
CREATE TABLE pipeline_runs (
    run_id          TEXT PRIMARY KEY,           -- UUID

    -- 任务信息
    task_name       TEXT NOT NULL,              -- ingest_daily / build_features
    target_table    TEXT NOT NULL,              -- curated/market/daily

    -- 执行范围
    date_range      TEXT,                       -- 2024-01-01:2024-01-31
    watermark_dt    DATE,                       -- 本次处理的截止日期（便于定位影响范围）
    params          JSON,                       -- 任务参数

    -- 执行结果
    rows_read       INTEGER,
    rows_written    INTEGER,
    status          TEXT NOT NULL,              -- pending/running/success/failed
    error_msg       TEXT,

    -- 质量摘要
    dq_summary      JSON,                       -- {"nulls": 0, "outliers": 3}
    dq_passed       BOOLEAN,                    -- DQ是否通过

    -- 版本追踪（可复现的关键）
    code_version    TEXT,                       -- git commit hash
    data_version    TEXT,                       -- 依赖数据版本摘要

    -- 时间（运行态信息集中在此，不进事实表）
    started_at      TIMESTAMP,
    finished_at     TIMESTAMP,
    duration_sec    REAL
);

CREATE INDEX idx_runs_task ON pipeline_runs(task_name);
CREATE INDEX idx_runs_status ON pipeline_runs(status);
CREATE INDEX idx_runs_time ON pipeline_runs(started_at);


-- ============================================================
-- 数据版本追踪
-- ============================================================
CREATE TABLE data_versions (
    table_name      TEXT NOT NULL,
    partition_key   TEXT NOT NULL,              -- dt=2024-01-01 / year=2024

    -- 文件信息
    file_path       TEXT NOT NULL,
    file_size       INTEGER,
    row_count       INTEGER,

    -- 数据范围
    min_date        DATE,
    max_date        DATE,
    sid_count       INTEGER,                    -- 涉及的证券数量

    -- 校验（使用流式计算，避免大文件内存爆炸）
    checksum        TEXT,                       -- 文件MD5（流式计算）

    -- 版本
    code_version    TEXT,
    created_by      TEXT,                       -- run_id
    created_at      TIMESTAMP,

    PRIMARY KEY (table_name, partition_key)
);

CREATE INDEX idx_versions_table ON data_versions(table_name);


-- ============================================================
-- Compaction 状态（Reader 路径裁剪的 watermark）
-- ============================================================
CREATE TABLE compaction_state (
    table_name          TEXT PRIMARY KEY,       -- market/daily, adjustment/factor
    last_compacted_dt   DATE,                   -- 已合并到 derived 的截止日期
    last_compacted_year INTEGER,                -- 已合并的最新年份
    updated_at          TIMESTAMP
);

CREATE INDEX idx_compaction_updated ON compaction_state(updated_at);


-- ============================================================
-- 数据质量异常记录
-- ============================================================
CREATE TABLE dq_anomalies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 关联
    run_id          TEXT,
    table_name      TEXT NOT NULL,

    -- 异常位置（v1.4：使用 src_code 而非 symbol）
    sid             INTEGER,
    src_code        TEXT,                           -- 数据源原始代码
    trade_date      DATE,

    -- 异常信息
    rule_name       TEXT NOT NULL,              -- price_jump_dynamic / ohlc_invalid / adj_gap
    severity        TEXT DEFAULT 'warning',     -- info/warning/error
    detail          TEXT,                       -- JSON 字符串：{"pct_change": 25, "limit_pct": 20}

    -- 处理
    action          TEXT,                       -- flagged/fixed/dropped

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_anomalies_table ON dq_anomalies(table_name);
CREATE INDEX idx_anomalies_date ON dq_anomalies(trade_date);
CREATE INDEX idx_anomalies_rule ON dq_anomalies(rule_name);
CREATE INDEX idx_anomalies_severity ON dq_anomalies(severity);
CREATE INDEX idx_anomalies_src_code ON dq_anomalies(src_code);


-- ============================================================
-- 涨跌幅制度配置（DQ 动态阈值）
-- ============================================================
CREATE TABLE price_limit_config (
    config_id       INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 匹配条件（NULL = 不限制该条件）
    exchange        TEXT,                       -- SZ/SH/BJ
    board           TEXT,                       -- 主板/创业板/科创板/北交所
    is_st           BOOLEAN,
    min_list_days   INTEGER,                    -- 最小上市交易日数
    max_list_days   INTEGER,                    -- 最大上市交易日数

    -- 阈值
    limit_pct       REAL NOT NULL,              -- 涨跌幅阈值（%）

    -- 优先级（数字越大优先级越高）
    priority        INTEGER DEFAULT 0,

    -- 备注
    description     TEXT,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 默认配置数据
INSERT INTO price_limit_config (exchange, board, is_st, min_list_days, max_list_days, limit_pct, priority, description) VALUES
    (NULL, NULL, NULL, NULL, 5, 1000, 100, '新股前5个交易日：不限制'),
    (NULL, NULL, TRUE, 6, NULL, 5, 90, 'ST股：±5%'),
    ('BJ', NULL, NULL, 6, NULL, 30, 80, '北交所：±30%'),
    (NULL, '科创板', NULL, 6, NULL, 20, 70, '科创板：±20%'),
    (NULL, '创业板', NULL, 6, NULL, 20, 70, '创业板：±20%'),
    (NULL, NULL, NULL, 6, NULL, 10, 0, '默认（主板）：±10%');
```

### 6.2 Checksum 流式计算

```python
import hashlib

def file_md5_stream(path: str, chunk_size: int = 1024 * 1024) -> str:
    """
    流式计算文件 MD5（避免大文件一次性读入内存）

    chunk_size: 1MB 分块
    """
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
```

---

## 七、数据 Pipeline 流程

### 7.1 Pipeline 总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Daily Pipeline（每日收盘后）                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│   │   Tushare    │───▶│   Ingest     │───▶│   Curated    │             │
│   │   (Source)   │    │   (Extract)  │    │   (Load)     │             │
│   └──────────────┘    └──────────────┘    └──────────────┘             │
│                              │                    │                     │
│                              ▼                    ▼                     │
│                       ┌──────────────┐    ┌──────────────┐             │
│                       │  DQ Check    │    │   Features   │             │
│                       │  (Validate)  │    │   (Transform)│             │
│                       └──────────────┘    └──────────────┘             │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                         Weekly Pipeline（每周末）                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│   │  Compaction  │    │   Universe   │    │   Security   │             │
│   │  (dt→year)   │    │   Update     │    │   Refresh    │             │
│   └──────────────┘    └──────────────┘    └──────────────┘             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 任务依赖图

```python
# 每日任务
daily_tasks = {
    "sync_calendar":        [],                          # 无依赖
    "ingest_market_daily":  ["sync_calendar"],
    "ingest_adj_factor":    ["sync_calendar"],
    "ingest_daily_basic":   ["sync_calendar"],
    "dq_market_check":      ["ingest_market_daily"],
    "build_curated_market": ["ingest_market_daily", "ingest_adj_factor", "dq_market_check"],
    "build_features":       ["build_curated_market"],
}

# 每周任务
weekly_tasks = {
    "sync_securities":      [],                          # 刷新证券主数据
    "sync_universe":        ["sync_securities"],         # 刷新指数成分
    "compact_market":       [],                          # dt→year 合并
    "compact_adj_factor":   [],
}

# 每季任务（财报季后）
quarterly_tasks = {
    "ingest_income":        [],
    "ingest_balance":       [],
    "ingest_cashflow":      [],
    "build_fundamental":    ["ingest_income", "ingest_balance", "ingest_cashflow"],
}
```

### 7.3 核心 Pipeline 实现

#### 7.3.1 Security Master 管理（v1.4：src_code 主映射通道）

```python
class SecurityMaster:
    """
    证券主数据管理（v1.4：多数据源支持）

    核心原则：
    - sid 永不改变，是唯一身份标识
    - (source, src_code) 是外部稳定键，用于数据对接
    - symbol 仅作为展示标签，不参与数据映射

    v1.4 改进：
    - 主映射通道从 symbol -> sid 改为 (source, src_code) -> sid
    - 支持多数据源（tushare/ricequant/akshare）
    - resolve_sid 历史查询只走 symbol_changes，不短路当前映射
    """

    DEFAULT_SOURCE = "tushare"

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self._init_cache()

    def _init_cache(self):
        """初始化内存缓存"""
        # 主映射：(source, src_code) -> sid（仅活跃证券）
        df = pd.read_sql("""
            SELECT source, src_code, sid, symbol, list_open_seq
            FROM securities WHERE is_active = TRUE
        """, self.conn)

        # (source, src_code) -> sid
        self._src_code_to_sid: dict[tuple[str, str], int] = {
            (row['source'], row['src_code']): row['sid']
            for _, row in df.iterrows()
        }

        # sid -> (source, src_code, symbol, list_open_seq)
        self._sid_to_info: dict[int, dict] = {
            row['sid']: {
                'source': row['source'],
                'src_code': row['src_code'],
                'symbol': row['symbol'],
                'list_open_seq': row['list_open_seq'],
            }
            for _, row in df.iterrows()
        }

        # 历史 symbol/src_code 变更（用于 as_of 查询）
        df_history = pd.read_sql("""
            SELECT source, src_code, symbol, sid, effective_from, effective_to
            FROM symbol_changes
        """, self.conn)
        self._symbol_history = df_history

    def refresh_cache(self):
        """刷新缓存（symbol_changes 更新后调用）"""
        self._init_cache()

    # ========== 核心查询 API ==========

    def resolve_current_sid(
        self,
        src_code: str,
        source: str = None
    ) -> int | None:
        """
        解析当前有效的 sid（用于 ingestion）

        v1.4：以 (source, src_code) 作为主映射通道
        """
        source = source or self.DEFAULT_SOURCE
        return self._src_code_to_sid.get((source, src_code))

    def resolve_sid(
        self,
        src_code: str,
        as_of_date: str,
        source: str = None
    ) -> int | None:
        """
        解析历史时点的 sid（用于历史数据处理、审计）

        v1.4：不短路当前映射，只查 symbol_changes（权威历史来源）
        """
        source = source or self.DEFAULT_SOURCE

        # 查找历史映射（symbol_changes 是带有效期的权威来源）
        for _, row in self._symbol_history.iterrows():
            if row['source'] == source and row['src_code'] == src_code:
                eff_from = row['effective_from']
                eff_to = row['effective_to']
                if eff_from <= as_of_date and (eff_to is None or eff_to > as_of_date):
                    return row['sid']

        return None

    def get_current_src_code(self, sid: int) -> tuple[str, str] | None:
        """sid -> (source, src_code)"""
        info = self._sid_to_info.get(sid)
        if info:
            return (info['source'], info['src_code'])
        return None

    def get_current_symbol(self, sid: int) -> str | None:
        """sid -> 当前展示 symbol"""
        info = self._sid_to_info.get(sid)
        return info['symbol'] if info else None

    def get_list_open_seq(self, sid: int) -> int | None:
        """获取上市日交易日序号（用于 O(1) 计算 list_days）"""
        info = self._sid_to_info.get(sid)
        return info['list_open_seq'] if info else None

    def get_symbol_history(self, sid: int) -> list[dict]:
        """获取某 sid 的所有历史 symbol/src_code"""
        history = self._symbol_history[self._symbol_history['sid'] == sid]
        return history.to_dict('records')

    # ========== 注册与变更 API ==========

    def register_pending(
        self,
        src_code: str,
        first_seen_date: str,
        discovered_by: str,
        source: str = None
    ):
        """
        将未知 src_code 注册到待处理表（不直接污染 securities）

        v1.4：使用 (data_source, src_code) 作为主键
        """
        source = source or self.DEFAULT_SOURCE
        try:
            safe_execute(self.conn, """
                INSERT OR IGNORE INTO pending_symbols
                (data_source, src_code, first_seen_date, discovered_by)
                VALUES (?, ?, ?, ?)
            """, [source, src_code, first_seen_date, discovered_by])
        except Exception as e:
            print(f"Failed to register pending src_code {src_code}: {e}")

    def process_pending_symbols(self, securities_df: pd.DataFrame, source: str = None):
        """
        处理待注册证券（由 weekly sync_securities 调用）

        securities_df: 从数据源获取的完整证券信息
        """
        source = source or self.DEFAULT_SOURCE

        pending = pd.read_sql("""
            SELECT src_code FROM pending_symbols
            WHERE data_source = ? AND status = 'pending'
        """, self.conn, params=[source])

        for src_code in pending['src_code']:
            # Tushare 的 ts_code 就是 src_code
            info = securities_df[securities_df['ts_code'] == src_code]
            if len(info) > 0:
                row = info.iloc[0]
                self._register_security(
                    source=source,
                    src_code=src_code,
                    symbol=src_code.split('.')[0],  # 600000.SH -> 600000
                    name=row.get('name'),
                    exchange=src_code[-2:],  # SH/SZ/BJ
                    list_date=row.get('list_date'),
                    board=row.get('market'),
                )
                # 标记为已处理
                safe_execute(self.conn, """
                    UPDATE pending_symbols
                    SET status = 'processed', processed_at = datetime('now')
                    WHERE data_source = ? AND src_code = ?
                """, [source, src_code])
            else:
                # 未找到信息，标记为需关注
                safe_execute(self.conn, """
                    UPDATE pending_symbols
                    SET notes = 'Not found in stock_basic'
                    WHERE data_source = ? AND src_code = ?
                """, [source, src_code])

        self.refresh_cache()

    def _register_security(
        self,
        source: str,
        src_code: str,
        symbol: str,
        **kwargs
    ) -> int:
        """
        内部方法：注册新证券

        v1.4：必须写入 source + src_code
        """
        # 查找上市日的 open_seq
        list_date = kwargs.get('list_date')
        list_open_seq = None
        if list_date:
            row = self.conn.execute("""
                SELECT open_seq FROM trading_calendar
                WHERE trade_date = ? AND is_open = TRUE
            """, [list_date]).fetchone()
            list_open_seq = row[0] if row else None

        cursor = self.conn.execute("""
            INSERT INTO securities
            (source, src_code, symbol, name, display_name, exchange, list_date, list_open_seq, board, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, TRUE)
        """, [
            source,
            src_code,
            symbol,
            kwargs.get('name'),
            kwargs.get('name'),  # display_name 初始与 name 相同
            kwargs.get('exchange'),
            list_date,
            list_open_seq,
            kwargs.get('board'),
        ])

        sid = cursor.lastrowid

        # 记录初始 src_code/symbol
        self.conn.execute("""
            INSERT INTO symbol_changes (sid, source, src_code, symbol, effective_from)
            VALUES (?, ?, ?, ?, ?)
        """, [sid, source, src_code, symbol, list_date])

        self.conn.commit()
        return sid

    def handle_symbol_change(
        self,
        old_src_code: str,
        new_symbol: str,
        change_date: str,
        reason: str = None,
        source: str = None
    ):
        """
        处理 symbol 变更（src_code 通常不变，symbol 可能变）
        """
        source = source or self.DEFAULT_SOURCE
        sid = self.resolve_current_sid(old_src_code, source)
        if sid is None:
            raise ValueError(f"Unknown src_code: {old_src_code}")

        info = self._sid_to_info.get(sid)
        src_code = info['src_code']

        # 关闭旧记录有效期
        self.conn.execute("""
            UPDATE symbol_changes
            SET effective_to = ?
            WHERE sid = ? AND effective_to IS NULL
        """, [change_date, sid])

        # 插入新 symbol 记录
        self.conn.execute("""
            INSERT INTO symbol_changes (sid, source, src_code, symbol, effective_from, change_reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [sid, source, src_code, new_symbol, change_date, reason])

        # 更新主表当前 symbol
        self.conn.execute("""
            UPDATE securities
            SET symbol = ?, updated_at = datetime('now')
            WHERE sid = ?
        """, [new_symbol, sid])

        self.conn.commit()
        self.refresh_cache()

    # ========== 批量操作 API ==========

    def enrich_with_sid(
        self,
        lf: pl.LazyFrame,
        source: str = None,
        src_code_col: str = "src_code",
        as_of_date: str = None
    ) -> pl.LazyFrame:
        """
        为 LazyFrame 添加 sid 列

        v1.4：基于 src_code 映射，不再依赖 symbol
        """
        source = source or self.DEFAULT_SOURCE

        if as_of_date:
            # 历史模式：需要考虑 symbol_changes
            mapping_df = self._build_asof_mapping(source, as_of_date)
        else:
            # 当前模式：直接使用缓存
            mapping_data = [
                {"src_code": src_code, "sid": sid}
                for (s, src_code), sid in self._src_code_to_sid.items()
                if s == source
            ]
            mapping_df = pl.DataFrame(mapping_data) if mapping_data else pl.DataFrame({
                "src_code": [], "sid": []
            })

        return lf.join(
            mapping_df.lazy(),
            left_on=src_code_col,
            right_on="src_code",
            how="left"
        )

    def _build_asof_mapping(self, source: str, as_of_date: str) -> pl.DataFrame:
        """构建历史时点的 src_code -> sid 映射"""
        mapping = {}

        for _, row in self._symbol_history.iterrows():
            if row['source'] != source:
                continue
            eff_from = row['effective_from']
            eff_to = row['effective_to']
            if eff_from <= as_of_date and (eff_to is None or eff_to > as_of_date):
                mapping[row['src_code']] = row['sid']

        return pl.DataFrame({
            "src_code": list(mapping.keys()),
            "sid": list(mapping.values())
        })
```

#### 7.3.2 字段映射层（Tushare -> Canonical）

```python
# Tushare 字段到标准字段的映射
# v1.4：ts_code 映射为 src_code（数据源原始代码）
TUSHARE_FIELD_MAPPING = {
    "market_daily": {
        "ts_code": "src_code",        # v1.4：外部稳定键
        "trade_date": "trade_date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "vol": "volume",              # 注意：Tushare 单位是手
        "amount": "amount",           # 单位：千元
        "pct_chg": "pct_change",      # 注意字段名差异
        "change": "_change",          # 涨跌额，不常用
    },
    "adj_factor": {
        "ts_code": "src_code",        # v1.4：外部稳定键
        "trade_date": "trade_date",
        "adj_factor": "adj_factor",
    }
}

# 单位转换配置
UNIT_CONVERSIONS = {
    "volume": lambda x: x * 100,      # 手 -> 股
    "amount": lambda x: x * 1000,     # 千元 -> 元
}


def standardize_tushare_df(
    df: pd.DataFrame,
    table_type: str,
    source: str = "tushare"
) -> pl.LazyFrame:
    """
    标准化 Tushare 返回的 DataFrame

    1. 字段重命名（ts_code -> src_code）
    2. 单位转换
    3. 类型强制
    4. 添加 source 字段
    """
    mapping = TUSHARE_FIELD_MAPPING.get(table_type, {})

    # 重命名
    df = df.rename(columns=mapping)

    # 转为 Polars
    lf = pl.from_pandas(df).lazy()

    # 日期转换
    if "trade_date" in df.columns:
        lf = lf.with_columns(
            pl.col("trade_date").str.to_date("%Y%m%d")
        )

    # 单位转换
    for col, converter in UNIT_CONVERSIONS.items():
        if col in df.columns:
            lf = lf.with_columns(
                pl.col(col).map_batches(converter)
            )

    # 添加 source
    lf = lf.with_columns(pl.lit(source).alias("source"))

    return lf
```

#### 7.3.3 数据摄取（三段式原子提交）

```python
class TushareIngestion:
    """
    Tushare 数据摄取

    核心流程：staging -> DQ -> atomic commit
    确保 Curated 层始终"发布即可信"
    """

    def __init__(self, token: str, master: SecurityMaster, data_root: Path, conn: sqlite3.Connection):
        self.pro = ts.pro_api(token)
        self.master = master
        self.data_root = data_root
        self.conn = conn
        self.rate_limiter = RateLimiter(calls_per_minute=180)
        self.dq_checker = DataQualityChecker(conn)

    async def ingest_market_daily(self, trade_date: str, run_id: str) -> dict:
        """
        摄取日线行情（三段式原子提交）

        1. 拉取 & 标准化 -> DataFrame
        2. DQ 检查 -> pass/fail
        3. 通过则写入；失败则仅记录，不污染 Curated
        """

        # ========== 阶段1：拉取 & 标准化 ==========
        await self.rate_limiter.acquire()
        raw_df = self.pro.daily(trade_date=trade_date)

        if raw_df.empty:
            return {"status": "skip", "reason": "no_data", "rows": 0}

        # 标准化（字段映射、单位转换，ts_code -> src_code）
        lf = standardize_tushare_df(raw_df, "market_daily")

        # 添加 sid（v1.4：基于 source + src_code 映射）
        lf = self.master.enrich_with_sid(lf, source="tushare")

        # 收集为 DataFrame 以便 DQ 检查
        df = lf.collect()

        # 处理未知 src_code（注册到 pending，不直接污染 securities）
        unmapped = df.filter(pl.col("sid").is_null())
        if len(unmapped) > 0:
            for src_code in unmapped["src_code"].unique().to_list():
                self.master.register_pending(src_code, trade_date, "ingest_market_daily", source="tushare")

            # 过滤掉未映射的行（本次不写入，等 sync_securities 后重跑）
            df = df.filter(pl.col("sid").is_not_null())

            if len(df) == 0:
                return {"status": "partial", "reason": "all_unmapped", "pending": len(unmapped)}

        # 排序（优化 Parquet 读取性能）
        df = df.sort(["sid", "trade_date"])

        # ========== 阶段2：DQ 检查 ==========
        dq_result = self.dq_checker.check_market_daily(df, run_id)

        # DQ 失败（有 error 级别异常）：不写入，仅记录
        if dq_result["error_count"] > 0:
            self._record_failed_run(run_id, trade_date, dq_result)
            return {
                "status": "dq_failed",
                "dq_summary": dq_result,
                "rows": len(df)
            }

        # ========== 阶段3：原子提交 ==========
        output_path = self._atomic_write(
            df=df,
            table="curated/market/daily",
            partition_key=f"dt={trade_date}",
            run_id=run_id
        )

        return {
            "status": "success",
            "rows": len(df),
            "path": str(output_path),
            "dq_summary": dq_result
        }

    def _atomic_write(
        self,
        df: pl.DataFrame,
        table: str,
        partition_key: str,
        run_id: str
    ) -> Path:
        """
        原子写入：staging -> os.replace -> 记录版本

        v1.4：使用 os.replace 实现真正的原子替换，避免 unlink+rename 的竞态窗口
        """
        import os

        final_dir = self.data_root / table / partition_key
        final_path = final_dir / "data.parquet"
        staging_dir = self.data_root / "_staging" / run_id / table / partition_key
        staging_path = staging_dir / "data.parquet"

        # 1. 写入 staging
        staging_dir.mkdir(parents=True, exist_ok=True)
        df.write_parquet(staging_path, compression="zstd")

        # 2. 原子替换（v1.4：使用 os.replace，同文件系统上是原子操作）
        final_dir.mkdir(parents=True, exist_ok=True)
        os.replace(str(staging_path), str(final_path))

        # 3. 清理 staging
        try:
            staging_dir.rmdir()
            (self.data_root / "_staging" / run_id / table).rmdir()
            (self.data_root / "_staging" / run_id).rmdir()
        except OSError:
            pass  # 目录非空，忽略

        # 4. 记录版本
        self._record_data_version(
            table_name=table,
            partition_key=partition_key,
            file_path=str(final_path),
            df=df,
            run_id=run_id
        )

        return final_path

    def _record_data_version(
        self,
        table_name: str,
        partition_key: str,
        file_path: str,
        df: pl.DataFrame,
        run_id: str
    ):
        """
        记录数据版本

        v1.4：使用流式 checksum 计算，避免大文件内存爆炸
        """
        # 使用流式计算 checksum
        checksum = file_md5_stream(file_path)

        safe_execute(self.conn, """
            INSERT OR REPLACE INTO data_versions
            (table_name, partition_key, file_path, file_size, row_count,
             min_date, max_date, sid_count, checksum, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, [
            table_name,
            partition_key,
            file_path,
            Path(file_path).stat().st_size,
            len(df),
            str(df["trade_date"].min()),
            str(df["trade_date"].max()),
            df["sid"].n_unique(),
            checksum,
            run_id
        ])
        self.conn.commit()

    def _record_failed_run(self, run_id: str, trade_date: str, dq_result: dict):
        """记录失败的运行"""
        self.conn.execute("""
            UPDATE pipeline_runs
            SET status = 'dq_failed',
                dq_summary = ?,
                dq_passed = FALSE,
                finished_at = datetime('now')
            WHERE run_id = ?
        """, [json.dumps(dq_result), run_id])
        self.conn.commit()
```

#### 7.3.4 数据质量检查（动态涨跌幅阈值）

```python
class DataQualityChecker:
    """
    数据质量检查（v1.3：制度口径感知）

    核心改进：
    - 动态涨跌幅阈值（基于 board/exchange/list_days/is_st）
    - 复权因子连续性检查
    - 使用 safe_executemany 避免锁竞争
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._load_limit_config()

    def _load_limit_config(self):
        """加载涨跌幅配置到内存（按优先级排序）"""
        rows = self.conn.execute("""
            SELECT exchange, board, is_st, min_list_days, max_list_days, limit_pct
            FROM price_limit_config
            ORDER BY priority DESC
        """).fetchall()
        self._limit_rules = rows

    # 注意：_compute_list_days 已移除，改用 O(1) 计算方案
    # list_days = trade_open_seq - list_open_seq + 1

    def _get_limit_pct(self, exchange: str, board: str, is_st: bool, list_days: int) -> float:
        """
        根据配置表动态计算涨跌幅阈值

        匹配规则：按优先级从高到低，找到第一个匹配的规则
        """
        for rule in self._limit_rules:
            r_exchange, r_board, r_is_st, r_min_days, r_max_days, r_limit = rule

            # 条件匹配（NULL = 不限制）
            if r_exchange is not None and r_exchange != exchange:
                continue
            if r_board is not None and r_board != board:
                continue
            if r_is_st is not None and r_is_st != is_st:
                continue
            if r_min_days is not None and list_days < r_min_days:
                continue
            if r_max_days is not None and list_days > r_max_days:
                continue

            return r_limit

        # 默认值（应该不会走到这里，因为有默认配置）
        return 10.0

    def _get_trade_date_open_seq(self, trade_date: str) -> int | None:
        """获取交易日的 open_seq"""
        result = self.conn.execute("""
            SELECT open_seq FROM trading_calendar WHERE trade_date = ?
        """, [trade_date]).fetchone()
        return result[0] if result else None

    def _fetch_security_meta(self, sids: list[int]) -> pl.DataFrame:
        """
        批量获取证券元数据

        v1.4：返回 list_open_seq 用于 O(1) 计算 list_days
        """
        if not sids:
            return pl.DataFrame({
                "sid": [], "exchange": [], "board": [], "list_open_seq": [], "is_st": []
            })

        placeholders = ",".join(["?"] * len(sids))
        rows = self.conn.execute(f"""
            SELECT sid, exchange, board, list_open_seq, is_st
            FROM securities
            WHERE sid IN ({placeholders})
        """, sids).fetchall()

        return pl.DataFrame(
            rows,
            schema=["sid", "exchange", "board", "list_open_seq", "is_st"],
            orient="row"
        )

    def check_market_daily(self, df: pl.DataFrame, run_id: str) -> dict:
        """
        检查日线数据质量（v1.4：O(1) 计算 list_days）

        返回：
            - error_count > 0：DQ 失败，不应写入
            - warning_count > 0：有告警，可写入但需关注
        """
        anomalies = []
        trade_date = str(df["trade_date"].min()) if len(df) > 0 else None

        # ========== 1. OHLC 合法性（error 级别）==========
        invalid_ohlc = df.filter(
            (pl.col("high") < pl.col("low")) |
            (pl.col("high") < pl.col("open")) |
            (pl.col("high") < pl.col("close")) |
            (pl.col("low") > pl.col("open")) |
            (pl.col("low") > pl.col("close"))
        )
        for row in invalid_ohlc.iter_rows(named=True):
            anomalies.append({
                "run_id": run_id,
                "table_name": "market_daily",
                "sid": row["sid"],
                "src_code": row.get("src_code"),
                "trade_date": str(row["trade_date"]),
                "rule_name": "ohlc_invalid",
                "severity": "error",
                "detail": json.dumps({
                    "open": row["open"], "high": row["high"],
                    "low": row["low"], "close": row["close"]
                }),
                "action": "blocked"
            })

        # ========== 2. 动态涨跌幅阈值（v1.4：O(1) 计算）==========
        if "pct_change" in df.columns and trade_date:
            sids = df.select("sid").drop_nulls().unique().to_series().to_list()
            meta = self._fetch_security_meta(sids)

            # 获取当日的 open_seq（一次查询）
            trade_open_seq = self._get_trade_date_open_seq(trade_date)

            # O(1) 计算每个 sid 的 list_days 和 limit_pct
            limit_data = []
            for row in meta.iter_rows(named=True):
                # O(1) 计算：list_days = trade_open_seq - list_open_seq + 1
                list_open_seq = row["list_open_seq"]
                if list_open_seq is not None and trade_open_seq is not None:
                    list_days = trade_open_seq - list_open_seq + 1
                else:
                    list_days = 999999  # 默认值（不限制）

                limit_pct = self._get_limit_pct(
                    row["exchange"], row["board"],
                    bool(row["is_st"]), list_days
                )
                limit_data.append({
                    "sid": row["sid"],
                    "list_days": list_days,
                    "limit_pct": limit_pct
                })

            if limit_data:
                limit_df = pl.DataFrame(limit_data)
                df_with_limit = df.join(limit_df, on="sid", how="left")

                # 超过动态阈值的记录
                extreme = df_with_limit.filter(
                    pl.col("pct_change").abs() > pl.col("limit_pct")
                )

                for row in extreme.iter_rows(named=True):
                    anomalies.append({
                        "run_id": run_id,
                        "table_name": "market_daily",
                        "sid": row["sid"],
                        "src_code": row.get("src_code"),
                        "trade_date": str(row["trade_date"]),
                        "rule_name": "price_jump_dynamic",
                        "severity": "warning",  # v1.4：一律 warning，不阻塞写入
                        "detail": json.dumps({
                            "pct_change": row["pct_change"],
                            "limit_pct": row["limit_pct"],
                            "list_days": row.get("list_days")
                        }),
                        "action": "flagged"
                    })

        # ========== 3. 负值检查（error 级别）==========
        negative_values = df.filter(
            (pl.col("open") < 0) | (pl.col("high") < 0) |
            (pl.col("low") < 0) | (pl.col("close") < 0) |
            (pl.col("volume") < 0) | (pl.col("amount") < 0)
        )
        for row in negative_values.iter_rows(named=True):
            anomalies.append({
                "run_id": run_id,
                "table_name": "market_daily",
                "sid": row["sid"],
                "src_code": row.get("src_code"),
                "trade_date": str(row["trade_date"]),
                "rule_name": "negative_value",
                "severity": "error",
                "detail": json.dumps({
                    "open": row["open"], "close": row["close"],
                    "volume": row["volume"]
                }),
                "action": "blocked"
            })

        # ========== 4. 空值统计 ==========
        null_counts = {col: df[col].null_count() for col in df.columns}
        critical_nulls = {
            k: v for k, v in null_counts.items()
            if k in ["sid", "trade_date", "close"] and v > 0
        }

        # ========== 5. 批量写入异常记录（使用安全写入）==========
        if anomalies:
            safe_executemany(self.conn, """
                INSERT INTO dq_anomalies
                (run_id, table_name, sid, src_code, trade_date, rule_name, severity, detail, action)
                VALUES (:run_id, :table_name, :sid, :src_code, :trade_date, :rule_name, :severity, :detail, :action)
            """, anomalies)

        # 统计结果
        error_count = sum(1 for a in anomalies if a["severity"] == "error")
        warning_count = sum(1 for a in anomalies if a["severity"] == "warning")

        return {
            "total_rows": len(df),
            "anomaly_count": len(anomalies),
            "error_count": error_count,
            "warning_count": warning_count,
            "null_counts": null_counts,
            "critical_nulls": critical_nulls,
            "passed": error_count == 0 and len(critical_nulls) == 0
        }

    def check_adj_factor(self, df: pl.DataFrame, run_id: str) -> dict:
        """
        检查复权因子数据质量

        关键检查：
        - 无 null/0 值
        - 与交易日历的覆盖率
        """
        anomalies = []

        # 1. null/0 值检查（error 级别）
        invalid = df.filter(
            pl.col("adj_factor").is_null() | (pl.col("adj_factor") == 0)
        )
        for row in invalid.iter_rows(named=True):
            anomalies.append({
                "run_id": run_id,
                "table_name": "adj_factor",
                "sid": row["sid"],
                "src_code": row.get("src_code"),
                "trade_date": str(row["trade_date"]),
                "rule_name": "adj_factor_invalid",
                "severity": "error",
                "detail": json.dumps({"adj_factor": row["adj_factor"]}),
                "action": "blocked"
            })

        # 2. 覆盖率检查（需要与交易日历对比）
        # TODO: 实现交易日历覆盖率检查

        if anomalies:
            safe_executemany(self.conn, """
                INSERT INTO dq_anomalies
                (run_id, table_name, sid, src_code, trade_date, rule_name, severity, detail, action)
                VALUES (:run_id, :table_name, :sid, :src_code, :trade_date, :rule_name, :severity, :detail, :action)
            """, anomalies)

        error_count = sum(1 for a in anomalies if a["severity"] == "error")

        return {
            "total_rows": len(df),
            "error_count": error_count,
            "passed": error_count == 0
        }
```

#### 7.3.5 数据读取接口（v1.3：路径裁剪 + 强校验）

```python
class MarketDataReader:
    """
    行情数据读取（v1.3：性能优化 + 健壮性增强）

    核心策略：derived 优先，curated 精准补齐

    v1.3 改进：
    - 使用 compaction_state watermark 裁剪 curated 路径（避免 dt=* 全扫描）
    - base_factor 强校验（null/0 直接报错）
    """

    def __init__(self, master: SecurityMaster, data_root: Path, conn: sqlite3.Connection):
        self.master = master
        self.data_root = data_root
        self.conn = conn

    # ========== Compaction State 管理 ==========

    def _get_compaction_watermark(self, table: str = "market/daily") -> str | None:
        """获取 compaction watermark（最后已合并的日期）"""
        result = self.conn.execute("""
            SELECT last_compacted_dt FROM compaction_state WHERE table_name = ?
        """, [table]).fetchone()
        return result[0] if result and result[0] else None

    def _get_available_derived_years(self, table: str = "market/daily") -> set[int]:
        """获取已有的 derived 年度分区"""
        derived_path = self.data_root / f"derived/{table}"
        if not derived_path.exists():
            return set()

        years = set()
        for p in derived_path.glob("year=*/data.parquet"):
            year_str = p.parent.name.replace("year=", "")
            try:
                years.add(int(year_str))
            except ValueError:
                continue
        return years

    def _list_trading_dates(self, start_date: str, end_date: str) -> list[str]:
        """获取交易日列表（用于精准路径生成）"""
        rows = self.conn.execute("""
            SELECT trade_date FROM trading_calendar
            WHERE is_open = TRUE AND trade_date BETWEEN ? AND ?
            ORDER BY trade_date
        """, [start_date, end_date]).fetchall()
        return [r[0] for r in rows]

    def _build_curated_paths(self, table: str, dates: list[str]) -> list[str]:
        """构建 curated dt 文件路径列表（只返回存在的文件）"""
        paths = []
        for d in dates:
            p = self.data_root / f"curated/{table}/dt={d}/data.parquet"
            if p.exists():
                paths.append(str(p))
        return paths

    def _get_next_trade_date(self, date: str) -> str | None:
        """获取下一个交易日（用于 watermark 裁剪）"""
        result = self.conn.execute("""
            SELECT next_trade_date FROM trading_calendar WHERE trade_date = ?
        """, [date]).fetchone()
        return result[0] if result and result[0] else None

    # ========== 查询接口 ==========

    def query_by_src_code(
        self,
        src_code: str,
        start_date: str = None,
        end_date: str = None,
        fields: list[str] = None,
        source: str = "tushare"
    ) -> pl.DataFrame:
        """按 src_code 查询（自动解析为 sid）"""
        sid = self.master.resolve_current_sid(src_code, source)
        if sid is None:
            raise ValueError(f"Unknown src_code: {src_code} (source={source})")
        return self.query_by_sid(sid, start_date, end_date, fields)

    def query_by_symbol(
        self,
        symbol: str,
        start_date: str = None,
        end_date: str = None,
        fields: list[str] = None,
        source: str = "tushare"
    ) -> pl.DataFrame:
        """
        按 symbol 查询（兼容接口，内部转为 src_code 查询）

        注意：symbol 可能不唯一，建议使用 query_by_src_code
        """
        # 尝试构造 src_code（Tushare: symbol.exchange）
        # 这里简化处理，假设调用者传入的是 src_code 格式
        return self.query_by_src_code(symbol, start_date, end_date, fields, source)

    def query_by_sid(
        self,
        sid: int,
        start_date: str = None,
        end_date: str = None,
        fields: list[str] = None
    ) -> pl.DataFrame:
        """
        按 sid 查询（v1.4：优化 watermark 裁剪逻辑）
        """
        dfs = []

        start_date = start_date or "2010-01-01"
        end_date = end_date or "2099-12-31"
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])

        derived_years = self._get_available_derived_years()
        watermark = self._get_compaction_watermark("market/daily")

        # 1. 从 derived 读取已 compaction 的年度
        for year in range(start_year, end_year + 1):
            if year in derived_years:
                year_path = self.data_root / f"derived/market/daily/year={year}/data.parquet"
                if year_path.exists():
                    lf = (
                        pl.scan_parquet(str(year_path))
                        .filter(pl.col("sid") == sid)
                        .filter(pl.col("trade_date") >= start_date)
                        .filter(pl.col("trade_date") <= end_date)
                    )
                    dfs.append(lf)

        # 2. 从 curated 精准补齐（v1.4：简化 watermark 裁剪逻辑）
        # 计算 curated 扫描的起始日期
        if watermark:
            # 获取 watermark 的下一个交易日
            next_date = self._get_next_trade_date(watermark)
            curated_start = max(start_date, next_date) if next_date else start_date
        else:
            curated_start = start_date

        if curated_start <= end_date:
            # 使用交易日历生成精准路径列表（不再用 dt=*）
            scan_dates = self._list_trading_dates(curated_start, end_date)

            if scan_dates:
                dt_files = self._build_curated_paths("market/daily", scan_dates)
                if dt_files:
                    lf = (
                        pl.scan_parquet(dt_files)
                        .filter(pl.col("sid") == sid)
                        .filter(pl.col("trade_date") >= start_date)
                        .filter(pl.col("trade_date") <= end_date)
                    )
                    dfs.append(lf)

        # 3. 合并并去重
        if not dfs:
            return pl.DataFrame()

        combined = pl.concat(dfs)
        if fields:
            combined = combined.select(["sid", "trade_date", "symbol"] + fields)

        return (
            combined
            .unique(subset=["sid", "trade_date"])
            .sort("trade_date")
            .collect()
        )

    def query_universe(
        self,
        sids: list[int],
        start_date: str,
        end_date: str,
        fields: list[str] = None
    ) -> pl.DataFrame:
        """
        批量查询（回测用，v1.4：watermark 裁剪逻辑统一）
        """
        derived_years = self._get_available_derived_years()
        watermark = self._get_compaction_watermark("market/daily")

        start_year = int(start_date[:4])
        end_year = int(end_date[:4])

        dfs = []

        # 从 derived 读取
        for year in range(start_year, end_year + 1):
            if year in derived_years:
                year_path = self.data_root / f"derived/market/daily/year={year}/data.parquet"
                if year_path.exists():
                    lf = (
                        pl.scan_parquet(str(year_path))
                        .filter(pl.col("sid").is_in(sids))
                        .filter(pl.col("trade_date") >= start_date)
                        .filter(pl.col("trade_date") <= end_date)
                    )
                    dfs.append(lf)

        # 从 curated 精准补齐（v1.4：与 query_by_sid 统一逻辑）
        if watermark:
            next_date = self._get_next_trade_date(watermark)
            curated_start = max(start_date, next_date) if next_date else start_date
        else:
            curated_start = start_date

        if curated_start <= end_date:
            scan_dates = self._list_trading_dates(curated_start, end_date)

            if scan_dates:
                dt_files = self._build_curated_paths("market/daily", scan_dates)
                if dt_files:
                    lf = (
                        pl.scan_parquet(dt_files)
                        .filter(pl.col("sid").is_in(sids))
                        .filter(pl.col("trade_date") >= start_date)
                        .filter(pl.col("trade_date") <= end_date)
                    )
                    dfs.append(lf)

        if not dfs:
            return pl.DataFrame()

        combined = pl.concat(dfs)
        if fields:
            combined = combined.select(["sid", "trade_date", "symbol"] + fields)

        return (
            combined
            .unique(subset=["sid", "trade_date"])
            .sort(["trade_date", "sid"])
            .collect()
        )

    def query_with_adj(
        self,
        sid: int,
        start_date: str,
        end_date: str,
        adj_method: str = "hfq",
        qfq_base: str = "end_date"
    ) -> pl.DataFrame:
        """
        查询含复权价格（v1.3：base_factor 强校验）

        adj_method:
            - hfq: 后复权（price * adj_factor），适合研究/回测
            - qfq: 前复权（price * adj_factor / base_factor），适合展示

        qfq_base（仅 qfq 模式）:
            - end_date: 以查询区间末日为基准（默认）

        重要：回测时 qfq_base 必须是"当期可见的最后交易日"，避免偷看未来
        """
        # 行情数据
        market = self.query_by_sid(sid, start_date, end_date)

        if market.is_empty():
            return market

        # 复权因子
        adj = self._query_adj_factor(sid, start_date, end_date)

        if adj.is_empty():
            return market

        # Join
        result = market.join(adj, on=["sid", "trade_date"], how="left")

        # 计算复权价格
        if adj_method == "hfq":
            # 后复权：price * adj_factor
            result = result.with_columns([
                (pl.col("open") * pl.col("adj_factor")).alias("open_adj"),
                (pl.col("high") * pl.col("adj_factor")).alias("high_adj"),
                (pl.col("low") * pl.col("adj_factor")).alias("low_adj"),
                (pl.col("close") * pl.col("adj_factor")).alias("close_adj"),
            ])
        elif adj_method == "qfq":
            # 前复权：确定基准因子（v1.3：强校验）
            if qfq_base == "end_date":
                end_dt = result["trade_date"].max()
                base_series = result.filter(
                    pl.col("trade_date") == end_dt
                ).select("adj_factor").to_series()

                base_factor = base_series[0] if len(base_series) > 0 else None

                # 强校验：null/0 直接报错
                self._assert_valid_base_factor(base_factor, sid, str(end_dt))
            else:
                raise ValueError(f"Unknown qfq_base: {qfq_base}")

            result = result.with_columns([
                (pl.col("open") * pl.col("adj_factor") / base_factor).alias("open_adj"),
                (pl.col("high") * pl.col("adj_factor") / base_factor).alias("high_adj"),
                (pl.col("low") * pl.col("adj_factor") / base_factor).alias("low_adj"),
                (pl.col("close") * pl.col("adj_factor") / base_factor).alias("close_adj"),
            ])

        return result

    def _assert_valid_base_factor(self, base_factor: float | None, sid: int, end_date: str):
        """强校验 base_factor（v1.3 新增）"""
        if base_factor is None or base_factor == 0:
            raise ValueError(
                f"Invalid base_factor for sid={sid} at end_date={end_date}. "
                f"Likely missing adj_factor bars. Please run: "
                f"backfill_range('adjustment/factor', ...) to fix."
            )

    def _query_adj_factor(self, sid: int, start_date: str, end_date: str) -> pl.DataFrame:
        """查询复权因子（使用路径裁剪）"""
        watermark = self._get_compaction_watermark("adjustment/factor")

        dfs = []

        # derived 年度数据
        derived_years = self._get_available_derived_years("adjustment/factor")
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])

        for year in range(start_year, end_year + 1):
            if year in derived_years:
                year_path = self.data_root / f"derived/adjustment/factor/year={year}/data.parquet"
                if year_path.exists():
                    lf = (
                        pl.scan_parquet(str(year_path))
                        .filter(pl.col("sid") == sid)
                        .filter(pl.col("trade_date") >= start_date)
                        .filter(pl.col("trade_date") <= end_date)
                    )
                    dfs.append(lf)

        # curated 补齐
        curated_start = watermark if watermark else start_date
        if curated_start < end_date:
            scan_dates = self._list_trading_dates(curated_start, end_date)
            if watermark:
                scan_dates = [d for d in scan_dates if d > watermark]

            if scan_dates:
                dt_files = self._build_curated_paths("adjustment/factor", scan_dates)
                if dt_files:
                    lf = (
                        pl.scan_parquet(dt_files)
                        .filter(pl.col("sid") == sid)
                        .filter(pl.col("trade_date") >= start_date)
                        .filter(pl.col("trade_date") <= end_date)
                    )
                    dfs.append(lf)

        if not dfs:
            return pl.DataFrame()

        return (
            pl.concat(dfs)
            .unique(subset=["sid", "trade_date"])
            .select(["sid", "trade_date", "adj_factor"])
            .collect()
        )
```
```

---

## 八、Compaction 策略

### 8.1 dt → year 合并

```python
class Compactor:
    """分区合并"""

    def __init__(self, data_root: Path, conn: sqlite3.Connection):
        self.data_root = data_root
        self.conn = conn

    def compact_to_year(self, table: str, year: int):
        """将 dt 分区合并为 year 分区"""

        # 源路径
        dt_path = self.data_root / f"curated/{table}/dt=*"

        # 读取该年所有数据
        df = (
            pl.scan_parquet(str(dt_path / "data.parquet"))
            .filter(pl.col("trade_date").dt.year() == year)
            .sort(["trade_date", "sid"])
            .collect()
        )

        if len(df) == 0:
            return {"status": "skip", "reason": "no_data"}

        # 写入 derived（使用 zstd 压缩）
        output_path = self.data_root / f"derived/{table}/year={year}/data.parquet"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(output_path, compression="zstd")

        # 计算 checksum（流式）
        checksum = file_md5_stream(str(output_path))

        # 记录版本
        last_dt = str(df["trade_date"].max())

        safe_execute(self.conn, """
            INSERT OR REPLACE INTO data_versions
            (table_name, partition_key, file_path, file_size, row_count,
             min_date, max_date, checksum, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, [
            f"derived/{table}",
            f"year={year}",
            str(output_path),
            output_path.stat().st_size,
            len(df),
            str(df["trade_date"].min()),
            last_dt,
            checksum,
        ])

        # 更新 compaction_state（v1.3 新增：Reader 路径裁剪的关键）
        self._update_compaction_state(table, last_dt, year)

        return {
            "status": "success",
            "rows": len(df),
            "path": str(output_path),
            "last_compacted_dt": last_dt
        }

    @retry_sqlite_locked()
    def _update_compaction_state(self, table: str, last_dt: str, year: int):
        """更新 compaction watermark"""
        self.conn.execute("""
            INSERT INTO compaction_state (table_name, last_compacted_dt, last_compacted_year, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(table_name) DO UPDATE SET
                last_compacted_dt = CASE
                    WHEN excluded.last_compacted_dt > compaction_state.last_compacted_dt
                    THEN excluded.last_compacted_dt
                    ELSE compaction_state.last_compacted_dt
                END,
                last_compacted_year = CASE
                    WHEN excluded.last_compacted_year > compaction_state.last_compacted_year
                    THEN excluded.last_compacted_year
                    ELSE compaction_state.last_compacted_year
                END,
                updated_at = datetime('now')
        """, [table, last_dt, year])
        self.conn.commit()
```

---

## 九、回补策略（Backfill）

### 9.1 回补类型

| 类型 | 说明 | 触发条件 |
|-----|------|---------|
| Range Backfill | 按日期范围回补 | 发现数据缺失 |
| Symbol Backfill | 按证券回补 | 新增证券需要历史数据 |
| Rule Backfill | 规则变更回补 | 清洗逻辑或Schema变更 |

### 9.2 实现

```python
class Backfiller:
    """数据回补"""

    def __init__(self, ingestion: TushareIngestion, conn: sqlite3.Connection):
        self.ingestion = ingestion
        self.conn = conn

    async def backfill_range(
        self,
        table: str,
        start_date: str,
        end_date: str
    ):
        """按日期范围回补"""

        # 获取交易日列表
        trading_dates = self._get_trading_dates(start_date, end_date)

        for dt in trading_dates:
            result = await self.ingestion.ingest_market_daily(dt)
            print(f"Backfill {dt}: {result['status']}")

    def _get_trading_dates(self, start: str, end: str) -> list[str]:
        """获取交易日列表"""
        result = self.conn.execute("""
            SELECT trade_date FROM trading_calendar
            WHERE trade_date BETWEEN ? AND ?
              AND is_open = TRUE
            ORDER BY trade_date
        """, [start, end]).fetchall()
        return [r[0] for r in result]
```

---

## 十、使用示例

### 10.1 初始化

```python
from pathlib import Path
import sqlite3

# 初始化
DATA_ROOT = Path("/data/ditto")
META_DB = DATA_ROOT / "meta/ditto.sqlite"

# 创建元数据库（带并发优化）
conn = init_meta_db(str(META_DB))

# 初始化组件
master = SecurityMaster(str(META_DB))
reader = MarketDataReader(master, DATA_ROOT, conn)
```

### 10.2 查询数据

```python
# 按 symbol 查询（自动解析 sid）
df = reader.query_by_symbol("000001.SZ", "2024-01-01", "2024-06-30")

# 按 sid 查询（推荐用于策略代码）
df = reader.query_by_sid(1, "2024-01-01", "2024-06-30")

# 批量查询（回测场景）
universe_sids = [1, 2, 3, 4, 5]  # 从 universe 表获取
df = reader.query_universe(universe_sids, "2024-01-01", "2024-06-30")

# 含复权价格（后复权，研究/回测用）
df = reader.query_with_adj(1, "2024-01-01", "2024-06-30", adj_method="hfq")

# 含复权价格（前复权，明确基准日）
df = reader.query_with_adj(
    sid=1,
    start_date="2024-01-01",
    end_date="2024-06-30",
    adj_method="qfq",
    qfq_base="end_date"  # 以查询区间末日为基准
)
```

### 10.3 PIT 财务查询

```python
def query_pit_fundamental(
    sid: int,
    as_of_date: str,
    metrics: list[str] = None,
    periods: int = 1
) -> pl.DataFrame:
    """
    获取某时点能看到的财务数据（PIT）

    关键：只返回 announce_date <= as_of_date 的数据
    """
    lf = pl.scan_parquet("curated/fundamental/income/data.parquet")

    lf = (
        lf
        .filter(pl.col("sid") == sid)
        .filter(pl.col("announce_date") <= as_of_date)  # PIT 约束
        .sort("report_period", descending=True)
        .head(periods)
    )

    if metrics:
        lf = lf.select(["sid", "report_period", "announce_date"] + metrics)

    return lf.collect()

# 使用：获取2024年3月1日时点能看到的最新ROE
roe = query_pit_fundamental(
    sid=1,
    as_of_date="2024-03-01",
    metrics=["roe", "net_profit"],
    periods=1
)
```

### 10.4 运行 Pipeline

```python
import uuid
from datetime import datetime

async def run_daily_pipeline(trade_date: str):
    """每日 Pipeline"""
    run_id = str(uuid.uuid4())

    # 记录开始
    conn.execute("""
        INSERT INTO pipeline_runs (run_id, task_name, target_table, date_range, status, started_at)
        VALUES (?, 'daily_pipeline', 'curated/market/daily', ?, 'running', datetime('now'))
    """, [run_id, trade_date])
    conn.commit()

    try:
        # 初始化组件
        ingestion = TushareIngestion(
            token=TUSHARE_TOKEN,
            master=master,
            data_root=DATA_ROOT,
            conn=conn
        )

        # 执行摄取
        result = await ingestion.ingest_market_daily(trade_date, run_id)

        # 更新状态
        conn.execute("""
            UPDATE pipeline_runs
            SET status = ?, rows_written = ?, dq_summary = ?,
                dq_passed = ?, finished_at = datetime('now')
            WHERE run_id = ?
        """, [
            result["status"],
            result.get("rows", 0),
            json.dumps(result.get("dq_summary")),
            result.get("dq_summary", {}).get("passed", False),
            run_id
        ])
        conn.commit()

        return result

    except Exception as e:
        conn.execute("""
            UPDATE pipeline_runs
            SET status = 'failed', error_msg = ?, finished_at = datetime('now')
            WHERE run_id = ?
        """, [str(e), run_id])
        conn.commit()
        raise

# 运行
result = await run_daily_pipeline("2024-01-02")
print(f"Result: {result}")
```

---

## 附录 A：术语表

| 术语 | 英文 | 说明 |
|-----|------|------|
| sid | Security ID | 内部唯一证券标识，永不改变 |
| symbol | Symbol/Ticker | 外部交易代码，可能变更 |
| PIT | Point-in-Time | 时点数据，避免未来信息泄露 |
| SCD2 | Slowly Changing Dimension Type 2 | 缓慢变化维度，用有效期跟踪历史 |
| adj_factor | Adjustment Factor | 复权因子 |
| universe | Universe | 投资域/股票池 |
| constituent | Constituent | 成分股 |
| curated | Curated | 清洗标准化后的数据 |
| derived | Derived | 派生数据（可重建） |
| taxonomy | Taxonomy | 分类目录/层级结构 |
| membership | Membership | 归属关系 |
| neutralize | Neutralize | 中性化（去除某维度影响） |
| whitelist | Whitelist | 白名单（策略关注的子集） |

## 附录 B：Tushare 接口映射

| 数据域 | Tushare 接口 | Ditto 表 |
|-------|-------------|---------|
| 日线行情 | `daily` | `curated/market/daily` |
| 复权因子 | `adj_factor` | `curated/adjustment/factor` |
| 股票基础 | `stock_basic` | `securities` |
| 交易日历 | `trade_cal` | `trading_calendar` |
| 利润表 | `income` | `curated/fundamental/income` |
| 资产负债表 | `balancesheet` | `curated/fundamental/balance` |
| 现金流量表 | `cashflow` | `curated/fundamental/cashflow` |
| 指数成分 | `index_weight` | `curated/universe/index=*` |
| 申万行业目录 | `index_classify` | `sw_industry_taxonomy` |
| 申万行业成分 | `index_member_all` | `security_sw_industry` |
| 同花顺板块目录 | `ths_index` | `theme_taxonomy` |
| 东财板块成分 | `dc_member` | `theme_member_daily` |
| 板块热榜 | `ths_hot` | `curated/classification/theme/signals` |
| 板块资金流 | `moneyflow_ind_dc` | `curated/classification/theme/signals` |

---

## 十一、Classification 子域（行业/概念）

### 11.1 设计原则

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Classification 数据定位                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   行业（Industry）                    概念/主题（Theme）                  │
│   ─────────────────                   ─────────────────                  │
│   • 稳定的风险与归因维度               • 噪声大但对主题/事件敏感            │
│   • 必须做 PIT（有效期）               • 白名单策略，不做全量               │
│   • 用于：中性化、风险归因、轮动        • 用于：筛选、主题暴露、热度信号      │
│   • 数据源：申万（Tushare官方授权）     • 数据源：同花顺/东财                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**核心约束：**

| 约束 | 说明 |
|-----|------|
| taxonomy_version | 行业分类必须带版本（如SW2021），避免升级时"同名不同义" |
| SCD2 有效期 | 行业归属用 effective_from/to，支持 PIT 回测 |
| source 隔离 | 概念板块按 source 分存（THS/DC是不同体系） |
| 白名单策略 | 概念成分只同步策略用到的板块，避免成本黑洞 |
| 回测快照 | 预生成每日快照 Parquet，回测 join 零负担 |

### 11.2 SQLite 表结构（控制塔）

#### 11.2.1 申万行业

```sql
-- ============================================================
-- 申万行业目录（Taxonomy）
-- ============================================================
CREATE TABLE sw_industry_taxonomy (
    version         TEXT NOT NULL,              -- SW2021
    level           INTEGER NOT NULL,           -- 1/2/3
    industry_code   TEXT NOT NULL,              -- 801010.SI
    industry_name   TEXT NOT NULL,              -- 农林牧渔
    parent_code     TEXT,                       -- 上级行业代码（L1为空）
    index_code      TEXT,                       -- 对应可交易指数代码

    updated_at      TIMESTAMP,

    PRIMARY KEY (version, level, industry_code)
);

CREATE INDEX idx_sw_taxonomy_version ON sw_industry_taxonomy(version);
CREATE INDEX idx_sw_taxonomy_parent ON sw_industry_taxonomy(version, parent_code);


-- ============================================================
-- 个股行业归属（SCD2 / PIT）
-- ============================================================
CREATE TABLE security_sw_industry (
    version         TEXT NOT NULL,              -- SW2021
    sid             INTEGER NOT NULL,

    -- 三级行业（冗余存储，避免 join）
    l1_code         TEXT NOT NULL,              -- 一级行业代码
    l1_name         TEXT NOT NULL,              -- 一级行业名称
    l2_code         TEXT NOT NULL,              -- 二级行业代码
    l2_name         TEXT NOT NULL,              -- 二级行业名称
    l3_code         TEXT NOT NULL,              -- 三级行业代码
    l3_name         TEXT NOT NULL,              -- 三级行业名称

    -- 有效期（PIT 核心）
    effective_from  DATE NOT NULL,              -- 纳入日期
    effective_to    DATE,                       -- 剔除日期（NULL=当前）

    -- 溯源
    source          TEXT DEFAULT 'tushare',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (version, sid, effective_from),
    FOREIGN KEY (sid) REFERENCES securities(sid)
);

CREATE INDEX idx_sec_sw_ind_sid ON security_sw_industry(version, sid);
CREATE INDEX idx_sec_sw_ind_l1 ON security_sw_industry(version, l1_code);
CREATE INDEX idx_sec_sw_ind_l2 ON security_sw_industry(version, l2_code);
CREATE INDEX idx_sec_sw_ind_l3 ON security_sw_industry(version, l3_code);
CREATE INDEX idx_sec_sw_ind_dt ON security_sw_industry(version, effective_from, effective_to);
```

#### 11.2.2 概念/主题板块

```sql
-- ============================================================
-- 概念/主题板块目录（分 source）
-- ============================================================
CREATE TABLE theme_taxonomy (
    source          TEXT NOT NULL,              -- ths / dc
    theme_code      TEXT NOT NULL,              -- 885xxx.TI / BKxxxx
    theme_name      TEXT NOT NULL,              -- 人工智能 / 华为概念
    theme_type      TEXT,                       -- N=概念 / I=行业 / S=风格...

    -- 是否在白名单（只同步白名单内的成分）
    in_whitelist    BOOLEAN DEFAULT FALSE,

    updated_at      TIMESTAMP,

    PRIMARY KEY (source, theme_code)
);

CREATE INDEX idx_theme_tax_source ON theme_taxonomy(source);
CREATE INDEX idx_theme_tax_whitelist ON theme_taxonomy(source, in_whitelist);


-- ============================================================
-- 概念每日成分（PIT 天然成立，只同步白名单）
-- ============================================================
CREATE TABLE theme_member_daily (
    source          TEXT NOT NULL,              -- dc（东财每日成分最适合PIT）
    trade_date      DATE NOT NULL,
    theme_code      TEXT NOT NULL,
    sid             INTEGER NOT NULL,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (source, trade_date, theme_code, sid),
    FOREIGN KEY (sid) REFERENCES securities(sid)
);

CREATE INDEX idx_theme_member_sid ON theme_member_daily(source, sid, trade_date);
CREATE INDEX idx_theme_member_theme ON theme_member_daily(source, theme_code, trade_date);
CREATE INDEX idx_theme_member_date ON theme_member_daily(source, trade_date);


-- ============================================================
-- 概念白名单（策略关注的板块）
-- ============================================================
CREATE TABLE theme_whitelist (
    source          TEXT NOT NULL,
    theme_code      TEXT NOT NULL,
    theme_name      TEXT,
    reason          TEXT,                       -- 加入白名单的原因
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (source, theme_code)
);
```

### 11.3 Parquet Schema

#### 11.3.1 申万行业每日快照（回测核心）

```python
# curated/classification/sw_industry/daily/version=SW2021/dt=YYYY-MM-DD/data.parquet
SW_INDUSTRY_DAILY_SCHEMA = {
    "trade_date":   pl.Date,
    "sid":          pl.Int64,

    # 版本
    "sw_version":   pl.Utf8,        # SW2021

    # 行业代码（只存 code，不存 symbol，避免代码变更不一致）
    "sw_l1_code":   pl.Utf8,        # 801010
    "sw_l1_name":   pl.Utf8,        # 农林牧渔（冗余，减少 join）
    "sw_l2_code":   pl.Utf8,
    "sw_l2_name":   pl.Utf8,
    "sw_l3_code":   pl.Utf8,
    "sw_l3_name":   pl.Utf8,
}

# 注意：不存 symbol，需要时通过 sid + symbol_changes 做 as-of 映射
```

#### 11.3.2 概念成分每日快照

```python
# curated/classification/theme/membership_daily/source=dc/dt=YYYY-MM-DD/data.parquet
THEME_MEMBER_DAILY_SCHEMA = {
    "trade_date":   pl.Date,
    "source":       pl.Utf8,        # dc
    "theme_code":   pl.Utf8,        # BKxxxx
    "theme_name":   pl.Utf8,        # 冗余
    "sid":          pl.Int64,
}
```

#### 11.3.3 板块信号（热度/资金流）

```python
# curated/classification/theme/signals/source=ths_hot/dt=YYYY-MM-DD/data.parquet
THEME_HOT_SIGNAL_SCHEMA = {
    "trade_date":   pl.Date,
    "source":       pl.Utf8,        # ths_hot
    "theme_code":   pl.Utf8,
    "theme_name":   pl.Utf8,
    "rank":         pl.Int32,       # 热榜排名
    "hot_score":    pl.Float64,     # 热度值（如有）
}

# curated/classification/theme/signals/source=dc_moneyflow/dt=YYYY-MM-DD/data.parquet
THEME_MONEYFLOW_SCHEMA = {
    "trade_date":   pl.Date,
    "source":       pl.Utf8,        # dc_moneyflow
    "theme_code":   pl.Utf8,
    "theme_name":   pl.Utf8,
    "net_inflow":   pl.Float64,     # 净流入（元）
    "pct_change":   pl.Float64,     # 涨跌幅
}
```

### 11.4 Pipeline 实现

#### 11.4.1 任务依赖

```python
# 每周任务（行业数据变化慢）
weekly_tasks.update({
    "sync_sw_taxonomy":         [],                         # index_classify
    "sync_sw_membership":       ["sync_sw_taxonomy"],       # index_member_all
    "build_sw_industry_daily":  ["sync_sw_membership"],     # 生成回测快照

    "sync_theme_taxonomy_ths":  [],                         # ths_index
    "sync_theme_taxonomy_dc":   [],                         # dc 板块列表
})

# 每日任务（概念成分和信号变化快）
daily_tasks.update({
    "sync_theme_member_dc":     ["sync_calendar"],          # dc_member（仅白名单）
    "sync_theme_signals":       ["sync_calendar"],          # ths_hot + moneyflow_ind_dc
})
```

#### 11.4.2 申万行业同步

```python
class SWIndustrySync:
    """申万行业数据同步"""

    SW_VERSION = "SW2021"  # 当前使用的申万版本

    def __init__(self, pro, master: SecurityMaster, conn: sqlite3.Connection, data_root: Path):
        self.pro = pro
        self.master = master
        self.conn = conn
        self.data_root = data_root

    def sync_taxonomy(self):
        """同步行业目录（每年更新即可）"""
        for level in ["L1", "L2", "L3"]:
            df = self.pro.index_classify(level=level, src=self.SW_VERSION)

            for _, row in df.iterrows():
                self.conn.execute("""
                    INSERT OR REPLACE INTO sw_industry_taxonomy
                    (version, level, industry_code, industry_name, parent_code, index_code, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """, [
                    self.SW_VERSION,
                    int(level[1]),  # L1 -> 1
                    row['index_code'],
                    row['industry_name'],
                    row.get('parent_code'),
                    row['index_code']
                ])

        self.conn.commit()
        print(f"Synced SW industry taxonomy ({self.SW_VERSION})")

    def sync_membership(self):
        """
        同步个股行业归属（SCD2 有效期）

        使用 index_member_all 获取带 in_date/out_date 的成分
        """
        # 获取所有三级行业
        l3_industries = self.conn.execute("""
            SELECT industry_code, industry_name FROM sw_industry_taxonomy
            WHERE version = ? AND level = 3
        """, [self.SW_VERSION]).fetchall()

        # 构建行业层级映射
        hierarchy = self._build_hierarchy()

        for l3_code, l3_name in l3_industries:
            try:
                # 获取该行业的所有成分（含历史）
                df = self.pro.index_member_all(
                    index_code=l3_code,
                    is_new='N'  # 获取所有，包括历史
                )

                if df is None or df.empty:
                    continue

                # 获取层级信息
                l2_code, l2_name, l1_code, l1_name = hierarchy.get(l3_code, (None, None, None, None))

                for _, row in df.iterrows():
                    symbol = row['con_code']
                    sid = self.master.resolve_current_sid(symbol)

                    if sid is None:
                        self.master.register_pending(symbol, row['in_date'], 'sync_sw_membership')
                        continue

                    self.conn.execute("""
                        INSERT OR REPLACE INTO security_sw_industry
                        (version, sid, l1_code, l1_name, l2_code, l2_name, l3_code, l3_name,
                         effective_from, effective_to, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'tushare')
                    """, [
                        self.SW_VERSION,
                        sid,
                        l1_code, l1_name,
                        l2_code, l2_name,
                        l3_code, l3_name,
                        row['in_date'],
                        row.get('out_date'),  # 可能为 None
                    ])

            except Exception as e:
                print(f"Error syncing {l3_code}: {e}")
                continue

        self.conn.commit()
        print(f"Synced SW industry membership ({self.SW_VERSION})")

    def _build_hierarchy(self) -> dict:
        """构建行业层级映射：L3 -> (L2, L1)"""
        hierarchy = {}

        # 获取所有层级
        all_industries = pd.read_sql("""
            SELECT level, industry_code, industry_name, parent_code
            FROM sw_industry_taxonomy WHERE version = ?
        """, self.conn, params=[self.SW_VERSION])

        l1_map = {row['industry_code']: row['industry_name']
                  for _, row in all_industries[all_industries['level'] == 1].iterrows()}
        l2_map = {row['industry_code']: (row['industry_name'], row['parent_code'])
                  for _, row in all_industries[all_industries['level'] == 2].iterrows()}
        l3_map = {row['industry_code']: (row['industry_name'], row['parent_code'])
                  for _, row in all_industries[all_industries['level'] == 3].iterrows()}

        for l3_code, (l3_name, l2_code) in l3_map.items():
            if l2_code in l2_map:
                l2_name, l1_code = l2_map[l2_code]
                l1_name = l1_map.get(l1_code, '')
                hierarchy[l3_code] = (l2_code, l2_name, l1_code, l1_name)

        return hierarchy

    def build_daily_snapshot(self, trade_date: str):
        """
        生成行业每日快照（回测用）

        从 SCD2 membership 表生成某日的截面
        """
        df = pd.read_sql("""
            SELECT
                sid, l1_code, l1_name, l2_code, l2_name, l3_code, l3_name
            FROM security_sw_industry
            WHERE version = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
        """, self.conn, params=[self.SW_VERSION, trade_date, trade_date])

        if df.empty:
            return {"status": "skip", "reason": "no_data"}

        # 转为 Polars
        pl_df = (
            pl.from_pandas(df)
            .with_columns([
                pl.lit(trade_date).str.to_date("%Y-%m-%d").alias("trade_date"),
                pl.lit(self.SW_VERSION).alias("sw_version"),
            ])
            .select([
                "trade_date", "sid", "sw_version",
                "l1_code", "l1_name", "l2_code", "l2_name", "l3_code", "l3_name"
            ])
            .sort("sid")
        )

        # 写入
        output_path = (
            self.data_root /
            f"curated/classification/sw_industry/daily/version={self.SW_VERSION}/dt={trade_date}/data.parquet"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pl_df.write_parquet(output_path, compression="zstd")

        return {"status": "success", "rows": len(pl_df), "path": str(output_path)}
```

#### 11.4.3 概念/主题同步

```python
class ThemeSync:
    """概念/主题板块同步"""

    def __init__(self, pro, master: SecurityMaster, conn: sqlite3.Connection, data_root: Path):
        self.pro = pro
        self.master = master
        self.conn = conn
        self.data_root = data_root

    def sync_taxonomy_ths(self):
        """同步同花顺板块目录"""
        # 概念板块
        df_concept = self.pro.ths_index(exchange='A', type='N')
        # 行业板块
        df_industry = self.pro.ths_index(exchange='A', type='I')

        for df, theme_type in [(df_concept, 'N'), (df_industry, 'I')]:
            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                self.conn.execute("""
                    INSERT OR REPLACE INTO theme_taxonomy
                    (source, theme_code, theme_name, theme_type, updated_at)
                    VALUES ('ths', ?, ?, ?, datetime('now'))
                """, [row['ts_code'], row['name'], theme_type])

        self.conn.commit()
        print("Synced THS theme taxonomy")

    def sync_member_dc_daily(self, trade_date: str):
        """
        同步东财板块每日成分（仅白名单）

        东财 dc_member 天然按 trade_date 提供成分，最适合 PIT
        """
        # 获取白名单
        whitelist = self.conn.execute("""
            SELECT theme_code FROM theme_whitelist WHERE source = 'dc'
        """).fetchall()

        if not whitelist:
            print("No DC themes in whitelist, skipping")
            return {"status": "skip", "reason": "empty_whitelist"}

        all_members = []
        pending_count = 0  # v1.3：追踪映射失败的数量

        for (theme_code,) in whitelist:
            try:
                df = self.pro.dc_member(trade_date=trade_date, ts_code=theme_code)

                if df is None or df.empty:
                    continue

                for _, row in df.iterrows():
                    symbol = row['code']
                    sid = self.master.resolve_current_sid(symbol)

                    if sid is None:
                        # v1.3：必须 register_pending，避免成分消失
                        self.master.register_pending(symbol, trade_date, "sync_theme_member_dc")
                        pending_count += 1
                        continue

                    all_members.append({
                        "trade_date": trade_date,
                        "source": "dc",
                        "theme_code": theme_code,
                        "theme_name": row.get('name', ''),
                        "sid": sid,
                    })

            except Exception as e:
                print(f"Error syncing DC {theme_code}: {e}")
                continue

        if not all_members:
            return {"status": "skip", "reason": "no_members", "pending_count": pending_count}

        # 写入 SQLite（使用安全写入）
        safe_executemany(self.conn, """
            INSERT OR REPLACE INTO theme_member_daily
            (source, trade_date, theme_code, sid)
            VALUES (:source, :trade_date, :theme_code, :sid)
        """, all_members)

        # 写入 Parquet 快照
        pl_df = pl.DataFrame(all_members)
        output_path = (
            self.data_root /
            f"curated/classification/theme/membership_daily/source=dc/dt={trade_date}/data.parquet"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pl_df.write_parquet(output_path, compression="zstd")

        return {
            "status": "success",
            "rows": len(all_members),
            "pending_count": pending_count  # v1.3：返回待处理数量，便于监控
        }

    def sync_signals(self, trade_date: str):
        """同步板块信号（热榜 + 资金流）"""
        results = {}

        # 1. 同花顺热榜
        try:
            df_hot = self.pro.ths_hot(trade_date=trade_date)
            if df_hot is not None and not df_hot.empty:
                pl_hot = (
                    pl.from_pandas(df_hot)
                    .with_columns([
                        pl.lit(trade_date).str.to_date("%Y-%m-%d").alias("trade_date"),
                        pl.lit("ths_hot").alias("source"),
                    ])
                    .select(["trade_date", "source", "ts_code", "name", "rank"])
                    .rename({"ts_code": "theme_code", "name": "theme_name"})
                )

                output_path = (
                    self.data_root /
                    f"curated/classification/theme/signals/source=ths_hot/dt={trade_date}/data.parquet"
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                pl_hot.write_parquet(output_path, compression="zstd")
                results["ths_hot"] = {"status": "success", "rows": len(pl_hot)}
        except Exception as e:
            results["ths_hot"] = {"status": "error", "error": str(e)}

        # 2. 东财板块资金流
        try:
            df_flow = self.pro.moneyflow_ind_dc(trade_date=trade_date)
            if df_flow is not None and not df_flow.empty:
                pl_flow = (
                    pl.from_pandas(df_flow)
                    .with_columns([
                        pl.lit(trade_date).str.to_date("%Y-%m-%d").alias("trade_date"),
                        pl.lit("dc_moneyflow").alias("source"),
                    ])
                    .select([
                        "trade_date", "source", "ts_code", "name",
                        "net_amount", "pct_change"
                    ])
                    .rename({
                        "ts_code": "theme_code",
                        "name": "theme_name",
                        "net_amount": "net_inflow"
                    })
                )

                output_path = (
                    self.data_root /
                    f"curated/classification/theme/signals/source=dc_moneyflow/dt={trade_date}/data.parquet"
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                pl_flow.write_parquet(output_path, compression="zstd")
                results["dc_moneyflow"] = {"status": "success", "rows": len(pl_flow)}
        except Exception as e:
            results["dc_moneyflow"] = {"status": "error", "error": str(e)}

        return results

    def add_to_whitelist(self, source: str, theme_code: str, theme_name: str = None, reason: str = None):
        """添加板块到白名单"""
        self.conn.execute("""
            INSERT OR REPLACE INTO theme_whitelist (source, theme_code, theme_name, reason)
            VALUES (?, ?, ?, ?)
        """, [source, theme_code, theme_name, reason])

        # 同时更新 taxonomy 的 in_whitelist 标记
        self.conn.execute("""
            UPDATE theme_taxonomy SET in_whitelist = TRUE
            WHERE source = ? AND theme_code = ?
        """, [source, theme_code])

        self.conn.commit()
```

### 11.5 数据查询接口（v1.3：Unknown 兜底）

```python
# v1.3：行业 Unknown 兜底（避免中性化时报错）
INDUSTRY_UNKNOWN = {
    "l1_code": "UNKNOWN", "l1_name": "Industry_Unknown",
    "l2_code": "UNKNOWN", "l2_name": "Industry_Unknown",
    "l3_code": "UNKNOWN", "l3_name": "Industry_Unknown",
}


class ClassificationReader:
    """行业/概念分类数据读取（v1.3：增强健壮性）"""

    def __init__(self, conn: sqlite3.Connection, data_root: Path):
        self.conn = conn
        self.data_root = data_root

    # ========== 申万行业查询 ==========

    def get_industry_pit(
        self,
        sid: int,
        as_of_date: str,
        version: str = "SW2021"
    ) -> dict | None:
        """
        获取某时点的行业归属（PIT）
        """
        result = self.conn.execute("""
            SELECT l1_code, l1_name, l2_code, l2_name, l3_code, l3_name
            FROM security_sw_industry
            WHERE version = ? AND sid = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
            ORDER BY effective_from DESC
            LIMIT 1
        """, [version, sid, as_of_date, as_of_date]).fetchone()

        if result:
            return {
                "l1_code": result[0], "l1_name": result[1],
                "l2_code": result[2], "l2_name": result[3],
                "l3_code": result[4], "l3_name": result[5],
            }
        return None

    def get_industry_pit_safe(
        self,
        sid: int,
        as_of_date: str,
        version: str = "SW2021"
    ) -> dict:
        """
        获取某时点的行业归属（v1.3：带 Unknown 兜底）

        用于行业中性化等场景，避免缺失行业时报错
        """
        result = self.get_industry_pit(sid, as_of_date, version)
        return result if result else INDUSTRY_UNKNOWN

    def get_industry_members(
        self,
        industry_code: str,
        as_of_date: str,
        level: int = 1,
        version: str = "SW2021"
    ) -> list[int]:
        """获取某行业在某时点的成分股 sid 列表"""
        level_col = f"l{level}_code"

        result = self.conn.execute(f"""
            SELECT sid FROM security_sw_industry
            WHERE version = ? AND {level_col} = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
        """, [version, industry_code, as_of_date, as_of_date]).fetchall()

        return [r[0] for r in result]

    def query_industry_daily(
        self,
        trade_date: str,
        sids: list[int] = None,
        version: str = "SW2021"
    ) -> pl.DataFrame:
        """
        查询行业每日快照（回测用）

        优先从 Parquet 读取，fallback 到 SQLite
        """
        parquet_path = (
            self.data_root /
            f"curated/classification/sw_industry/daily/version={version}/dt={trade_date}/data.parquet"
        )

        if parquet_path.exists():
            lf = pl.scan_parquet(str(parquet_path))
            if sids:
                lf = lf.filter(pl.col("sid").is_in(sids))
            return lf.collect()

        # Fallback: 从 SQLite 生成
        sql = """
            SELECT
                ? as trade_date,
                sid,
                ? as sw_version,
                l1_code, l1_name, l2_code, l2_name, l3_code, l3_name
            FROM security_sw_industry
            WHERE version = ?
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
        """
        params = [trade_date, version, version, trade_date, trade_date]

        df = pd.read_sql(sql, self.conn, params=params)
        pl_df = pl.from_pandas(df)

        if sids:
            pl_df = pl_df.filter(pl.col("sid").is_in(sids))

        return pl_df

    # ========== 概念/主题查询 ==========

    def get_theme_members_pit(
        self,
        theme_code: str,
        trade_date: str,
        source: str = "dc"
    ) -> list[int]:
        """获取某概念在某日的成分股"""
        result = self.conn.execute("""
            SELECT sid FROM theme_member_daily
            WHERE source = ? AND theme_code = ? AND trade_date = ?
        """, [source, theme_code, trade_date]).fetchall()

        return [r[0] for r in result]

    def query_theme_signals(
        self,
        trade_date: str,
        signal_type: str = "ths_hot"
    ) -> pl.DataFrame:
        """查询板块信号"""
        parquet_path = (
            self.data_root /
            f"curated/classification/theme/signals/source={signal_type}/dt={trade_date}/data.parquet"
        )

        if parquet_path.exists():
            return pl.read_parquet(str(parquet_path))

        return pl.DataFrame()

    # ========== 行业中性化工具 ==========

    def neutralize_by_industry(
        self,
        df: pl.DataFrame,
        factor_col: str,
        industry_col: str = "sw_l1_name",
        method: str = "demean"
    ) -> pl.DataFrame:
        """
        行业中性化

        method:
            - demean: 去均值
            - rank: 行业内排名标准化
        """
        if method == "demean":
            return df.with_columns(
                (pl.col(factor_col) - pl.col(factor_col).mean().over(industry_col))
                .alias(f"{factor_col}_neutral")
            )
        elif method == "rank":
            return df.with_columns(
                pl.col(factor_col).rank().over(industry_col)
                .alias(f"{factor_col}_rank")
            )
        else:
            raise ValueError(f"Unknown method: {method}")
```

### 11.6 使用示例

```python
# 初始化
sw_sync = SWIndustrySync(pro, master, conn, DATA_ROOT)
theme_sync = ThemeSync(pro, master, conn, DATA_ROOT)
class_reader = ClassificationReader(conn, DATA_ROOT)

# ========== 行业数据同步 ==========

# 同步申万行业（每年一次）
sw_sync.sync_taxonomy()
sw_sync.sync_membership()

# 生成每日快照（每日/每周）
sw_sync.build_daily_snapshot("2024-01-02")

# ========== 概念数据同步 ==========

# 同步板块目录
theme_sync.sync_taxonomy_ths()

# 添加关注的板块到白名单
theme_sync.add_to_whitelist("dc", "BK0493", "华为概念", reason="关注华为产业链")
theme_sync.add_to_whitelist("dc", "BK0891", "人工智能", reason="AI主题投资")

# 同步白名单板块的每日成分
theme_sync.sync_member_dc_daily("2024-01-02")

# 同步信号
theme_sync.sync_signals("2024-01-02")

# ========== 数据查询 ==========

# PIT 行业查询
industry = class_reader.get_industry_pit(sid=1, as_of_date="2024-01-02")
# {'l1_code': '801010', 'l1_name': '农林牧渔', ...}

# 获取某行业的成分股
members = class_reader.get_industry_members("801010", "2024-01-02", level=1)

# 回测场景：批量查询行业
industry_df = class_reader.query_industry_daily("2024-01-02", sids=[1, 2, 3])

# 概念成分查询
ai_members = class_reader.get_theme_members_pit("BK0891", "2024-01-02", source="dc")

# 板块信号
hot_df = class_reader.query_theme_signals("2024-01-02", signal_type="ths_hot")

# ========== 行业中性化 ==========

# 假设 factor_df 含有 sid, trade_date, factor_value, sw_l1_name
neutralized = class_reader.neutralize_by_industry(
    factor_df,
    factor_col="factor_value",
    industry_col="sw_l1_name"
)
```

### 11.7 v1 落地优先级

| 优先级 | 任务 | 说明 |
|-------|------|------|
| P0 | 申万行业 taxonomy + membership | 行业轮动、风险归因、中性化的地基 |
| P0 | 申万行业 daily snapshot | 回测 join 零负担 |
| P1 | ths_index（概念目录） | 了解市场主题全貌 |
| P1 | ths_hot + dc_moneyflow（信号） | 热度/资金流信号 |
| P2 | dc_member（概念成分） | 白名单策略，需要时再开启 |

---

## 附录 C：Classification 数据源映射

| 数据类型 | Tushare 接口 | 参数 | PIT 支持 |
|---------|-------------|------|---------|
| 申万行业目录 | `index_classify` | `src='SW2021', level='L1/L2/L3'` | - |
| 申万行业成分 | `index_member_all` | `index_code, is_new` | ✅ in_date/out_date |
| 同花顺板块目录 | `ths_index` | `type='N/I'` | - |
| 同花顺板块成分 | `ths_member` | `ts_code` | ❌ 无有效期 |
| 东财板块成分 | `dc_member` | `trade_date, ts_code` | ✅ 天然按日 |
| 板块热榜 | `ths_hot` | `trade_date` | ✅ 按日 |
| 板块资金流 | `moneyflow_ind_dc` | `trade_date` | ✅ 按日 |

---

## 附录 D：v1.4 Implementation Checklist

### P0 必须做（影响正确性/稳定性）

**识别体系统一**
- [ ] **securities 表使用 (source, src_code) 唯一约束**：替代 ts_code，支持多数据源
- [ ] **新增 list_open_seq 字段**：用于 O(1) 计算上市交易日天数
- [ ] **移除 securities.industry_l1/l2**：统一由 security_sw_industry 管理
- [ ] **新增 name_changes 表**：改名与改代码分离，约束收敛到 sid 维度

**Schema 统一**
- [ ] **TUSHARE_FIELD_MAPPING 使用 src_code**：`"ts_code": "src_code"`
- [ ] **所有事实表 Schema 使用 src_code**：market_daily, adj_factor, fundamental_pit
- [ ] **移除 fundamental_pit 的 ingest_ts**：保证幂等性

**SecurityMaster 重构**
- [ ] **主映射改为 (source, src_code) -> sid**：不再依赖 symbol
- [ ] **resolve_sid 历史查询只走 symbol_changes**：不短路当前映射
- [ ] **register_pending 使用 (data_source, src_code) 主键**

**原子性与健壮性**
- [ ] **_atomic_write 使用 os.replace**：真正原子替换，避免 unlink+rename 竞态
- [ ] **_record_data_version 使用 file_md5_stream**：统一 checksum 入口
- [ ] **SQLite 锁重试装饰器**：`retry_sqlite_locked` 覆盖所有写路径

**DQ 动态涨跌幅**
- [ ] **新增 price_limit_config 表**：涨跌幅配置，插入默认数据
- [ ] **trading_calendar 新增 open_seq 字段**：交易日序号
- [ ] **DQ 检查使用 O(1) 计算 list_days**：`trade_open_seq - list_open_seq + 1`

### P1 强烈建议（影响性能/完整性）

**Reader 优化**
- [ ] **新增 compaction_state 表**：Reader 路径裁剪的 watermark
- [ ] **Reader 使用 _get_next_trade_date 裁剪**：避免 off-by-one 错误
- [ ] **Compactor 更新 compaction_state**：compact 成功后更新 watermark

**复权因子**
- [ ] **Reader qfq base_factor 强校验**：null/0 直接报错 + 指引 backfill
- [ ] **adj_factor DQ 检查**：覆盖率 + 连续性检查

**Classification**
- [ ] **Theme sid 映射失败 register_pending**：避免概念成分消失
- [ ] **行业 Unknown 兜底**：`get_industry_pit_safe` 返回默认值
- [ ] **index_member_all 防截断**：返回行数达到上限时报警

### P2 可选增强（后续版本）

- [ ] 行业 daily snapshot 支持 RLE/仅变化日落盘开关
- [ ] 复权因子交易日历覆盖率检查 + 单 sid 缺口定位
- [ ] pending_symbols 每日统计监控
- [ ] 多数据源适配器（RiceQuant/AkShare）

---

## 附录 E：关键配置默认值

### 涨跌幅制度配置

| 条件 | 阈值 | 优先级 | 说明 |
|-----|------|--------|------|
| 上市≤5个交易日 | 1000% | 100 | 新股不限制 |
| ST股 | 5% | 90 | ST涨跌幅限制 |
| 北交所 | 30% | 80 | 北交所涨跌幅 |
| 科创板 | 20% | 70 | 科创板涨跌幅 |
| 创业板 | 20% | 70 | 创业板涨跌幅 |
| 默认（主板） | 10% | 0 | 主板涨跌幅 |

### SQLite 并发配置

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA busy_timeout=5000;
PRAGMA cache_size=-64000;
```

### 重试配置

```python
retry_sqlite_locked(
    max_retries=8,
    base_sleep=0.05,
    max_sleep=1.0
)
```

---

## 附录 F：多数据源代码映射

### 数据源标识符

| 数据源 | source 值 | src_code 格式 | 示例 |
|-------|----------|---------------|------|
| Tushare | `tushare` | `{code}.{exchange}` | `600000.SH` |
| RiceQuant | `ricequant` | `{code}.{exchange}` | `600000.XSHG` |
| AkShare | `akshare` | `{exchange}{code}` | `sh600000` |
| Wind | `wind` | `{code}.{exchange}` | `600000.SH` |

### 代码转换示例

```python
def convert_src_code(src_code: str, from_source: str, to_source: str) -> str:
    """
    数据源代码转换

    示例：tushare -> ricequant
    600000.SH -> 600000.XSHG
    """
    EXCHANGE_MAP = {
        ("tushare", "ricequant"): {"SH": "XSHG", "SZ": "XSHE", "BJ": "XBSE"},
        ("ricequant", "tushare"): {"XSHG": "SH", "XSHE": "SZ", "XBSE": "BJ"},
    }

    if from_source == to_source:
        return src_code

    # 解析
    if from_source == "tushare":
        code, exchange = src_code.split(".")
    elif from_source == "ricequant":
        code, exchange = src_code.split(".")
    elif from_source == "akshare":
        exchange = src_code[:2].upper()
        code = src_code[2:]
        exchange = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}[exchange]

    # 转换交易所
    mapping = EXCHANGE_MAP.get((from_source, to_source), {})
    new_exchange = mapping.get(exchange, exchange)

    # 格式化
    if to_source == "tushare":
        return f"{code}.{new_exchange}"
    elif to_source == "ricequant":
        return f"{code}.{new_exchange}"
    elif to_source == "akshare":
        prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}[new_exchange]
        return f"{prefix}{code}"

    return src_code
```

---

## 附录 G：v1.4 vs v1.3 变更摘要

| 组件 | v1.3 | v1.4 | 变更原因 |
|-----|------|------|---------|
| 外部稳定键 | `ts_code` | `src_code` | 支持多数据源 |
| securities 唯一约束 | `UNIQUE(ts_code)` | `UNIQUE(source, src_code)` | 多数据源隔离 |
| 主映射通道 | `symbol -> sid` | `(source, src_code) -> sid` | 语义正确性 |
| list_days 计算 | `COUNT(*) SQL` | `open_seq - list_open_seq + 1` | O(1) 性能 |
| 原子替换 | `unlink + rename` | `os.replace` | 真正原子性 |
| checksum | `f.read()` | `file_md5_stream()` | 避免内存爆炸 |
| fundamental_pit | 含 `ingest_ts` | 移除 `ingest_ts` | 幂等性保证 |
| symbol_changes 约束 | `UNIQUE(symbol, effective_from)` | `UNIQUE(sid, effective_from)` | sid 为主 |
| securities 行业字段 | `industry_l1/l2` | 移除 | 单一真相 |
| resolve_sid | 先短路当前映射 | 只查 symbol_changes | 历史正确性 |

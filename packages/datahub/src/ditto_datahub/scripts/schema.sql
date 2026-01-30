-- SQLite Database Schema for Ditto DataHub
-- This schema supports SID allocation, 证券主数据, PIT queries,
-- trading calendar, freeze points, and universe management.

-- SID 序列 (百万级范围，与 SidRange 保持一致)
CREATE TABLE IF NOT EXISTS sid_sequence (
    asset_class TEXT PRIMARY KEY,
    current_max INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
VALUES ('stock', 1000000);
INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
VALUES ('etf', 2000000);
INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
VALUES ('index', 3000000);
INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
VALUES ('bond', 4000000);
INSERT OR IGNORE INTO sid_sequence (asset_class, current_max)
VALUES ('future', 5000000);

-- 证券主表
CREATE TABLE IF NOT EXISTS security (
    sid INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT,
    display_name TEXT,
    exchange TEXT NOT NULL,
    board TEXT,
    asset_class TEXT NOT NULL,
    list_date DATE NOT NULL,
    delist_date DATE,
    is_st BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_security_symbol ON security(symbol);
CREATE INDEX IF NOT EXISTS idx_security_asset_class ON security(asset_class);

-- 证券映射 (PIT support)
CREATE TABLE IF NOT EXISTS security_mapping (
    sid INTEGER NOT NULL,
    source TEXT NOT NULL,
    src_code TEXT NOT NULL,
    effective_from DATE NOT NULL DEFAULT '1990-01-01',
    effective_to DATE,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, src_code, effective_from),
    FOREIGN KEY (sid) REFERENCES security(sid)
);
CREATE INDEX IF NOT EXISTS idx_mapping_current
    ON security_mapping(source, src_code) WHERE effective_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_mapping_sid ON security_mapping(sid);

-- 交易日历
CREATE TABLE IF NOT EXISTS trading_calendar (
    trade_date DATE PRIMARY KEY,
    is_open BOOLEAN NOT NULL,
    prev_trade_date DATE,
    next_trade_date DATE,
    week_of_year INTEGER,
    month INTEGER,
    quarter INTEGER,
    year INTEGER,
    is_week_end BOOLEAN,
    is_month_end BOOLEAN,
    is_quarter_end BOOLEAN
);

-- Freeze 冻结点
CREATE TABLE IF NOT EXISTS freeze_point (
    freeze_id TEXT PRIMARY KEY,
    description TEXT,
    manifest_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 涨跌幅配置
CREATE TABLE IF NOT EXISTS price_limit_config (
    config_id INTEGER PRIMARY KEY AUTOINCREMENT,
    exchange TEXT,
    board TEXT,
    is_st BOOLEAN,
    min_list_days INTEGER,
    max_list_days INTEGER,
    limit_pct REAL NOT NULL,
    priority INTEGER DEFAULT 0,
    description TEXT
);
INSERT OR IGNORE INTO price_limit_config
    (config_id, limit_pct, priority, description)
VALUES
    (1, 1000, 100, '新股前5日'),
    (2, 5, 90, 'ST股'),
    (3, 30, 80, '北交所'),
    (4, 20, 70, '科创板/创业板'),
    (5, 10, 0, '默认');

-- 标的池定义
CREATE TABLE IF NOT EXISTS universe (
    universe_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    universe_type   TEXT NOT NULL,
    source_ref      TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP
);

-- 标的池成分 (PIT support)
CREATE TABLE IF NOT EXISTS universe_constituent (
    universe_id     TEXT NOT NULL,
    sid             INTEGER NOT NULL,
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    weight          REAL DEFAULT 1.0,
    source          TEXT,
    src_code        TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (universe_id, sid, effective_from),
    FOREIGN KEY (universe_id) REFERENCES universe(universe_id),
    FOREIGN KEY (sid) REFERENCES security(sid)
);

-- 当前有效成分快速查询
CREATE INDEX IF NOT EXISTS idx_constituent_current
    ON universe_constituent(universe_id, sid) WHERE effective_to IS NULL;

-- PIT 查询优化
CREATE INDEX IF NOT EXISTS idx_constituent_pit
    ON universe_constituent(universe_id, effective_from, effective_to);

-- 指数成分股权重（PIT support）
CREATE TABLE IF NOT EXISTS index_weight (
    index_id       TEXT NOT NULL,
    sid            INTEGER NOT NULL,
    effective_from DATE NOT NULL,
    effective_to   DATE,
    weight         REAL,
    PRIMARY KEY (index_id, sid, effective_from)
);

-- 当前有效成分快速查询
CREATE INDEX IF NOT EXISTS idx_index_weight_current
    ON index_weight(index_id, sid) WHERE effective_to IS NULL;

-- PIT 查询优化
CREATE INDEX IF NOT EXISTS idx_index_weight_pit
    ON index_weight(index_id, effective_from, effective_to);

-- DQ 隔离区存储（失败数据）
CREATE TABLE IF NOT EXISTS quarantine_failed_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    failed_data TEXT,  -- JSON stored failed records
    affected_rows INTEGER DEFAULT 0,
    trade_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_quarantine_dataset
    ON quarantine_failed_data(dataset);
CREATE INDEX IF NOT EXISTS idx_quarantine_rule
    ON quarantine_failed_data(rule_id);

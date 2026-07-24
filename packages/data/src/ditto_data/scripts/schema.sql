-- SQLite Database Schema for Ditto DataHub
-- This schema supports Instrument ID allocation, 证券主数据, PIT queries,
-- trading calendar, freeze points, and universe management.

-- Instrument ID 序列 (百万级范围，与 SidRange 保持一致)
CREATE TABLE IF NOT EXISTS instrument_id_sequence (
    asset_class TEXT PRIMARY KEY,
    current_max INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO instrument_id_sequence (asset_class, current_max)
VALUES ('stock', 1000000);
INSERT OR IGNORE INTO instrument_id_sequence (asset_class, current_max)
VALUES ('etf', 2000000);
INSERT OR IGNORE INTO instrument_id_sequence (asset_class, current_max)
VALUES ('index', 3000000);
INSERT OR IGNORE INTO instrument_id_sequence (asset_class, current_max)
VALUES ('bond', 4000000);
INSERT OR IGNORE INTO instrument_id_sequence (asset_class, current_max)
VALUES ('future', 5000000);

-- 证券主表
CREATE TABLE IF NOT EXISTS instrument (
    instrument_id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    name TEXT,
    display_name TEXT,
    exchange TEXT NOT NULL,
    board TEXT,
    asset_class TEXT NOT NULL,
    list_date DATE,  -- 可为 NULL，后续通过行情数据推断
    delist_date DATE,
    is_st BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_instrument_ticker ON instrument(ticker);
CREATE INDEX IF NOT EXISTS idx_instrument_asset_class ON instrument(asset_class);

-- 证券映射 (PIT support)
CREATE TABLE IF NOT EXISTS instrument_mapping (
    instrument_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_ticker TEXT NOT NULL,
    effective_from DATE NOT NULL DEFAULT '1990-01-01',
    effective_to DATE,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, source_ticker, effective_from),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_mapping_current
    ON instrument_mapping(source, source_ticker) WHERE effective_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_mapping_instrument_id ON instrument_mapping(instrument_id);

-- ============ 资产类型扩展表 ============
-- 使用扩展表模式（而非宽表）以保持类型安全和可扩展性

-- 股票扩展表
CREATE TABLE IF NOT EXISTS instrument_stock (
    instrument_id INTEGER PRIMARY KEY,
    list_status TEXT,  -- L=正常, D=退市, P=暂停
    industry_id INTEGER,
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);

-- ETF 扩展表
CREATE TABLE IF NOT EXISTS instrument_etf (
    instrument_id INTEGER PRIMARY KEY,
    fund_type TEXT,  -- 股票型/债券型/货币型/混合型等
    fund_manager TEXT,
    establish_date DATE,
    tracking_index TEXT,
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);

-- 指数扩展表
CREATE TABLE IF NOT EXISTS instrument_index (
    instrument_id INTEGER PRIMARY KEY,
    base_date DATE,  -- 基日
    base_point REAL,  -- 基点
    num_constituents INTEGER,  -- 成分股数量
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);

-- ============ 行业分类表 ============

-- 行业主数据（申万/证监会）
CREATE TABLE IF NOT EXISTS industry_basic (
    industry_id TEXT PRIMARY KEY,
    industry_name TEXT NOT NULL,
    industry_level TEXT NOT NULL,  -- L1/L2/L3
    parent_id TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    source TEXT DEFAULT 'sw'  -- sw=申万, csrc=证监会
);

-- 股票-行业映射（PIT support）
CREATE TABLE IF NOT EXISTS industry_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id INTEGER NOT NULL,
    industry_id TEXT NOT NULL,
    source TEXT DEFAULT 'sw',
    effective_from DATE,
    effective_to DATE,
    entry_reason TEXT,
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id),
    FOREIGN KEY (industry_id) REFERENCES industry_basic(industry_id)
);
CREATE INDEX IF NOT EXISTS idx_industry_mapping_current
    ON industry_mapping(instrument_id, source) WHERE effective_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_industry_mapping_pit
    ON industry_mapping(instrument_id, source, effective_from, effective_to);

-- 交易日历
CREATE TABLE IF NOT EXISTS trading_calendar (
    trade_date DATE PRIMARY KEY,
    is_open BOOLEAN NOT NULL,
    exchange TEXT DEFAULT 'SSE',
    prev_trade_date DATE,
    next_trade_date DATE,
    week_of_year INTEGER,
    month INTEGER,
    quarter INTEGER,
    year INTEGER,
    is_week_end BOOLEAN,
    is_month_end BOOLEAN,
    is_quarter_end BOOLEAN,
    is_half_day BOOLEAN DEFAULT FALSE,
    is_special BOOLEAN DEFAULT FALSE
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
    instrument_id             INTEGER NOT NULL,
    effective_from  DATE NOT NULL,
    effective_to    DATE,
    weight          REAL DEFAULT 1.0,
    source          TEXT,
    source_ticker        TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (universe_id, instrument_id, effective_from),
    FOREIGN KEY (universe_id) REFERENCES universe(universe_id),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);

-- 证券名称变更历史
CREATE TABLE IF NOT EXISTS instrument_name_history (
    instrument_id INTEGER NOT NULL,
    old_name TEXT NOT NULL,
    new_name TEXT NOT NULL,
    changed_date DATE NOT NULL,
    PRIMARY KEY (instrument_id, changed_date),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_name_history_instrument ON instrument_name_history(instrument_id);

-- ST 状态变更历史 (PIT support)
CREATE TABLE IF NOT EXISTS st_change_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id INTEGER NOT NULL,
    effective_from DATE NOT NULL,
    is_st INTEGER NOT NULL,
    st_type TEXT,
    effective_to DATE,
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_st_change_history_pit
    ON st_change_history(instrument_id, effective_from, effective_to);

-- 当前有效成分快速查询
CREATE INDEX IF NOT EXISTS idx_constituent_current
    ON universe_constituent(universe_id, instrument_id) WHERE effective_to IS NULL;

-- PIT 查询优化
CREATE INDEX IF NOT EXISTS idx_constituent_pit
    ON universe_constituent(universe_id, effective_from, effective_to);

-- 标的池调仓日程
CREATE TABLE IF NOT EXISTS universe_rebalance (
    universe_id TEXT NOT NULL,
    rebalance_date DATE NOT NULL,
    description TEXT,
    PRIMARY KEY (universe_id, rebalance_date),
    FOREIGN KEY (universe_id) REFERENCES universe(universe_id)
);
CREATE INDEX IF NOT EXISTS idx_rebalance_date ON universe_rebalance(universe_id, rebalance_date);

-- 策略目录控制面
CREATE TABLE IF NOT EXISTS strategy_spec (
    strategy_id       TEXT NOT NULL,
    version           INTEGER NOT NULL,
    name              TEXT NOT NULL,
    spec_json         TEXT NOT NULL,
    spec_hash         TEXT NOT NULL DEFAULT '',
    parent_version    INTEGER,
    status            TEXT NOT NULL DEFAULT 'draft',
    tags              TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT '',
    updated_at        TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (strategy_id, version)
);
CREATE INDEX IF NOT EXISTS idx_spec_status ON strategy_spec(status);
CREATE INDEX IF NOT EXISTS idx_spec_strategy_id ON strategy_spec(strategy_id);
CREATE INDEX IF NOT EXISTS idx_spec_hash ON strategy_spec(spec_hash);

-- 策略产物控制面
CREATE TABLE IF NOT EXISTS strategy_artifact (
    artifact_id       TEXT PRIMARY KEY,
    strategy_id       TEXT NOT NULL,
    run_id            TEXT NOT NULL,
    artifact_type     TEXT NOT NULL,
    file_path         TEXT NOT NULL DEFAULT '',
    metadata          TEXT NOT NULL DEFAULT '{}',
    status            TEXT NOT NULL DEFAULT 'active',
    created_at        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_artifact_strategy_id
    ON strategy_artifact(strategy_id);
CREATE INDEX IF NOT EXISTS idx_artifact_status
    ON strategy_artifact(status);

-- 策略运行控制面
CREATE TABLE IF NOT EXISTS strategy_run (
    run_id            TEXT PRIMARY KEY,
    strategy_id       TEXT NOT NULL,
    strategy_version  TEXT NOT NULL DEFAULT '',
    mode              TEXT NOT NULL DEFAULT 'backtest',
    status            TEXT NOT NULL DEFAULT 'pending',
    started_at        TEXT NOT NULL DEFAULT '',
    completed_at      TEXT NOT NULL DEFAULT '',
    error_message     TEXT NOT NULL DEFAULT '',
    parent_run_id     TEXT NOT NULL DEFAULT '',
    progress_pct      REAL NOT NULL DEFAULT 0.0,
    current_step      TEXT NOT NULL DEFAULT '',
    completed_days    INTEGER NOT NULL DEFAULT 0,
    total_days        INTEGER NOT NULL DEFAULT 0,
    config_json       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_strategy_run_strategy_id
    ON strategy_run(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_run_status
    ON strategy_run(status);
-- parent_run_id index is created by strategy storage migrations after
-- legacy strategy_run tables have been upgraded with the parent_run_id column.

CREATE TABLE IF NOT EXISTS strategy_run_checkpoint (
    run_id               TEXT PRIMARY KEY,
    strategy_id          TEXT NOT NULL,
    strategy_version     TEXT NOT NULL DEFAULT '',
    mode                 TEXT NOT NULL DEFAULT 'backtest',
    completed_trade_date TEXT NOT NULL,
    resume_from          TEXT,
    completed_days       INTEGER NOT NULL DEFAULT 0,
    total_days           INTEGER NOT NULL DEFAULT 0,
    nav                  REAL NOT NULL DEFAULT 0.0,
    order_count          INTEGER NOT NULL DEFAULT 0,
    fill_count           INTEGER NOT NULL DEFAULT 0,
    account_state_json   TEXT NOT NULL DEFAULT '',
    account_state_hash   TEXT NOT NULL DEFAULT '',
    settlement_state_json TEXT NOT NULL DEFAULT '',
    settlement_state_hash TEXT NOT NULL DEFAULT '',
    runtime_state_json   TEXT NOT NULL DEFAULT '',
    runtime_state_hash   TEXT NOT NULL DEFAULT '',
    updated_at           TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_strategy_run_checkpoint_strategy_id
    ON strategy_run_checkpoint(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_run_checkpoint_completed_trade_date
    ON strategy_run_checkpoint(completed_trade_date);

-- 指数成分股权重（PIT support）
CREATE TABLE IF NOT EXISTS index_weight (
    index_id       TEXT NOT NULL,
    instrument_id            INTEGER NOT NULL,
    effective_from DATE NOT NULL,
    effective_to   DATE,
    weight         REAL,
    PRIMARY KEY (index_id, instrument_id, effective_from)
);

-- 当前有效成分快速查询
CREATE INDEX IF NOT EXISTS idx_index_weight_current
    ON index_weight(index_id, instrument_id) WHERE effective_to IS NULL;

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

-- ============ 基本面数据表 ============

-- 资产负债表
CREATE TABLE IF NOT EXISTS balance_sheet (
    instrument_id INTEGER NOT NULL,
    report_date DATE NOT NULL,
    knowledge_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    total_assets REAL,
    total_liabilities REAL,
    net_assets REAL,
    current_assets REAL,
    current_liabilities REAL,
    inventory REAL,
    fixed_assets REAL,
    cash_equivalents REAL,
    accounts_receivable REAL,
    short_term_debt REAL,
    long_term_debt REAL,
    money_cap REAL,
    total_share REAL,
    PRIMARY KEY (instrument_id, report_date, effective_from),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_balance_sheet_pit
    ON balance_sheet(instrument_id, effective_from, effective_to);

-- 利润表
CREATE TABLE IF NOT EXISTS income_statement (
    instrument_id INTEGER NOT NULL,
    report_date DATE NOT NULL,
    knowledge_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    revenue REAL,
    operating_profit REAL,
    net_profit REAL,
    eps REAL,
    operate_cost REAL,
    sale_exp REAL,
    admin_exp REAL,
    fin_exp REAL,
    rd_exp REAL,
    total_profit REAL,
    income_tax REAL,
    diluted_eps REAL,
    PRIMARY KEY (instrument_id, report_date, effective_from),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_income_statement_pit
    ON income_statement(instrument_id, effective_from, effective_to);

-- 现金流量表
CREATE TABLE IF NOT EXISTS cash_flow (
    instrument_id INTEGER NOT NULL,
    report_date DATE NOT NULL,
    knowledge_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    operating_cash_flow REAL,
    investing_cash_flow REAL,
    financing_cash_flow REAL,
    net_cash_flow REAL,
    depreciation REAL,
    interest_paid REAL,
    tax_paid REAL,
    PRIMARY KEY (instrument_id, report_date, effective_from),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_cash_flow_pit
    ON cash_flow(instrument_id, effective_from, effective_to);

-- 分红送配
-- P015 修复：ex_dividend_date 可为 NULL（预案阶段），添加 div_proc 字段
CREATE TABLE IF NOT EXISTS dividend (
    instrument_id INTEGER NOT NULL,
    ex_dividend_date DATE,  -- 可为 NULL，预案阶段
    knowledge_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    dividend_per_share REAL,
    dividend_yield REAL,
    div_proc TEXT,  -- P015: 实施进度：预案/实施
    PRIMARY KEY (instrument_id, effective_from, ex_dividend_date),  -- 调整主键顺序
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_dividend_pit
    ON dividend(instrument_id, effective_from, effective_to);

-- 公司行动
CREATE TABLE IF NOT EXISTS corporate_actions (
    instrument_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    action_date DATE NOT NULL,
    knowledge_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    description TEXT,
    PRIMARY KEY (instrument_id, action_type, action_date, effective_from),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_corporate_actions_pit
    ON corporate_actions(instrument_id, effective_from, effective_to);

-- ============ 资本面数据表 ============

-- 估值指标
CREATE TABLE IF NOT EXISTS valuation_metrics (
    instrument_id INTEGER NOT NULL,
    trade_date DATE NOT NULL,
    knowledge_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    pe_ratio REAL,
    pb_ratio REAL,
    ps_ratio REAL,
    dividend_yield REAL,
    market_cap REAL,
    PRIMARY KEY (instrument_id, trade_date, effective_from),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_valuation_metrics_pit
    ON valuation_metrics(instrument_id, effective_from, effective_to);

-- 融资融券
CREATE TABLE IF NOT EXISTS margin_trading (
    instrument_id INTEGER NOT NULL,
    trade_date DATE NOT NULL,
    knowledge_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    margin_buy_balance REAL,
    short_sell_balance REAL,
    margin_buy_volume REAL,
    short_sell_volume REAL,
    PRIMARY KEY (instrument_id, trade_date, effective_from),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_margin_trading_pit
    ON margin_trading(instrument_id, effective_from, effective_to);

-- 股权质押
CREATE TABLE IF NOT EXISTS pledge_ratio (
    instrument_id INTEGER NOT NULL,
    report_date DATE NOT NULL,
    knowledge_date DATE NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    pledge_ratio REAL,
    pledge_shares REAL,
    total_shares REAL,
    PRIMARY KEY (instrument_id, report_date, effective_from),
    FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_pledge_ratio_pit
    ON pledge_ratio(instrument_id, effective_from, effective_to);

-- ============ 宏观数据表 ============

-- 宏观指标元数据
CREATE TABLE IF NOT EXISTS macro_indicators (
    indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    frequency TEXT NOT NULL,
    need_pit BOOLEAN DEFAULT FALSE,
    source TEXT,
    unit TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_macro_indicators_code ON macro_indicators(code);
CREATE INDEX IF NOT EXISTS idx_macro_indicators_category ON macro_indicators(category);

-- 宏观指标数据 (PIT support)
CREATE TABLE IF NOT EXISTS macro_indicator_data (
    indicator_id INTEGER NOT NULL,
    date DATE NOT NULL,
    value REAL,
    knowledge_date DATE,
    effective_from DATE NOT NULL,
    effective_to DATE,
    PRIMARY KEY (indicator_id, date, effective_from),
    FOREIGN KEY (indicator_id) REFERENCES macro_indicators(indicator_id)
);
CREATE INDEX IF NOT EXISTS idx_macro_indicator_data_pit
    ON macro_indicator_data(indicator_id, effective_from, effective_to);

-- ============ Unified Derived Runtime Tables ============

CREATE TABLE IF NOT EXISTS derived_spec (
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    role TEXT NOT NULL,
    materialization_profile TEXT NOT NULL,
    spec_hash TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (derived_id, version)
);

CREATE TABLE IF NOT EXISTS derived_version (
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    is_online INTEGER NOT NULL,
    is_primary INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    PRIMARY KEY (derived_id, version)
);

CREATE TABLE IF NOT EXISTS derived_run (
    run_id TEXT PRIMARY KEY,
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    mode TEXT NOT NULL,
    trigger TEXT NOT NULL,
    request_start TEXT NOT NULL,
    request_end TEXT NOT NULL,
    compute_start TEXT NOT NULL,
    compute_end TEXT NOT NULL,
    source_snapshot_id TEXT,
    status TEXT NOT NULL,
    rows_written INTEGER NOT NULL,
    partitions_written TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_derived_run_lookup
    ON derived_run(derived_id, version, created_at DESC);

CREATE TABLE IF NOT EXISTS derived_partition (
    run_id TEXT NOT NULL,
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    partition_key TEXT NOT NULL,
    partition_path TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    checksum TEXT,
    written_at TEXT NOT NULL,
    PRIMARY KEY (run_id, partition_key)
);

CREATE TABLE IF NOT EXISTS derived_checkpoint (
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    partition_key TEXT NOT NULL,
    status TEXT NOT NULL,
    rows_written INTEGER NOT NULL,
    checksum TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    PRIMARY KEY (derived_id, version, partition_key)
);

CREATE TABLE IF NOT EXISTS derived_dependency (
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    dependency_kind TEXT NOT NULL,
    dependency_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (derived_id, version, dependency_kind, dependency_ref)
);
CREATE INDEX IF NOT EXISTS idx_derived_dependency_ref
    ON derived_dependency(dependency_ref);

CREATE TABLE IF NOT EXISTS derived_invalidation (
    invalidation_id TEXT PRIMARY KEY,
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    source_domain TEXT NOT NULL,
    source_dataset TEXT NOT NULL,
    change_date TEXT NOT NULL,
    affected_start TEXT NOT NULL,
    affected_end TEXT NOT NULL,
    source_snapshot_id TEXT,
    root_dependency_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    processed_at TEXT,
    depth INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    dead_letter_at TEXT,
    role TEXT NOT NULL DEFAULT 'factor'
);
CREATE INDEX IF NOT EXISTS idx_derived_invalidation_pending
    ON derived_invalidation(status, created_at);
CREATE INDEX IF NOT EXISTS idx_derived_invalidation_stale
    ON derived_invalidation(status, depth, created_at);

CREATE TABLE IF NOT EXISTS derived_state (
    derived_id TEXT PRIMARY KEY,
    active_version INTEGER,
    coverage_start TEXT,
    coverage_end TEXT,
    watermark TEXT,
    latest_run_id TEXT,
    latest_run_status TEXT,
    total_rows INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS derived_shadow_slot (
    derived_id TEXT PRIMARY KEY,
    candidate_version INTEGER NOT NULL,
    baseline_version INTEGER,
    activated_at TEXT NOT NULL,
    disabled_at TEXT
);

CREATE TABLE IF NOT EXISTS compiled_expression_cache (
    cache_key TEXT PRIMARY KEY,
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    compiler_fingerprint TEXT NOT NULL,
    compile_input_hash TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    compile_identity_json TEXT NOT NULL,
    expression_repr TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS compiled_expression_operator (
    cache_key TEXT NOT NULL,
    operator_name TEXT NOT NULL,
    operator_version TEXT NOT NULL,
    PRIMARY KEY (cache_key, operator_name)
);

CREATE TABLE IF NOT EXISTS derived_spec_operator (
    derived_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    operator_name TEXT NOT NULL,
    operator_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (derived_id, version, operator_name)
);

-- ============ Research Control-Plane Tables ============

CREATE TABLE IF NOT EXISTS research_spine_spec (
    spine_id TEXT PRIMARY KEY,
    universe_id TEXT NOT NULL,
    calendar TEXT NOT NULL,
    grain TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS research_dataset_spec (
    dataset_id TEXT PRIMARY KEY,
    spine_id TEXT NOT NULL,
    derived_ids TEXT NOT NULL,
    join_policy TEXT NOT NULL,
    known_at_policy TEXT NOT NULL,
    late_arrival_policy TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (spine_id) REFERENCES research_spine_spec(spine_id)
);

CREATE TABLE IF NOT EXISTS research_spine_snapshot (
    spine_snapshot_id TEXT PRIMARY KEY,
    spine_id TEXT NOT NULL,
    snapshot_start TEXT NOT NULL,
    snapshot_end TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    data_path TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (spine_id) REFERENCES research_spine_spec(spine_id)
);
CREATE INDEX IF NOT EXISTS idx_research_spine_snapshot_lookup
    ON research_spine_snapshot(spine_id, created_at DESC);

CREATE TABLE IF NOT EXISTS research_dataset_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    dataset_spec_version INTEGER NOT NULL,
    spine_snapshot_id TEXT NOT NULL,
    snapshot_start TEXT NOT NULL,
    snapshot_end TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    data_path TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    known_at_policy TEXT NOT NULL,
    effective_cutoff TEXT,
    spine_spec_version INTEGER NOT NULL DEFAULT 1,
    resolved_versions TEXT NOT NULL,
    resolved_inputs TEXT NOT NULL,
    source_snapshot_ids TEXT NOT NULL,
    builder_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (dataset_id) REFERENCES research_dataset_spec(dataset_id),
    FOREIGN KEY (spine_snapshot_id)
        REFERENCES research_spine_snapshot(spine_snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_research_dataset_snapshot_lookup
    ON research_dataset_snapshot(dataset_id, created_at DESC);

-- ============ 交易闭环表 ============

CREATE TABLE IF NOT EXISTS trade_intents (
    intent_id      TEXT PRIMARY KEY,
    strategy_id    TEXT    NOT NULL,
    signal_date    TEXT    NOT NULL,
    instrument_id  INTEGER NOT NULL,
    direction      TEXT    NOT NULL,
    target_weight  REAL    NOT NULL,
    current_weight REAL    NOT NULL,
    delta_weight   REAL    NOT NULL,
    quantity       INTEGER,
    status         TEXT    NOT NULL DEFAULT 'pending',
    created_at     TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_trade_intents_strategy_date
    ON trade_intents(strategy_id, signal_date);
CREATE INDEX IF NOT EXISTS idx_trade_intents_status ON trade_intents(status);

CREATE TABLE IF NOT EXISTS execution_fills (
    fill_id        TEXT PRIMARY KEY,
    intent_id      TEXT    NOT NULL,
    strategy_id    TEXT    NOT NULL,
    trade_date     TEXT    NOT NULL,
    instrument_id  INTEGER NOT NULL,
    direction      TEXT    NOT NULL,
    quantity       INTEGER NOT NULL,
    fill_price     REAL    NOT NULL,
    fee            REAL    NOT NULL,
    slippage       REAL    NOT NULL DEFAULT 0.0,
    notes          TEXT    NOT NULL DEFAULT '',
    settlement_date TEXT   NOT NULL DEFAULT '',
    created_at     TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_execution_fills_strategy_date
    ON execution_fills(strategy_id, trade_date);
CREATE INDEX IF NOT EXISTS idx_execution_fills_intent
    ON execution_fills(intent_id);

CREATE TABLE IF NOT EXISTS actual_positions (
    snapshot_id       TEXT PRIMARY KEY,
    strategy_id       TEXT    NOT NULL,
    snapshot_date     TEXT    NOT NULL,
    instrument_id     INTEGER NOT NULL,
    quantity          INTEGER NOT NULL,
    available_quantity INTEGER NOT NULL,
    average_cost      REAL    NOT NULL,
    market_value      REAL    NOT NULL,
    unrealized_pnl    REAL    NOT NULL,
    realized_pnl      REAL    NOT NULL,
    total_fees        REAL    NOT NULL,
    created_at        TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_actual_positions_strategy_date
    ON actual_positions(strategy_id, snapshot_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_actual_positions_strategy_instrument_date
    ON actual_positions(strategy_id, instrument_id, snapshot_date);

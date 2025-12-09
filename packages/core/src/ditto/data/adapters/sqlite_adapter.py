"""SQLite 数据库适配器"""

from pathlib import Path
from typing import Optional
import sqlite3


class SQLiteAdapter:
    """SQLite 数据库适配器，用于交易型数据"""

    def __init__(self, database_path: str) -> None:
        """初始化适配器"""
        self.database_path = database_path
        self.connection: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """建立数据库连接"""
        # 确保目录存在
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)

        if self.connection is None:
            self.connection = sqlite3.connect(self.database_path)
            # 启用外键约束
            self.connection.execute("PRAGMA foreign_keys = ON")
            # 设置 WAL 模式提高并发性能
            self.connection.execute("PRAGMA journal_mode = WAL")

    def disconnect(self) -> None:
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def initialize_schema(self) -> None:
        """初始化数据库表结构"""
        if not self.connection:
            raise RuntimeError("Must connect before initializing schema")

        cursor = self.connection.cursor()

        # 交易记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id VARCHAR NOT NULL,
                ts_code VARCHAR NOT NULL,
                direction VARCHAR NOT NULL,  -- BUY, SELL
                trade_price FLOAT NOT NULL,
                trade_volume INTEGER NOT NULL,
                trade_amount FLOAT NOT NULL,
                trade_time TIMESTAMP NOT NULL,
                trade_id VARCHAR,
                commission FLOAT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            )
        """)

        # 订单记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id VARCHAR NOT NULL UNIQUE,
                strategy_id VARCHAR NOT NULL,
                ts_code VARCHAR NOT NULL,
                direction VARCHAR NOT NULL,  -- BUY, SELL
                order_type VARCHAR NOT NULL,  -- MARKET, LIMIT
                order_price FLOAT,
                order_volume INTEGER NOT NULL,
                order_status VARCHAR NOT NULL,  -- PENDING, FILLED, CANCELLED, REJECTED
                order_time TIMESTAMP NOT NULL,
                filled_volume INTEGER DEFAULT 0,
                filled_amount FLOAT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 持仓表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id VARCHAR NOT NULL,
                ts_code VARCHAR NOT NULL,
                current_volume INTEGER NOT NULL DEFAULT 0,
                available_volume INTEGER NOT NULL DEFAULT 0,
                avg_cost FLOAT NOT NULL DEFAULT 0,
                market_value FLOAT NOT NULL DEFAULT 0,
                last_price FLOAT NOT NULL DEFAULT 0,
                last_update TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(strategy_id, ts_code)
            )
        """)

        # 组合快照表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id VARCHAR NOT NULL,
                snapshot_date DATE NOT NULL,
                total_value FLOAT NOT NULL,
                cash_amount FLOAT NOT NULL,
                position_value FLOAT NOT NULL,
                daily_pnl FLOAT NOT NULL DEFAULT 0,
                total_pnl FLOAT NOT NULL DEFAULT 0,
                position_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(strategy_id, snapshot_date)
            )
        """)

        # 策略配置表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id VARCHAR NOT NULL UNIQUE,
                strategy_name VARCHAR NOT NULL,
                strategy_version VARCHAR NOT NULL,
                config_json TEXT NOT NULL,  -- JSON 格式的配置
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 执行日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id VARCHAR NOT NULL,
                execution_id VARCHAR NOT NULL,
                execution_type VARCHAR NOT NULL,  -- REBALANCE, RISK_CHECK, SIGNAL
                status VARCHAR NOT NULL,  -- SUCCESS, FAILED, PARTIAL
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                details TEXT,  -- JSON 格式的详细信息
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 风险事件表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id VARCHAR NOT NULL,
                event_type VARCHAR NOT NULL,  -- DRAWDOWN, KILL_SWITCH, POSITION_LIMIT
                event_level VARCHAR NOT NULL,  -- INFO, WARNING, CRITICAL
                event_time TIMESTAMP NOT NULL,
                event_data TEXT,  -- JSON 格式的事件数据
                is_resolved INTEGER NOT NULL DEFAULT 0,
                resolved_time TIMESTAMP,
                resolution TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引
        self._create_indexes(cursor)

        self.connection.commit()

    def _create_indexes(self, cursor: sqlite3.Cursor) -> None:
        """创建性能优化索引"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_trades_order_id ON trades(order_id)",
            "CREATE INDEX IF NOT EXISTS idx_trades_ts_code ON trades(ts_code)",
            "CREATE INDEX IF NOT EXISTS idx_trades_trade_time ON trades(trade_time)",
            "CREATE INDEX IF NOT EXISTS idx_orders_strategy_id ON orders(strategy_id)",
            "CREATE INDEX IF NOT EXISTS idx_orders_ts_code ON orders(ts_code)",
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status)",
            "CREATE INDEX IF NOT EXISTS idx_positions_strategy_id ON positions(strategy_id)",
            "CREATE INDEX IF NOT EXISTS idx_positions_ts_code ON positions(ts_code)",
            "CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_strategy_id ON portfolio_snapshots(strategy_id)",
            "CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date ON portfolio_snapshots(snapshot_date)",
            "CREATE INDEX IF NOT EXISTS idx_execution_logs_strategy_id ON execution_logs(strategy_id)",
            "CREATE INDEX IF NOT EXISTS idx_execution_logs_execution_id ON execution_logs(execution_id)",
            "CREATE INDEX IF NOT EXISTS idx_risk_events_strategy_id ON risk_events(strategy_id)",
            "CREATE INDEX IF NOT EXISTS idx_risk_events_event_time ON risk_events(event_time)",
        ]

        for sql in indexes:
            cursor.execute(sql)
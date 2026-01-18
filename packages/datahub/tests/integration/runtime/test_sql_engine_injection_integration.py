"""Tests for SQL injection prevention in SqlEngine."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import pytest
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.stores.calendar_store import CalendarStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


class TestSqlEngineInjection:
    """Test cases for SQL injection prevention in SqlEngine."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.data_root = Path(self.temp_dir.name)

        # Initialize test database
        db_path = self.data_root / "meta" / "hub.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self.pool = SQLitePool(str(db_path))
        self.pool.init_schema()

        # Create stores
        sqlite_client = SQLiteClient(self.pool)
        self.security_store = SecurityStore(sqlite_client)
        self.calendar_store = CalendarStore(sqlite_client)

        # Create SqlEngine
        self.engine = SqlEngine(
            data_root=self.data_root,
            security_store=self.security_store,
            calendar_store=self.calendar_store,
        )

    def teardown_method(self) -> None:
        """Clean up test environment."""
        try:
            if hasattr(self, "engine"):
                self.engine.close()
        except Exception:
            pass
        try:
            if hasattr(self, "pool"):
                self.pool.close()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_asof_normal_input_works(self) -> None:
        """测试正常 asof 输入应该工作。"""
        # 简单查询测试 $asof 替换
        result = self.engine.execute(
            "SELECT CAST($asof AS DATE) AS asof_date", asof="2024-01-01"
        )

        assert len(result) == 1
        assert result["asof_date"][0] == date(2024, 1, 1)

    def test_sql_injection_prevention(self) -> None:
        """测试 SQL 注入防护。"""
        malicious_inputs = [
            "2024-01-01'; DROP TABLE stock_daily; --",
            "2024-01-01' OR '1'='1",
            "' UNION SELECT * FROM security --",
            "2024-01-01'; INSERT INTO users VALUES ('hacker', 'admin') --",
            "'; EXECUTE IMMEDIATE 'DROP TABLE security'; --",
            "2024-01-01' UNION SELECT * FROM security --",
            "2024-01-01'; SELECT * FROM security WHERE '1'='1' --",
        ]

        for malicious in malicious_inputs:
            with pytest.raises(ValueError, match="Invalid asof"):
                self.engine.execute(
                    "SELECT CAST($asof AS DATE) AS asof_date", asof=malicious
                )

    def test_asof_invalid_format_rejected(self) -> None:
        """测试无效格式的 asof 被拒绝。"""
        invalid_formats = [
            "2024/01/01",  # 错误的分隔符
            "01-01-2024",  # 错误的顺序
            "2024-1-1",  # 缺少前导零
            "24-01-01",  # 两位年份
            "2024-01",  # 缺少日期
            "2024",  # 只有年份
            "not-a-date",  # 完全无效
            "",  # 空字符串
            "2024-01-01   ",  # 尾随空格
            "  2024-01-01",  # 前导空格
        ]

        for invalid in invalid_formats:
            with pytest.raises(ValueError, match="Invalid asof"):
                self.engine.execute(
                    "SELECT CAST($asof AS DATE) AS asof_date", asof=invalid
                )

    def test_asof_invalid_date_rejected_by_duckdb(self) -> None:
        """测试语义无效的日期被 DuckDB 拒绝。"""
        invalid_dates = [
            "2024-13-01",  # 无效月份
            "2024-01-32",  # 无效日期
            "2024-02-30",  # 无效日期（2月没有30号）
        ]

        for invalid in invalid_dates:
            # DuckDB 会拒绝这些无效日期并抛出 Error
            with pytest.raises(duckdb.Error):
                self.engine.execute(
                    "SELECT CAST($asof AS DATE) AS asof_date", asof=invalid
                )

    def test_asof_parameterized_query(self) -> None:
        """测试使用参数化查询。"""
        # 测试 $asof 与其他参数的组合使用
        result = self.engine.execute(
            "SELECT CAST($asof AS DATE) AS asof_date, $1 AS num",
            asof="2024-01-02",
            params=[42],
        )

        assert len(result) == 1
        assert result["asof_date"][0] == date(2024, 1, 2)
        assert result["num"][0] == 42

    def test_asof_with_dict_params_raises_error(self) -> None:
        """测试 $asof 与 dict params 组合使用时应该报错。"""
        with pytest.raises(ValueError, match="Cannot combine"):
            self.engine.execute(
                "SELECT CAST($asof AS DATE) AS asof_date",
                asof="2024-01-01",
                params={"key": "value"},
            )

    def test_asof_none_does_not_modify_query(self) -> None:
        """测试 asof=None 时不修改查询。"""
        # 没有 asof 参数，查询应该保持不变
        result = self.engine.execute("SELECT 1 AS num")

        assert len(result) == 1
        assert result["num"][0] == 1

    def test_asof_in_complex_query(self) -> None:
        """测试在复杂查询中使用 $asof。"""
        result = self.engine.execute(
            """
            SELECT
                CAST($asof AS DATE) AS asof_date,
                CASE
                    WHEN CAST($asof AS DATE) < '2024-02-01'::DATE THEN 'before_feb'
                    ELSE 'after_feb'
                END AS period
            """,
            asof="2024-01-15",
        )

        assert len(result) == 1
        assert result["asof_date"][0] == date(2024, 1, 15)
        assert result["period"][0] == "before_feb"

    def test_multiple_asof_replacements(self) -> None:
        """测试查询中多个 $asof 占位符的替换。"""
        result = self.engine.execute(
            """
            SELECT
                CAST($asof AS DATE) AS asof1,
                CAST($asof AS DATE) AS asof2,
                CAST($asof AS DATE) = CAST($asof AS DATE) AS same
            """,
            asof="2024-03-15",
        )

        assert len(result) == 1
        assert result["asof1"][0] == date(2024, 3, 15)
        assert result["asof2"][0] == date(2024, 3, 15)
        assert result["same"][0] is True

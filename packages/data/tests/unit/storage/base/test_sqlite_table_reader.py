"""Tests for SqliteTableSpec and SqliteTableReader."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from unittest.mock import MagicMock

import pytest
from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.fixture
def balance_sheet_spec() -> SqliteTableSpec:
    return SqliteTableSpec(
        table="balance_sheet",
        columns=(
            "total_assets",
            "total_liabilities",
            "net_assets",
            "current_assets",
            "current_liabilities",
        ),
        id_column="instrument_id",
        date_column="report_date",
    )


@pytest.fixture
def valuation_spec() -> SqliteTableSpec:
    return SqliteTableSpec(
        table="valuation_metrics",
        columns=("pe_ratio", "pb_ratio", "ps_ratio", "dividend_yield", "market_cap"),
        id_column="instrument_id",
        date_column="trade_date",
    )


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


class TestSqliteTableSpec:
    def test_frozen(self, balance_sheet_spec: SqliteTableSpec) -> None:
        with pytest.raises(FrozenInstanceError):
            balance_sheet_spec.table = "other"  # type: ignore[misc]

    def test_default_pit_columns(self, balance_sheet_spec: SqliteTableSpec) -> None:
        assert balance_sheet_spec.pit_columns == (
            "knowledge_date",
            "effective_from",
            "effective_to",
        )

    def test_custom_pit_columns(self) -> None:
        spec = SqliteTableSpec(
            table="test",
            columns=("a",),
            id_column="id",
            date_column="date",
            pit_columns=("effective_from", "effective_to"),
        )
        assert spec.pit_columns == ("effective_from", "effective_to")

    def test_nullable_columns_default(
        self, balance_sheet_spec: SqliteTableSpec
    ) -> None:
        assert balance_sheet_spec.nullable_columns == frozenset()

    def test_nullable_columns_custom(self) -> None:
        spec = SqliteTableSpec(
            table="test",
            columns=("a", "b"),
            id_column="id",
            date_column="date",
            nullable_columns=frozenset({"b"}),
        )
        assert spec.nullable_columns == frozenset({"b"})

    def test_all_columns_includes_id_date_and_pit(
        self, balance_sheet_spec: SqliteTableSpec
    ) -> None:
        all_cols = balance_sheet_spec.all_columns
        assert "instrument_id" in all_cols
        assert "report_date" in all_cols
        assert "knowledge_date" in all_cols
        assert "effective_from" in all_cols
        assert "effective_to" in all_cols
        assert "total_assets" in all_cols

    def test_optional_date_column(self) -> None:
        spec = SqliteTableSpec(
            table="index_composition",
            columns=("instrument_id", "weight"),
            id_column="index_id",
            date_column=None,
            pit_columns=("effective_from", "effective_to"),
        )
        assert spec.date_column is None
        assert "index_id" in spec.all_columns
        assert "weight" in spec.all_columns

    def test_order_by_column(self) -> None:
        spec = SqliteTableSpec(
            table="index_composition",
            columns=("instrument_id", "weight"),
            id_column="index_id",
            order_by_column="instrument_id",
            pit_columns=("effective_from", "effective_to"),
        )
        assert spec.order_by_column == "instrument_id"

    def test_order_by_column_defaults_to_date_column(self) -> None:
        spec = SqliteTableSpec(
            table="test",
            columns=("a",),
            id_column="id",
            date_column="report_date",
        )
        assert spec.order_by_column is None


class TestSqliteTableReader:
    def test_get_delegates_with_report_date(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "instrument_id": 1,
                "report_date": "2024-03-31",
                "knowledge_date": "2024-04-25",
                "effective_from": "2024-04-25",
                "effective_to": None,
                "total_assets": 1000,
                "total_liabilities": 500,
                "net_assets": 500,
                "current_assets": 200,
                "current_liabilities": 100,
            }
        ]

        result = reader.get(1, date(2024, 6, 1))

        assert len(result) == 1
        mock_client.fetchall.assert_called_once()
        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "balance_sheet" in sql
        assert "knowledge_date <= ?" in sql
        assert "effective_from <= ?" in sql
        assert "effective_to IS NULL OR effective_to > ?" in sql
        assert "report_date DESC" in sql
        assert "total_assets" in sql
        assert "knowledge_date" in sql
        assert params == [
            1,
            date(2024, 6, 1),
            date(2024, 6, 1),
            date(2024, 6, 1),
        ]

    def test_get_delegates_with_trade_date(
        self, valuation_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(valuation_spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get(1, date(2024, 6, 1))

        sql = mock_client.fetchall.call_args[0][0]
        assert "trade_date DESC" in sql
        assert "pe_ratio" in sql

    def test_get_returns_empty_dataframe_when_no_rows(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        result = reader.get(1, date(2024, 6, 1))

        assert result.is_empty()

    def test_get_returns_dataframe_with_rows(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "instrument_id": 1,
                "report_date": "2024-03-31",
                "knowledge_date": "2024-04-25",
                "effective_from": "2024-04-25",
                "effective_to": None,
                "total_assets": 1000,
                "total_liabilities": 500,
                "net_assets": 500,
                "current_assets": 200,
                "current_liabilities": 100,
            }
        ]

        result = reader.get(1, date(2024, 6, 1))

        assert not result.is_empty()
        assert result["instrument_id"][0] == 1
        assert result["total_assets"][0] == 1000

    def test_satisfies_sqlite_reader_protocol(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        from ditto_platform.foundation import SqliteReader

        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        _: SqliteReader = reader

    def test_get_range_with_date_range_only(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "instrument_id": 1,
                "report_date": "2024-03-31",
                "knowledge_date": "2024-04-25",
                "effective_from": "2024-04-25",
                "effective_to": None,
                "total_assets": 1000,
                "total_liabilities": 500,
                "net_assets": 500,
                "current_assets": 200,
                "current_liabilities": 100,
            }
        ]

        result = reader.get_range(
            1, start_date=date(2024, 1, 1), end_date=date(2024, 6, 30)
        )

        assert len(result) == 1
        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "report_date >= ?" in sql
        assert "report_date <= ?" in sql
        assert "effective_from <= ?" not in sql
        assert params[0] == 1
        assert params[1] == date(2024, 1, 1)
        assert params[2] == date(2024, 6, 30)

    def test_get_range_with_pit_only(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get_range(1, as_of_date=date(2024, 6, 1))

        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "effective_from <= ?" in sql
        assert "knowledge_date <= ?" in sql
        assert "effective_to IS NULL OR effective_to > ?" in sql
        assert "report_date >=" not in sql
        assert "report_date <=" not in sql
        assert params == [
            1,
            date(2024, 6, 1),
            date(2024, 6, 1),
            date(2024, 6, 1),
        ]

    def test_get_range_with_all_params(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get_range(
            1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            as_of_date=date(2024, 6, 1),
        )

        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "report_date >= ?" in sql
        assert "report_date <= ?" in sql
        assert "effective_from <= ?" in sql
        assert "effective_to IS NULL OR effective_to > ?" in sql
        assert len(params) == 6

    def test_get_range_with_no_filters(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get_range(1)

        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "effective_from <= ?" not in sql
        assert "report_date >=" not in sql
        assert params == [1]

    def test_get_range_returns_empty_when_no_rows(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        result = reader.get_range(1, start_date=date(2024, 1, 1))

        assert result.is_empty()

    def test_order_by_uses_spec_column(self, mock_client: MagicMock) -> None:
        spec = SqliteTableSpec(
            table="index_composition",
            columns=("instrument_id", "weight"),
            id_column="index_id",
            order_by_column="instrument_id",
            pit_columns=("effective_from", "effective_to"),
        )
        reader = SqliteTableReader(spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get(1, date(2024, 6, 1))

        sql = mock_client.fetchall.call_args[0][0]
        assert "ORDER BY instrument_id DESC" in sql

    def test_get_with_str_id_value(self, mock_client: MagicMock) -> None:
        spec = SqliteTableSpec(
            table="index_composition",
            columns=("instrument_id", "weight"),
            id_column="index_id",
            order_by_column="instrument_id",
            pit_columns=("effective_from", "effective_to"),
        )
        reader = SqliteTableReader(spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "index_id": "000300",
                "instrument_id": 1,
                "weight": 0.05,
                "effective_from": "2024-01-01",
                "effective_to": None,
            }
        ]

        result = reader.get("000300", date(2024, 6, 1))

        assert len(result) == 1
        params = mock_client.fetchall.call_args[0][1]
        assert params[0] == "000300"


def _version_row(
    *,
    report_date: str = "2024-03-31",
    knowledge_date: str = "2024-04-25",
    effective_from: str | None = None,
    total_assets: float = 1000.0,
) -> dict[str, object]:
    return {
        "instrument_id": 1,
        "report_date": report_date,
        "knowledge_date": knowledge_date,
        "effective_from": effective_from or knowledge_date,
        "effective_to": None,
        "total_assets": total_assets,
        "total_liabilities": 500.0,
        "net_assets": 500.0,
        "current_assets": 200.0,
        "current_liabilities": 100.0,
    }


class TestVersionDeduplication:
    """#628 P4：同 (id, date) 修订多版本收敛到 as_of 可见的最新 knowledge 版本。"""

    def test_revision_collapses_to_latest_visible_version(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        """修订公告与原公告双开区间共存时，只返回 as_of 可见的最新版本。"""
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            _version_row(knowledge_date="2024-06-01", total_assets=9999.0),
            _version_row(knowledge_date="2024-04-25", total_assets=1000.0),
        ]

        result = reader.get(1, date(2024, 7, 1))

        assert result.height == 1
        assert result["total_assets"][0] == 9999.0
        assert result["knowledge_date"][0] == "2024-06-01"

    def test_knowledge_tie_prefers_later_effective_from(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            _version_row(
                knowledge_date="2024-06-01",
                effective_from="2024-06-01",
                total_assets=1111.0,
            ),
            _version_row(
                knowledge_date="2024-06-01",
                effective_from="2024-06-02",
                total_assets=2222.0,
            ),
        ]

        result = reader.get(1, date(2024, 7, 1))

        assert result.height == 1
        assert result["total_assets"][0] == 2222.0

    def test_output_order_stays_date_desc_across_reports(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        """去重后仍按 date_column 倒序，且修订并列时输出确定。"""
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            _version_row(report_date="2024-03-31", knowledge_date="2024-04-25"),
            _version_row(report_date="2023-12-31", knowledge_date="2024-03-25"),
            _version_row(
                report_date="2024-03-31",
                knowledge_date="2024-06-01",
                total_assets=9999.0,
            ),
        ]

        result = reader.get(1, date(2024, 7, 1))

        assert result["report_date"].to_list() == ["2024-03-31", "2023-12-31"]
        assert result["total_assets"].to_list() == [9999.0, 1000.0]

    def test_get_range_without_asof_keeps_version_history(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        """非 PIT 读取不收敛：版本历史原样返回（corporate_actions 契约）。"""
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            _version_row(knowledge_date="2024-04-25", total_assets=1000.0),
            _version_row(knowledge_date="2024-06-01", total_assets=9999.0),
        ]

        result = reader.get_range(1, start_date=date(2024, 1, 1))

        assert result.height == 2

    def test_no_date_column_keeps_all_rows(self, mock_client: MagicMock) -> None:
        spec = SqliteTableSpec(
            table="members",
            columns=("instrument_id",),
            id_column="group_id",
            date_column=None,
            pit_columns=("effective_from", "effective_to"),
        )
        reader = SqliteTableReader(spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "group_id": "g1",
                "instrument_id": 1,
                "effective_from": "2024-01-01",
                "effective_to": None,
            },
            {
                "group_id": "g1",
                "instrument_id": 2,
                "effective_from": "2024-01-01",
                "effective_to": None,
            },
        ]

        result = reader.get("g1", date(2024, 6, 1))

        assert result.height == 2


_BALANCE_SHEET_DDL = """CREATE TABLE IF NOT EXISTS balance_sheet (
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
    PRIMARY KEY (instrument_id, report_date, effective_from)
)"""


def _insert_version(
    client: SQLiteClient,
    *,
    report_date: str,
    knowledge_date: str,
    effective_to: str | None = None,
    total_assets: float = 1000.0,
) -> None:
    client.execute(
        """INSERT INTO balance_sheet
        (instrument_id, report_date, knowledge_date, effective_from,
         effective_to, total_assets, total_liabilities, net_assets,
         current_assets, current_liabilities)
        VALUES (1, ?, ?, ?, ?, ?, 500, 500, 200, 100)""",
        [
            report_date,
            knowledge_date,
            knowledge_date,
            effective_to,
            total_assets,
        ],
    )
    client.commit()


@pytest.fixture
def real_client() -> SQLiteClient:
    client = SQLiteClient(SQLitePool(":memory:"))
    client.execute(_BALANCE_SHEET_DDL)
    client.commit()
    return client


class TestVersionDeduplicationRealSqlite:
    """真实 SQLite 上验证闸门+去重组合（#628 P4 验收条款）。"""

    def _reader(self, client: SQLiteClient) -> SqliteTableReader:
        return SqliteTableReader(
            SqliteTableSpec(
                table="balance_sheet",
                columns=(
                    "total_assets",
                    "total_liabilities",
                    "net_assets",
                    "current_assets",
                    "current_liabilities",
                ),
                id_column="instrument_id",
                date_column="report_date",
            ),
            client,
        )

    @pytest.mark.pit
    def test_future_sentinel_and_positive_control(
        self, real_client: SQLiteClient
    ) -> None:
        """未来哨兵 + 截止内阳性对照（pit-contract 成对证明）。"""
        _insert_version(
            real_client, report_date="2024-03-31", knowledge_date="2024-04-25"
        )
        reader = self._reader(real_client)

        # 哨兵：as_of 早于 knowledge → 整行不可见
        assert reader.get(1, date(2024, 4, 24)).is_empty()
        # 阳性对照：as_of 达到 knowledge 当日（日终语义）→ 可见
        visible = reader.get(1, date(2024, 4, 25))
        assert visible.height == 1
        assert visible["total_assets"][0] == 1000.0

    @pytest.mark.pit
    def test_late_revision_frozen_before_and_current_after(
        self, real_client: SQLiteClient
    ) -> None:
        """晚到修订：旧 as_of 逐字段稳定，新 as_of 看到修订值。"""
        _insert_version(
            real_client, report_date="2024-03-31", knowledge_date="2024-04-25"
        )
        frozen = self._reader(real_client).get(1, date(2024, 5, 1))

        _insert_version(
            real_client,
            report_date="2024-03-31",
            knowledge_date="2024-06-01",
            total_assets=9999.0,
        )
        reader = self._reader(real_client)

        replay = reader.get(1, date(2024, 5, 1))
        assert replay.equals(frozen)
        assert replay["total_assets"].to_list() == [1000.0]

        current = reader.get(1, date(2024, 7, 1))
        assert current.height == 1
        assert current["total_assets"][0] == 9999.0
        assert current["knowledge_date"][0] == "2024-06-01"

    @pytest.mark.pit
    def test_effective_to_closing_day_half_open_boundary(
        self, real_client: SQLiteClient
    ) -> None:
        """半开边界：effective_to 当日版本关闭，旧版本重新成为可见版本。"""
        _insert_version(
            real_client, report_date="2024-03-31", knowledge_date="2024-04-25"
        )
        _insert_version(
            real_client,
            report_date="2024-03-31",
            knowledge_date="2024-06-01",
            effective_to="2024-06-30",
            total_assets=9999.0,
        )
        reader = self._reader(real_client)

        before_close = reader.get(1, date(2024, 6, 29))
        assert before_close["total_assets"].to_list() == [9999.0]

        on_close = reader.get(1, date(2024, 6, 30))
        assert on_close["total_assets"].to_list() == [1000.0]


class TestFactKeyColumns:
    """#628：事实键外的业务维度不参与修订收敛。"""

    def test_corporate_actions_same_day_distinct_types_both_kept(
        self, mock_client: MagicMock
    ) -> None:
        spec = SqliteTableSpec(
            table="corporate_actions",
            columns=("action_type", "action_date", "description"),
            id_column="instrument_id",
            date_column="action_date",
            fact_key_columns=("instrument_id", "action_date", "action_type"),
        )
        reader = SqliteTableReader(spec, mock_client)

        def action(action_type: str, knowledge: str) -> dict[str, object]:
            return {
                "instrument_id": 1,
                "action_date": "2024-05-01",
                "knowledge_date": knowledge,
                "effective_from": knowledge,
                "effective_to": None,
                "action_type": action_type,
                "description": "x",
            }

        mock_client.fetchall.return_value = [
            action("DIVIDEND", "2024-04-25"),
            action("SPLIT", "2024-04-26"),
        ]

        result = reader.get(1, date(2024, 7, 1))

        assert result.height == 2

    def test_corporate_actions_same_type_revision_collapses(
        self, mock_client: MagicMock
    ) -> None:
        spec = SqliteTableSpec(
            table="corporate_actions",
            columns=("action_type", "action_date", "description"),
            id_column="instrument_id",
            date_column="action_date",
            fact_key_columns=("instrument_id", "action_date", "action_type"),
        )
        reader = SqliteTableReader(spec, mock_client)

        def action(knowledge: str, description: str) -> dict[str, object]:
            return {
                "instrument_id": 1,
                "action_date": "2024-05-01",
                "knowledge_date": knowledge,
                "effective_from": knowledge,
                "effective_to": None,
                "action_type": "DIVIDEND",
                "description": description,
            }

        mock_client.fetchall.return_value = [
            action("2024-04-25", "0.3/share"),
            action("2024-05-01", "0.5/share revised"),
        ]

        result = reader.get(1, date(2024, 7, 1))

        assert result.height == 1
        assert result["description"][0] == "0.5/share revised"


class TestDividendNullExDateFactKey:
    """#628 双轴评审反例：ex_dividend_date NULL 的不同分红事实不得被收敛。"""

    def test_distinct_null_ex_date_announcements_both_kept(
        self, mock_client: MagicMock
    ) -> None:
        spec = SqliteTableSpec(
            table="dividend",
            columns=("dividend_per_share", "dividend_yield", "div_proc"),
            id_column="instrument_id",
            date_column="ex_dividend_date",
            nullable_columns=frozenset(
                {
                    "effective_to",
                    "ex_dividend_date",
                    "dividend_per_share",
                    "dividend_yield",
                    "div_proc",
                }
            ),
            fact_key_columns=("instrument_id", "ex_dividend_date", "effective_from"),
        )
        reader = SqliteTableReader(spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "instrument_id": 1,
                "ex_dividend_date": None,
                "div_proc": "预案",
                "dividend_per_share": 0.3,
                "dividend_yield": None,
                "knowledge_date": "2024-04-25",
                "effective_from": "2024-04-25",
                "effective_to": None,
            },
            {
                "instrument_id": 1,
                "ex_dividend_date": None,
                "div_proc": "预案",
                "dividend_per_share": 0.1,
                "dividend_yield": None,
                "knowledge_date": "2024-08-25",
                "effective_from": "2024-08-25",
                "effective_to": None,
            },
        ]

        result = reader.get(1, date(2024, 12, 1))

        assert result.height == 2
        assert sorted(result["dividend_per_share"].to_list()) == [0.1, 0.3]

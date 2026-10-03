"""#395 名称/ST 历史写侧集成测试（真实 SQLite seam）。

覆盖：带证据三元组写入、缺真实生效日期拒绝、幂等、PIT 读取、
晚到更名/ST 不进更早 cutoff、未知证券拒绝。
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.services.metadata.instrument import (
    InstrumentService,
    InstrumentServiceDeps,
)
from ditto_data.storage.market.stock.status import (
    StChangeHistoryReader,
    StChangeHistoryWriter,
)
from ditto_data.storage.metadata.instrument import (
    InstrumentReader,
    InstrumentRegistration,
    InstrumentWriter,
    NameHistoryReader,
    NameHistoryWriter,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool

_OBSERVED = "2026-09-19 08:00:00"


@pytest.mark.integration
class TestHistoryWriteSideIntegration:
    """namechange / st_history 写入与 PIT 读取。"""

    @pytest.fixture
    def client(self) -> SQLiteClient:
        pool = SQLitePool(db_path=":memory:")
        client = SQLiteClient(pool)
        schema_sql = """
            CREATE TABLE instrument (
                instrument_id INTEGER PRIMARY KEY,
                ticker TEXT NOT NULL,
                name TEXT,
                display_name TEXT,
                exchange TEXT NOT NULL,
                board TEXT,
                asset_class TEXT NOT NULL,
                list_date DATE,
                delist_date DATE,
                is_st BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            );
            CREATE TABLE instrument_mapping (
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
            CREATE TABLE instrument_name_history (
                instrument_id INTEGER NOT NULL,
                old_name TEXT,
                new_name TEXT NOT NULL,
                changed_date DATE NOT NULL,
                source TEXT NOT NULL DEFAULT 'tushare',
                observed_at TEXT,
                PRIMARY KEY (instrument_id, changed_date, source, observed_at),
                FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
            );
            CREATE TABLE st_change_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_id INTEGER NOT NULL,
                effective_from DATE NOT NULL,
                is_st INTEGER NOT NULL,
                st_type TEXT,
                effective_to DATE,
                source TEXT NOT NULL DEFAULT 'tushare',
                observed_at TEXT,
                FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
            );
            CREATE TABLE instrument_stock (
                instrument_id INTEGER PRIMARY KEY,
                list_status TEXT,
                industry_id INTEGER
            );
            CREATE UNIQUE INDEX idx_st_change_history_source_key
                ON st_change_history(
                    instrument_id, effective_from, source, observed_at
                );
        """
        client.executescript(schema_sql)
        writer = InstrumentWriter(client)
        for instrument_id, ticker, name in (
            (1_000_001, "000001", "平安银行"),
            (1_000_002, "000002", "万科A"),
        ):
            suffix = "SZ"
            writer.register(
                instrument_id,
                InstrumentRegistration(
                    source_ticker=f"{ticker}.{suffix}",
                    ticker=ticker,
                    name=name,
                    exchange="SZSE",
                    asset_class="stock",
                    list_date="1991-04-03",
                    source="tushare",
                ),
            )
        return client

    @pytest.fixture
    def service(self, client: SQLiteClient) -> InstrumentService:
        return InstrumentService(
            InstrumentServiceDeps(
                instrument_reader=InstrumentReader(client),
                instrument_writer=InstrumentWriter(client),
                name_history_reader=NameHistoryReader(client, MagicMock()),
                name_history_writer=NameHistoryWriter(client, MagicMock()),
                st_change_history_reader=StChangeHistoryReader(client, MagicMock()),
                st_change_history_writer=StChangeHistoryWriter(client, MagicMock()),
                industry_reader=MagicMock(),
                industry_writer=MagicMock(),
                industry_mapping_reader=MagicMock(),
                industry_mapping_writer=MagicMock(),
                instrument_id_allocator=MagicMock(),
                exchange_transformers=MagicMock(),
            )
        )

    # ── namechange 写侧 ──────────────────────────────────────────

    def test_name_history_writes_evidence_triple(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """写入行带 生效时间 + 可知时间(published_at→observed) + 来源。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "old_name": ["深发展A"],
                "new_name": ["平安银行"],
                "changed_date": [date(2012, 1, 9)],
                "effective_to": [None],
                "change_reason": ["更名"],
                "published_at": [date(2012, 1, 7)],
            }
        )
        written = service.save_name_history(df, source="tushare", observed_at=_OBSERVED)

        assert written == 1
        row = client.fetchone(
            "SELECT * FROM instrument_name_history WHERE instrument_id = ?",
            [1_000_001],
        )
        assert row is not None
        assert row["changed_date"] == "2012-01-09"
        assert row["source"] == "tushare"
        # provider published_at 优先于观察时间（date-only 公告保留日期粒度）
        assert row["observed_at"] == "2012-01-07"

    def test_name_history_rejects_missing_effective_date(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """缺真实生效日期的行拒绝，不以默认日期冒充历史。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "old_name": [None],
                "new_name": ["无名"],
                "changed_date": [None],
                "effective_to": [None],
                "change_reason": ["x"],
                "published_at": [None],
            }
        )
        written = service.save_name_history(df, source="tushare", observed_at=_OBSERVED)

        assert written == 0
        count = client.fetchone("SELECT COUNT(*) AS n FROM instrument_name_history")
        assert count is not None
        assert count["n"] == 0

    def test_name_history_idempotent_reregistration(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """同 (instrument_id, changed_date, source) 重复登记幂等。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ", "000001.SZ"],
                "old_name": [None, "深发展A"],
                "new_name": ["深发展A", "平安银行"],
                "changed_date": [date(2010, 6, 1), date(2012, 1, 9)],
                "effective_to": [date(2012, 1, 9), None],
                "change_reason": ["x", "更名"],
                "published_at": [None, None],
            }
        )
        service.save_name_history(df, source="tushare", observed_at=_OBSERVED)
        again = service.save_name_history(
            df, source="tushare", observed_at="2026-09-20 08:00:00"
        )

        assert again == 2  # 幂等替换而非报错
        count = client.fetchone("SELECT COUNT(*) AS n FROM instrument_name_history")
        assert count is not None
        assert count["n"] == 2

    def test_name_history_rejects_unknown_identity(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """未知证券行拒绝。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["999999.SZ"],
                "old_name": [None],
                "new_name": ["未知"],
                "changed_date": [date(2012, 1, 9)],
                "effective_to": [None],
                "change_reason": ["x"],
                "published_at": [None],
            }
        )
        written = service.save_name_history(df, source="tushare", observed_at=_OBSERVED)
        assert written == 0

    def test_late_name_change_not_visible_at_earlier_cutoff(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """晚到更名不能进入更早 cutoff（秒粒度 fail closed）。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "old_name": ["深发展A"],
                "new_name": ["平安银行"],
                "changed_date": [date(2012, 1, 9)],
                "effective_to": [None],
                "change_reason": ["更名"],
                # 晚到公告：2013 年才记录
                "published_at": [date(2013, 6, 1)],
            }
        )
        service.save_name_history(df, source="tushare", observed_at=_OBSERVED)

        reader = NameHistoryReader(client, MagicMock())
        # 2012-10-01 的知识截止：更名尚未可知 → 不返回
        assert (
            reader.get_name(1_000_001, "2012-10-01", cutoff="2012-10-01 00:00:00")
            is None
        )
        # 2013-07-01 的知识截止：可见
        assert (
            reader.get_name(1_000_001, "2013-07-01", cutoff="2013-07-01 00:00:00")
            == "平安银行"
        )

    # ── st_history 写侧 ──────────────────────────────────────────

    def test_st_history_writes_evidence_and_derives_state(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """change_reason 推导 is_st/st_type；撤销事件写非 ST 闭合区间。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ", "000001.SZ", "000002.SZ"],
                "change_date": [date(2020, 4, 1), date(2022, 6, 1), date(2021, 1, 1)],
                "end_date": [date(2022, 6, 1), None, None],
                "change_reason": ["ST", "撤销ST", "*ST"],
                "published_at": [None, None, None],
            }
        )
        written = service.save_st_change_history(
            df, source="tushare", observed_at=_OBSERVED
        )

        assert written == 3
        st_2021: dict[str, Any] | None = client.fetchone(
            """SELECT is_st, st_type, effective_to FROM st_change_history
            WHERE instrument_id = ? AND effective_from = '2020-04-01'""",
            [1_000_001],
        )
        assert st_2021 is not None
        assert st_2021["is_st"] == 1
        assert st_2021["st_type"] == "ST"
        assert st_2021["effective_to"] == "2022-06-01"

        star_row = client.fetchone(
            """SELECT is_st, st_type FROM st_change_history
            WHERE instrument_id = ? AND effective_from = '2021-01-01'""",
            [1_000_002],
        )
        assert star_row is not None
        assert star_row["is_st"] == 1
        assert star_row["st_type"] == "*ST"

        # PIT 读取：撤销后为非 ST
        reader = StChangeHistoryReader(client, MagicMock())
        after_repeal = reader.get_st_status(1_000_001, "2022-07-01")
        assert after_repeal is not None
        assert after_repeal["is_st"] is False
        before_st = reader.get_st_status(1_000_001, "2020-03-31")
        assert before_st is None  # 无证据区间不默认正常

    def test_st_history_rejects_missing_effective_date(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """缺真实生效日期的 ST 行拒绝。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "change_date": [None],
                "end_date": [None],
                "change_reason": ["ST"],
                "published_at": [None],
            }
        )
        written = service.save_st_change_history(
            df, source="tushare", observed_at=_OBSERVED
        )
        assert written == 0
        count = client.fetchone("SELECT COUNT(*) AS n FROM st_change_history")
        assert count is not None
        assert count["n"] == 0

    def test_late_st_change_not_visible_at_earlier_cutoff(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """晚到 ST 事件不能进入更早 cutoff。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "change_date": [date(2020, 4, 1)],
                "end_date": [None],
                "change_reason": ["ST"],
                "published_at": [date(2021, 1, 1)],  # 晚到公告
            }
        )
        service.save_st_change_history(df, source="tushare", observed_at=_OBSERVED)

        reader = StChangeHistoryReader(client, MagicMock())
        # cutoff 早于公告 → 无证据
        early = reader.get_st_status(
            1_000_001, "2020-06-01", cutoff="2020-12-31 00:00:00"
        )
        assert early is None
        # cutoff 晚于公告 → 证据可见
        late = reader.get_st_status(
            1_000_001, "2020-06-01", cutoff="2021-02-01 00:00:00"
        )
        assert late is not None
        assert late["is_st"] is True

    def test_st_history_idempotent_reregistration(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """(instrument_id, effective_from, source) 重复登记幂等。"""
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "change_date": [date(2020, 4, 1)],
                "end_date": [None],
                "change_reason": ["ST"],
                "published_at": [None],
            }
        )
        service.save_st_change_history(df, source="tushare", observed_at=_OBSERVED)
        again = service.save_st_change_history(
            df, source="tushare", observed_at="2026-09-20 08:00:00"
        )
        assert again == 1
        count = client.fetchone("SELECT COUNT(*) AS n FROM st_change_history")
        assert count is not None
        assert count["n"] == 1

    def test_get_stock_status_unknown_without_evidence(
        self, service: InstrumentService
    ) -> None:
        """无证据时 get_stock_status 返回显式未知（不被默认值伪装）。"""
        status = service.get_stock_status(1_000_001, "2026-01-01")
        assert status["has_evidence"] is False
        assert status["is_st"] is None
        assert status["list_status"] is None

    @pytest.mark.pit
    def test_st_reobservation_and_revision_preserve_past(self, service):
        frame = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "change_date": ["2026-09-01"],
                "change_reason": ["ST"],
                "published_at": [None],
            }
        )
        service.save_st_change_history(
            frame, source="tushare", observed_at="2026-09-02 08:00:00"
        )
        before = service.get_st_status_batch(
            [1000001], "2026-09-03", cutoff="2026-09-03 12:00:00"
        )
        service.save_st_change_history(
            frame, source="tushare", observed_at="2026-10-01 08:00:00"
        )
        assert (
            service.get_st_status_batch(
                [1000001], "2026-09-03", cutoff="2026-09-03 12:00:00"
            )
            == before
        )
        corrected = frame.with_columns(pl.lit("撤销ST").alias("change_reason"))
        service.save_st_change_history(
            corrected, source="tushare", observed_at="2026-10-02 08:00:00"
        )
        assert (
            service.get_st_status_batch(
                [1000001], "2026-09-03", cutoff="2026-09-03 12:00:00"
            )
            == before
        )
        assert (
            service.get_st_status_batch(
                [1000001], "2026-09-03", cutoff="2026-10-03 12:00:00"
            )[1000001]["is_st"]
            is False
        )

    @pytest.mark.pit
    def test_name_reobservation_and_revision_preserve_past(self, service):
        frame = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "changed_date": ["2026-09-01"],
                "new_name": ["original"],
                "published_at": [None],
            }
        )
        service.save_name_history(
            frame, source="tushare", observed_at="2026-09-02 08:00:00"
        )
        service.save_name_history(
            frame, source="tushare", observed_at="2026-10-01 08:00:00"
        )
        assert (
            service.get_stock_names(
                [1000001], "2026-09-03", cutoff="2026-09-03 12:00:00"
            )[1000001]
            == "original"
        )
        service.save_name_history(
            frame.with_columns(pl.lit("corrected").alias("new_name")),
            source="tushare",
            observed_at="2026-10-02 08:00:00",
        )
        assert (
            service.get_stock_names(
                [1000001], "2026-09-03", cutoff="2026-09-03 12:00:00"
            )[1000001]
            == "original"
        )
        assert (
            service.get_stock_names(
                [1000001], "2026-09-03", cutoff="2026-10-03 12:00:00"
            )[1000001]
            == "corrected"
        )

    @pytest.mark.pit
    def test_st_correction_closing_interval_does_not_resurrect_old_version(
        self, service
    ):
        frame = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "change_date": ["2026-09-01"],
                "change_reason": ["ST"],
                "end_date": [None],
            }
        )
        service.save_st_change_history(
            frame, source="tushare", observed_at="2026-09-02 08:00:00"
        )
        service.save_st_change_history(
            frame.with_columns(pl.lit("2026-09-03").alias("end_date")),
            source="tushare",
            observed_at="2026-09-10 08:00:00",
        )
        assert service.get_st_status_batch(
            [1000001], "2026-09-04", cutoff="2026-09-05 00:00:00"
        )
        assert (
            service.get_st_status_batch(
                [1000001], "2026-09-04", cutoff="2026-09-11 00:00:00"
            )
            == {}
        )

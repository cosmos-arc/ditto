"""#395 fuyao 来源映射接 instrument_id 的 SQLite 集成测试。

覆盖：映射有效区间解析、未知映射拒绝、重复映射拒绝、注册幂等、
裸码前缀规则唯一匹配（含交易所一致性校验）。
"""

from unittest.mock import MagicMock

import pytest
from ditto_data.services.metadata.instrument import (
    InstrumentService,
    InstrumentServiceDeps,
)
from ditto_data.storage.metadata.instrument import (
    InstrumentReader,
    InstrumentRegistration,
    InstrumentWriter,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.mark.integration
class TestFuyaoSourceMappingIntegration:
    """fuyao instrument_mapping 登记与解析（真实 SQLite seam）。"""

    @pytest.fixture
    def pool(self) -> SQLitePool:
        return SQLitePool(db_path=":memory:")

    @pytest.fixture
    def client(self, pool: SQLitePool) -> SQLiteClient:
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
            CREATE INDEX idx_security_ticker ON instrument(ticker);
        """
        client.executescript(schema_sql)
        return client

    @pytest.fixture
    def reader(self, client: SQLiteClient) -> InstrumentReader:
        return InstrumentReader(client)

    @pytest.fixture
    def writer(self, client: SQLiteClient) -> InstrumentWriter:
        return InstrumentWriter(client)

    @pytest.fixture
    def service(
        self, client: SQLiteClient, reader: InstrumentReader, writer: InstrumentWriter
    ) -> InstrumentService:
        writer.register(
            1_000_001,
            InstrumentRegistration(
                source_ticker="600000.SH",
                ticker="600000",
                name="浦发银行",
                exchange="SSE",
                asset_class="stock",
                list_date="1999-11-10",
                source="tushare",
            ),
        )
        return InstrumentService(
            InstrumentServiceDeps(
                instrument_reader=reader,
                instrument_writer=writer,
                name_history_reader=MagicMock(),
                name_history_writer=MagicMock(),
                industry_reader=MagicMock(),
                industry_writer=MagicMock(),
                industry_mapping_reader=MagicMock(),
                industry_mapping_writer=MagicMock(),
                instrument_id_allocator=MagicMock(),
                exchange_transformers=MagicMock(),
            )
        )

    def test_registers_and_resolves_fuyao_mapping_with_evidence_date(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """前缀规则唯一匹配 → 登记 effective_from=有证据日期并可解析。"""
        resolved = service.resolve_fuyao_instrument_ids(
            ["600000.SH"],
            evidence_dates={"600000.SH": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )

        assert resolved == {"600000.SH": 1_000_001}
        row = client.fetchone(
            """SELECT instrument_id, effective_from, is_primary, created_at
            FROM instrument_mapping WHERE source = 'fuyao'"""
        )
        assert row is not None
        assert row["instrument_id"] == 1_000_001
        assert row["effective_from"] == "2026-09-18"
        assert row["is_primary"] == 0
        assert row["created_at"] == "2026-09-19 08:00:00"

    def test_mapping_resolves_via_effective_interval(
        self, service: InstrumentService, reader: InstrumentReader
    ) -> None:
        """已登记映射按生效区间解析：asof 早于 effective_from 不可见。"""
        service.resolve_fuyao_instrument_ids(
            ["600000.SH"],
            evidence_dates={"600000.SH": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )

        # asof 在生效区间内 → 命中
        visible = reader.resolve_instrument_ids_batch(
            ["600000.SH"], "fuyao", "2026-09-18"
        )
        assert visible == {"600000.SH": 1_000_001}

        # asof 早于生效区间 → fail closed 不解析
        earlier = reader.resolve_instrument_ids_batch(
            ["600000.SH"], "fuyao", "2026-09-17"
        )
        assert earlier == {}

    def test_registration_is_idempotent(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """已存在同向映射时重复解析不重复写行。"""
        service.resolve_fuyao_instrument_ids(
            ["600000.SH"],
            evidence_dates={"600000.SH": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )
        again = service.resolve_fuyao_instrument_ids(
            ["600000.SH"],
            evidence_dates={"600000.SH": "2026-09-20"},
            observed_at="2026-09-21 08:00:00",
            register_missing=True,
        )

        assert again == {"600000.SH": 1_000_001}
        count = client.fetchone(
            "SELECT COUNT(*) AS n FROM instrument_mapping WHERE source = 'fuyao'"
        )
        assert count is not None
        assert count["n"] == 1

    def test_dated_mapping_is_authoritative(
        self, service: InstrumentService, writer: InstrumentWriter, client: SQLiteClient
    ) -> None:
        """历史有效映射优先于当前裸代码匹配，不写出第二个映射。"""
        writer.register(
            1_000_099,
            InstrumentRegistration(
                source_ticker="999999.SH",
                ticker="999999",
                name="既有实体",
                exchange="SSE",
                asset_class="stock",
                list_date="2010-01-01",
                source="tushare",
            ),
        )
        client.execute(
            """INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from, effective_to,
             is_primary, created_at)
            VALUES (?, 'fuyao', '600000.SH', '2010-01-01', '2027-12-31', FALSE,
                    '2010-01-01 00:00:00')""",
            [1_000_099],
        )
        client.commit()

        resolved = service.resolve_fuyao_instrument_ids(
            ["600000.SH"],
            evidence_dates={"600000.SH": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )

        assert resolved == {"600000.SH": 1_000_099}
        rows = client.fetchall(
            "SELECT instrument_id FROM instrument_mapping WHERE source = 'fuyao'"
        )
        assert rows is not None
        assert {int(row["instrument_id"]) for row in rows} == {1_000_099}

    def test_closed_non_overlapping_mapping_allows_new_interval(
        self, service: InstrumentService, writer: InstrumentWriter, client: SQLiteClient
    ) -> None:
        """已闭合且不与新区间重叠的旧映射不阻塞登记新开放区间。"""
        writer.register(
            1_000_099,
            InstrumentRegistration(
                source_ticker="999999.SH",
                ticker="999999",
                name="既有实体",
                exchange="SSE",
                asset_class="stock",
                list_date="2010-01-01",
                source="tushare",
            ),
        )
        client.execute(
            """INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from, effective_to,
             is_primary, created_at)
            VALUES (?, 'fuyao', '600000.SH', '2010-01-01', '2015-12-31', FALSE,
                    '2010-01-01 00:00:00')""",
            [1_000_099],
        )
        client.commit()

        resolved = service.resolve_fuyao_instrument_ids(
            ["600000.SH"],
            evidence_dates={"600000.SH": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )

        assert resolved == {"600000.SH": 1_000_001}
        rows = client.fetchall(
            "SELECT instrument_id FROM instrument_mapping "
            "WHERE source = 'fuyao' AND effective_to IS NULL"
        )
        assert rows is not None
        assert {int(row["instrument_id"]) for row in rows} == {1_000_001}

    def test_unknown_ticker_stays_unresolved(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """无法唯一匹配的键保持未解析（未知映射），不落任何行。"""
        resolved = service.resolve_fuyao_instrument_ids(
            ["300999.SZ"],
            evidence_dates={"300999.SZ": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )

        assert resolved == {}
        count = client.fetchone(
            "SELECT COUNT(*) AS n FROM instrument_mapping WHERE source = 'fuyao'"
        )
        assert count is not None
        assert count["n"] == 0

    def test_unrecognized_prefix_left_unresolved_with_trace(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """#516：未识别前缀（900xxx B 股）按规则 5 不解析，不中断其余键."""
        resolved = service.resolve_fuyao_instrument_ids(
            ["600000.SH", "900901"],
            evidence_dates={"600000.SH": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )

        assert resolved == {"600000.SH": 1_000_001}
        # 未识别前缀的裸码不登记任何映射（不猜测交易所）
        rows = client.fetchall(
            "SELECT source_ticker FROM instrument_mapping WHERE source = 'fuyao'"
        )
        assert [row["source_ticker"] for row in rows] == ["600000.SH"]

    def test_read_only_mode_never_writes(
        self, service: InstrumentService, writer: InstrumentWriter, client: SQLiteClient
    ) -> None:
        """对账只读模式（register_missing=False）可复用既有映射但不写新行。"""
        service.resolve_fuyao_instrument_ids(
            ["600000.SH"],
            evidence_dates={"600000.SH": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )
        # 只读解析新键：裸码可匹配但不登记
        writer.register(
            1_000_003,
            InstrumentRegistration(
                source_ticker="000001.SZ",
                ticker="000001",
                name="平安银行",
                exchange="SZSE",
                asset_class="stock",
                list_date="1991-04-03",
                source="tushare",
            ),
        )
        resolved = service.resolve_fuyao_instrument_ids(
            ["600000.SH", "000001.SZ"], register_missing=False
        )

        assert resolved == {"600000.SH": 1_000_001, "000001.SZ": 1_000_003}
        count = client.fetchone(
            "SELECT COUNT(*) AS n FROM instrument_mapping WHERE source = 'fuyao'"
        )
        assert count is not None
        assert count["n"] == 1

    def test_exchange_mismatch_blocks_reuse(
        self, service: InstrumentService, writer: InstrumentWriter
    ) -> None:
        """裸码命中但后缀推导交易所与注册交易所不一致 → 不复用。"""
        writer.register(
            1_000_004,
            InstrumentRegistration(
                source_ticker="600519.SH",
                ticker="600519",
                name="贵州茅台",
                exchange="SZSE",  # 故意错配（注册交易所与前缀规则不一致）
                asset_class="stock",
                list_date="2001-08-27",
                source="tushare",
            ),
        )
        resolved = service.resolve_fuyao_instrument_ids(
            ["600519.SH"],
            evidence_dates={"600519.SH": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )

        assert "600519.SH" not in resolved

    @pytest.mark.pit
    def test_existing_mapping_cannot_leak_before_effective_date(self, service):
        service.resolve_fuyao_instrument_ids(
            ["600000.SH"],
            evidence_dates={"600000.SH": "2026-09-18"},
            observed_at="2026-09-19 08:00:00",
            register_missing=True,
        )
        assert (
            service.resolve_fuyao_instrument_ids(
                ["600000.SH"],
                evidence_dates={"600000.SH": "2026-08-01"},
                observed_at="2026-10-01 08:00:00",
                register_missing=True,
            )
            == {}
        )
        assert service.resolve_fuyao_instrument_ids(
            ["600000.SH"],
            evidence_dates={"600000.SH": "2026-09-18"},
            register_missing=False,
        ) == {"600000.SH": 1000001}

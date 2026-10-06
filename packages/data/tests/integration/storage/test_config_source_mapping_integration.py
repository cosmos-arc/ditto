"""#408 config 来源映射接 instrument_id 的 SQLite 集成测试。

覆盖：最早证据日锚定、未解析身份时全批不登记（失败载荷无 canonical
副作用）、已知但区间外的身份不回退当前注册表、注册幂等。
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
class TestConfigSourceMappingIntegration:
    """config instrument_mapping 登记（#408，真实 SQLite seam）。"""

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
            2_000_801,
            InstrumentRegistration(
                source_ticker="510300.SH",
                ticker="510300",
                name="沪深300ETF",
                exchange="SSE",
                asset_class="etf",
                list_date="2012-05-28",
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

    def test_anchor_is_earliest_evidence_date(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """身份锚定=最早证据日，不随声明字段排序漂移。"""
        # 调用方（data_writer）按 min(effective_from) 汇聚后传入。
        resolved = service.resolve_config_reference_instruments(
            ["510300.SH"],
            evidence_dates={"510300.SH": "2012-05-28"},
            observed_at="2026-10-05T15:00:00Z",
        )
        assert resolved == {"510300.SH": 2_000_801}
        row = client.fetchone(
            "SELECT effective_from FROM instrument_mapping WHERE source = 'config'"
        )
        assert row is not None
        assert row["effective_from"] == "2012-05-28"

    def test_unresolved_identity_leaves_no_mappings(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """存在未解析标的时整批不登记（失败载荷无 canonical 副作用）。"""
        resolved = service.resolve_config_reference_instruments(
            ["510300.SH", "999999.SH"],
            evidence_dates={"510300.SH": "2026-09-01", "999999.SH": "2026-09-01"},
            observed_at="2026-10-05T15:00:00Z",
        )
        assert resolved == {}
        count = client.fetchone(
            "SELECT COUNT(*) AS n FROM instrument_mapping WHERE source = 'config'"
        )
        assert count is not None
        assert count["n"] == 0

    def test_known_out_of_range_mapping_never_falls_back(
        self,
        service: InstrumentService,
        writer: InstrumentWriter,
        client: SQLiteClient,
    ) -> None:
        """已知但区间外的 config 身份不得回退当前注册表（fuyao 同守卫）。"""
        registered = writer.register_source_mapping(
            instrument_id=2_000_801,
            source="config",
            source_ticker="510300.SH",
            effective_from="2030-01-01",
            observed_at="2026-10-05T15:00:00Z",
        )
        assert registered is True
        resolved = service.resolve_config_reference_instruments(
            ["510300.SH"],
            evidence_dates={"510300.SH": "2026-09-29"},
            observed_at="2026-10-05T15:00:00Z",
        )
        assert resolved == {}
        count = client.fetchone(
            "SELECT COUNT(*) AS n FROM instrument_mapping WHERE source = 'config'"
        )
        assert count is not None
        assert count["n"] == 1  # 仅既有未来映射，未新增

    def test_registration_is_idempotent(
        self, service: InstrumentService, client: SQLiteClient
    ) -> None:
        """重复解析同向映射幂等，不重复写行。"""
        first = service.resolve_config_reference_instruments(
            ["510300.SH"],
            evidence_dates={"510300.SH": "2012-05-28"},
            observed_at="2026-10-05T15:00:00Z",
        )
        again = service.resolve_config_reference_instruments(
            ["510300.SH"],
            evidence_dates={"510300.SH": "2026-09-29"},
            observed_at="2026-10-06T15:00:00Z",
        )
        assert first == again == {"510300.SH": 2_000_801}
        count = client.fetchone(
            "SELECT COUNT(*) AS n FROM instrument_mapping WHERE source = 'config'"
        )
        assert count is not None
        assert count["n"] == 1

"""#603 register_source_mapping 区间可用性谓词集成测试。

覆盖闭合区间/开放区间的角落语义（开区间端点比较，effective_to 排他端，
与读取侧 as-of 谓词一致）：
- 幂等授予仅当自有**开放**区间 from ≤ 新起点（部分重叠不算覆盖）。
- 冲突检测先于幂等判定，环序不漏检别家区间。
- 同起点闭合区间重注册（PK 形状不可写）fail-closed 拒绝。
- 端点相接的跨 instrument 切换合法（排他端点，无双覆盖）。
"""

import pytest
from ditto_data.storage.metadata.instrument import InstrumentWriter
from ditto_platform.foundation import SQLiteClient, SQLitePool

_SCHEMA = """
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
"""


@pytest.mark.integration
class TestSourceMappingIntervalPredicates:
    """#603 instrument_mapping 登记区间谓词（真实 SQLite seam）。"""

    @pytest.fixture
    def client(self) -> SQLiteClient:
        client = SQLiteClient(SQLitePool(db_path=":memory:"))
        client.executescript(_SCHEMA)
        return client

    @pytest.fixture
    def writer(self, client: SQLiteClient) -> InstrumentWriter:
        return InstrumentWriter(client)

    def _seed_instruments(self, client: SQLiteClient, ids: list[int]) -> None:
        for instrument_id in ids:
            client.execute(
                """INSERT INTO instrument
                (instrument_id, ticker, name, exchange, asset_class)
                VALUES (?, ?, ?, 'XSHE', 'stock')""",
                [instrument_id, f"T{instrument_id}", f"name{instrument_id}"],
            )
        client.commit()

    def _seed_mapping(
        self,
        client: SQLiteClient,
        instrument_id: int,
        effective_from: str,
        effective_to: str | None,
        source_ticker: str = "830001.BJ",
    ) -> None:
        client.execute(
            """INSERT INTO instrument_mapping
            (instrument_id, source, source_ticker, effective_from, effective_to)
            VALUES (?, 'tushare', ?, ?, ?)""",
            [instrument_id, source_ticker, effective_from, effective_to],
        )
        client.commit()

    def _mapping_rows(
        self, client: SQLiteClient, source_ticker: str = "830001.BJ"
    ) -> list[tuple[int, str, str | None]]:
        rows = client.fetchall(
            """SELECT instrument_id, effective_from, effective_to
            FROM instrument_mapping
            WHERE source = 'tushare' AND source_ticker = ?
            ORDER BY effective_from""",
            [source_ticker],
        )
        return [
            (int(r["instrument_id"]), str(r["effective_from"]), r["effective_to"])
            for r in rows
        ]

    def test_head_corner_earlier_from_writes_new_row(
        self, client: SQLiteClient, writer: InstrumentWriter
    ) -> None:
        """头侧越界：自有开放区间 [2021,∞)，注册 f=1990 → 必须真写行。

        旧谓词按部分重叠直接判幂等 True，[1990,2021) 实际无覆盖。
        """
        self._seed_instruments(client, [1])
        self._seed_mapping(client, 1, "2021-01-01", None)

        ok = writer.register_source_mapping(
            instrument_id=1,
            source="tushare",
            source_ticker="830001.BJ",
            effective_from="1990-01-01",
            observed_at="2026-10-25 00:00:00",
        )

        assert ok is True
        assert self._mapping_rows(client) == [
            (1, "1990-01-01", None),
            (1, "2021-01-01", None),
        ]

    def test_same_start_closed_reregister_fail_closed(
        self, client: SQLiteClient, writer: InstrumentWriter
    ) -> None:
        """同起点闭合区间重注册：PK 形状不可写 → fail-closed 拒绝。

        自有闭合 [1990,2025-10-09)，再注册 f=1990-01-01：INSERT 撞
        PRIMARY KEY (source, source_ticker, effective_from)，不得静默
        吞行后假报 available；重开放既有区间会破坏切换语义，也不可行。
        """
        self._seed_instruments(client, [1])
        self._seed_mapping(client, 1, "1990-01-01", "2025-10-09")

        ok = writer.register_source_mapping(
            instrument_id=1,
            source="tushare",
            source_ticker="830001.BJ",
            effective_from="1990-01-01",
            observed_at="2026-10-25 00:00:00",
        )

        assert ok is False
        assert self._mapping_rows(client) == [(1, "1990-01-01", "2025-10-09")]

    def test_gap_before_own_open_row_writes_coverage(
        self, client: SQLiteClient, writer: InstrumentWriter
    ) -> None:
        """缺口吞没：自有闭合 [2020,2024) + 自有开放 [2025-06,∞)，注册
        f=2024-01-01 → 必须写行补 [2024,∞)，不得被后方开放行幂等吞掉。
        """
        self._seed_instruments(client, [1])
        self._seed_mapping(client, 1, "2020-01-01", "2024-01-01")
        self._seed_mapping(client, 1, "2025-06-01", None)

        ok = writer.register_source_mapping(
            instrument_id=1,
            source="tushare",
            source_ticker="830001.BJ",
            effective_from="2024-01-01",
            observed_at="2026-10-25 00:00:00",
        )

        assert ok is True
        assert self._mapping_rows(client) == [
            (1, "2020-01-01", "2024-01-01"),
            (1, "2024-01-01", None),
            (1, "2025-06-01", None),
        ]

    def test_conflict_beats_own_overlap_regardless_of_row_order(
        self, client: SQLiteClient, writer: InstrumentWriter
    ) -> None:
        """环序缺陷：别家开放区间排在自家重叠闭合区间之后也必须拒。

        旧实现先命中自家行即返回 True，漏检后续冲突行。
        """
        self._seed_instruments(client, [1, 2])
        self._seed_mapping(client, 1, "2020-01-01", "2024-01-01")
        self._seed_mapping(client, 2, "2025-06-01", None)

        ok = writer.register_source_mapping(
            instrument_id=1,
            source="tushare",
            source_ticker="830001.BJ",
            effective_from="2021-06-01",
            observed_at="2026-10-25 00:00:00",
        )

        assert ok is False

    def test_true_idempotent_open_row_no_write(
        self, client: SQLiteClient, writer: InstrumentWriter
    ) -> None:
        """真幂等：自有开放行 from ≤ f → True 且零写入。"""
        self._seed_instruments(client, [1])
        self._seed_mapping(client, 1, "2020-01-01", None)

        ok = writer.register_source_mapping(
            instrument_id=1,
            source="tushare",
            source_ticker="830001.BJ",
            effective_from="2021-01-01",
            observed_at="2026-10-25 00:00:00",
        )

        assert ok is True
        assert self._mapping_rows(client) == [(1, "2020-01-01", None)]

    def test_adjacent_handoff_to_other_instrument_allowed(
        self, client: SQLiteClient, writer: InstrumentWriter
    ) -> None:
        """端点相接切换：别家闭合 [2020,2024)，注册 f=2024-01-01 → 合法。

        effective_to 排他端，无双覆盖日；这是代码切换的标准形状。
        """
        self._seed_instruments(client, [1, 2])
        self._seed_mapping(client, 1, "2020-01-01", "2024-01-01")

        ok = writer.register_source_mapping(
            instrument_id=2,
            source="tushare",
            source_ticker="830001.BJ",
            effective_from="2024-01-01",
            observed_at="2026-10-25 00:00:00",
        )

        assert ok is True
        assert self._mapping_rows(client) == [
            (1, "2020-01-01", "2024-01-01"),
            (2, "2024-01-01", None),
        ]

    def test_open_conflict_rejected(
        self, client: SQLiteClient, writer: InstrumentWriter
    ) -> None:
        """别家开放区间在场 → 任何更晚起点注册拒绝。"""
        self._seed_instruments(client, [1, 2])
        self._seed_mapping(client, 2, "2020-01-01", None)

        ok = writer.register_source_mapping(
            instrument_id=1,
            source="tushare",
            source_ticker="830001.BJ",
            effective_from="2024-01-01",
            observed_at="2026-10-25 00:00:00",
        )

        assert ok is False
        assert self._mapping_rows(client) == [(2, "2020-01-01", None)]

    def test_closed_interval_interior_conflict_rejected(
        self, client: SQLiteClient, writer: InstrumentWriter
    ) -> None:
        """别家闭合区间内部起点（含端点前一日）注册拒绝。"""
        self._seed_instruments(client, [1, 2])
        self._seed_mapping(client, 2, "2020-01-01", "2024-01-01")

        for effective_from in ("2022-06-01", "2023-12-31"):
            ok = writer.register_source_mapping(
                instrument_id=1,
                source="tushare",
                source_ticker="830001.BJ",
                effective_from=effective_from,
                observed_at="2026-10-25 00:00:00",
            )
            assert ok is False, effective_from

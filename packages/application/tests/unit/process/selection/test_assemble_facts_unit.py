"""Fake-based unit tests for server-side selection fact assembly."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.selection.assemble_facts import (
    AssembleSelectionFacts,
    AssembleSelectionFactsRequest,
    CertifiedSnapshotWindow,
)
from ditto_application.processes.selection.facade import (
    SelectionFactorWeightDraft,
)
from ditto_application.queries.historical_universe import (
    HistoricalUniverseResult,
    HistoricalUniverseSources,
)
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.spec import FactorSpec

_AS_OF = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)  # 18:00 Asia/Shanghai
_CROSS = date(2026, 9, 29)
_BAR_DATES = tuple(date(2026, 8, 31) + timedelta(days=i) for i in range(30))

_DAILY_WINDOW = CertifiedSnapshotWindow(
    "snapshot:tushare:stock_daily:sha256:d1", date(2026, 8, 1), _CROSS
)
_STATUS_WINDOW = CertifiedSnapshotWindow(
    "snapshot:tushare:stock_status:sha256:s1", date(2026, 9, 1), _CROSS
)
_BASIC_WINDOW = CertifiedSnapshotWindow(
    "snapshot:tushare:stock_basic:sha256:b1", date(2015, 1, 1), date(2026, 9, 30)
)


class _FakeProvider:
    def __init__(
        self, frame: pl.DataFrame, raw_frame: pl.DataFrame | None = None
    ) -> None:
        self.frame = frame
        self.raw_frame = raw_frame
        self.queries: list[object] = []

    def get_bars(self, query):
        self.queries.append(query)
        if query.adj == "none":
            return self.raw_frame if self.raw_frame is not None else self.frame
        return self.frame

    def get_instruments(self, query):
        return pl.DataFrame()

    def get_schedule(self, start, end):
        return pl.DataFrame()

    def get_factor(self, name, instruments, start, end, asof=None):
        return pl.DataFrame()


class _FakeHistory:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.result = HistoricalUniverseResult(
            frame,
            {
                "sources": {"universe_id": "a-share-main"},
                "as_of": _CROSS.isoformat(),
            },
        )
        self.calls: list[dict[str, object]] = []

    def resolve(self, sources, *, as_of, knowledge_cutoff, publication_cutoff):
        self.calls.append(
            {
                "sources": sources,
                "as_of": as_of,
                "knowledge_cutoff": knowledge_cutoff,
                "publication_cutoff": publication_cutoff,
            }
        )
        return self.result


class _FakeIdentities:
    def __init__(self, names: dict[int, str], tickers: dict[int, str]) -> None:
        self._names = names
        self._tickers = tickers

    def names(self, instrument_ids, *, asof):
        return {key: self._names[key] for key in instrument_ids}

    def source_tickers(self, instrument_ids, *, asof, cutoff):
        self.ticker_cutoffs = [*getattr(self, "ticker_cutoffs", []), (asof, cutoff)]
        return {
            key: self._tickers[key] for key in instrument_ids if key in self._tickers
        }


_ADJ_WINDOW = CertifiedSnapshotWindow(
    "snapshot:tushare:adj_factor:sha256:a1", date(2026, 8, 1), _CROSS
)


class _FakeSnapshots:
    def __init__(
        self,
        daily=(_DAILY_WINDOW,),
        status=(_STATUS_WINDOW,),
        basic=(_BASIC_WINDOW,),
        adj=(_ADJ_WINDOW,),
    ):
        self._windows = {
            "stock_daily": daily,
            "stock_status": status,
            "stock_basic": basic,
            "adj_factor": adj,
        }

    def snapshot_ids(self, dataset_id):
        return tuple(window.snapshot_id for window in self._windows[dataset_id])

    def covering(self, *, dataset_id, day):
        return tuple(
            window
            for window in self._windows[dataset_id]
            if window.request_start <= day <= window.request_end
        )


def _registry(**extra: FactorSpec) -> dict[str, FactorSpec]:
    from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS

    return {
        key: ALL_FACTOR_SPECS[key]
        for key in ("reversal_1w", "volatility_factor", "volatility_20", "returns_1")
    } | dict(extra)


class _Registry:
    def __init__(self, specs: dict[str, FactorSpec]) -> None:
        self._specs = specs

    def get(self, factor_id: str) -> FactorSpec | None:
        return self._specs.get(factor_id)


def _bars_frame(
    *,
    rows_per_instrument: dict[int, int],
    snapshot_ids: dict[int, str] | None = None,
    close_overrides: dict[int, tuple[float, float]] | None = None,
    close_series: dict[int, list[float]] | None = None,
    future_row: tuple[int, float] | None = None,
) -> pl.DataFrame:
    snapshots = snapshot_ids or {}
    closes = close_overrides or {}
    series = close_series or {}
    records = []
    for instrument_id, count in rows_per_instrument.items():
        for index in range(count):
            trade_date = _BAR_DATES[len(_BAR_DATES) - count + index]
            close, pre_close = closes.get(instrument_id, (10.0, 10.0))
            if instrument_id in series:
                close = series[instrument_id][index]
                pre_close = close
            records.append(
                {
                    "instrument_id": instrument_id,
                    "trade_date": trade_date,
                    "knowledge_date": trade_date,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "pre_close": pre_close,
                    "volume": 1000.0,
                    "amount": 1000.0 * (index + 1),
                    "source": "tushare",
                    "source_ticker": f"{instrument_id:06d}.SZ",
                    "source_snapshot_id": snapshots.get(
                        instrument_id, _DAILY_WINDOW.snapshot_id
                    ),
                }
            )
    if future_row is not None:
        instrument_id, close = future_row
        trade_date = _CROSS + timedelta(days=1)
        records.append(
            {
                "instrument_id": instrument_id,
                "trade_date": trade_date,
                "knowledge_date": trade_date,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "pre_close": close,
                "volume": 1000.0,
                "amount": 9999.0,
                "source": "tushare",
                "source_ticker": f"{instrument_id:06d}.SZ",
                "source_snapshot_id": _DAILY_WINDOW.snapshot_id,
            }
        )
    return pl.DataFrame(records)


def _roster_frame(instrument_ids: tuple[int, ...]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": list(instrument_ids),
            "list_date": [date(2020, 1, 1)] * len(instrument_ids),
            "delist_date": [None] * len(instrument_ids),
            "is_suspended": [False] * len(instrument_ids),
            "exclusion_reasons": [[] for _ in instrument_ids],
            "investable": [True] * len(instrument_ids),
        },
        schema_overrides={
            "instrument_id": pl.Int64,
            "delist_date": pl.Date,
            "is_suspended": pl.Boolean,
            "exclusion_reasons": pl.List(pl.String),
            "investable": pl.Boolean,
        },
    )


def _process(
    *,
    provider: _FakeProvider,
    history: _FakeHistory,
    registry: dict[str, FactorSpec] | None = None,
    tickers: dict[int, str] | None = None,
    snapshots: _FakeSnapshots | None = None,
    clock: object | None = None,
) -> AssembleSelectionFacts:
    return AssembleSelectionFacts(
        provider=provider,
        history=history,  # type: ignore[arg-type]
        discover_sources=lambda **_kwargs: HistoricalUniverseSources(
            universe_id="unused",
            asset_kind="stock",
            master_snapshot_ids=(_BASIC_WINDOW.snapshot_id,),
            status_snapshot_ids=(_STATUS_WINDOW.snapshot_id,),
        ),
        identities=_FakeIdentities(
            names={1: "平安银行", 2: "ST步高", 3: "宁波银行"},
            tickers=tickers or {1: "000001.SZ", 2: "000002.SZ", 3: "000003.SZ"},
        ),  # type: ignore[arg-type]
        factors=_Registry(registry or _registry()),  # type: ignore[arg-type]
        snapshots=snapshots or _FakeSnapshots(),  # type: ignore[arg-type]
        clock=clock or (lambda: _AS_OF),  # type: ignore[arg-type]
    )


def _request(
    factors: tuple[str, ...] = ("reversal_1w",),
    **overrides: object,
) -> AssembleSelectionFactsRequest:
    values: dict[str, object] = {
        "universe_id": "a-share-main",
        "asset_kind": "stock",
        "as_of": _AS_OF,
        "spec_id": "stock-momentum-196b3",
        "spec_version": "1",
        "top_k": 5,
        "min_average_turnover": 1000.0,
        "min_listing_days": 60,
        "factor_weights": tuple(
            SelectionFactorWeightDraft(name, 1.0) for name in factors
        ),
    }
    values.update(overrides)
    return AssembleSelectionFactsRequest(**values)  # type: ignore[arg-type]


def _happy_process() -> tuple[AssembleSelectionFacts, _FakeProvider, _FakeHistory]:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30, 2: 10}))
    history = _FakeHistory(_roster_frame((1, 2)))
    return _process(provider=provider, history=history), provider, history


def test_assembles_policy_only_request_with_certified_lineage() -> None:
    process, provider, history = _happy_process()
    request = process.assemble(_request())

    assert request.universe_sources is not None
    assert request.universe_snapshot_id == history.result.snapshot_id
    assert request.industries == ()
    assert request.rotation_missing_inputs == ("industries",)
    assert request.membership_version == "catalog"
    # The claim covers every consumed row, starting at the window's first bar.
    assert request.data_from == _BAR_DATES[0]
    assert request.data_to == _CROSS
    assert request.rotation_source_snapshot_ids == (_DAILY_WINDOW.snapshot_id,)
    assert _STATUS_WINDOW.snapshot_id in request.selection_source_snapshot_ids
    assert _BASIC_WINDOW.snapshot_id in request.selection_source_snapshot_ids
    assert request.universe_sources.master_snapshot_ids == (_BASIC_WINDOW.snapshot_id,)
    consumed = {item.consumer_field for item in request.data_fields}
    assert "instruments.factor_values.reversal_1w" in consumed
    assert "instruments.average_turnover" in consumed
    assert "instruments.is_suspended" in consumed
    assert "membership_version" in consumed
    assert "universe_snapshot_id" in consumed
    daily_binding = next(
        item
        for item in request.data_fields
        if item.consumer_field == "instruments.factor_values.reversal_1w"
    )
    assert (daily_binding.dataset_id, daily_binding.field) == (
        "stock_daily",
        "close",
    )
    bindings = {
        (item.dataset_id, item.field, item.consumer_field)
        for item in request.data_fields
    }
    assert ("stock_daily", "pre_close", "instruments.limit_state") in bindings
    assert ("stock_basic", "name", "instruments.instrument_name") in bindings
    assert ("stock_basic", "list_date", "instruments.listing_days") in bindings
    assert (
        "adj_factor",
        "adj_factor",
        "instruments.factor_values.reversal_1w",
    ) in bindings
    assert [draft.instrument_id for draft in request.instruments] == [1, 2]
    assert provider.queries[0].instruments == ("000001.SZ", "000002.SZ")
    assert provider.queries[0].asof == _CROSS.isoformat()
    assert provider.queries[0].adj == "hfq"
    assert provider.queries[-1].adj == "none"
    assert provider.queries[-1].end == _CROSS.isoformat()


def test_factor_values_and_hard_filters_are_projected_per_instrument() -> None:
    process, _, _ = _happy_process()
    request = process.assemble(_request())
    first, second = request.instruments

    assert first.instrument_name == "平安银行"
    assert first.is_st is False
    assert second.instrument_name == "ST步高"
    assert second.is_st is True
    values = {item.name: item.value for item in first.factor_values}
    assert set(values) == {"reversal_1w"}
    assert 0.0 < values["reversal_1w"] <= 1.0
    # 30 rows ending at the cross-section: the 20-day amount mean is 20 500.
    assert first.average_turnover == 20500.0
    # Only 10 rows for the second instrument: no full turnover window.
    assert second.average_turnover is None
    assert first.is_suspended is False
    assert first.listing_days == (_CROSS - date(2020, 1, 1)).days
    assert first.limit_state == "normal"
    assert first.declared_missing_inputs == ()


def test_factor_values_are_cross_sectional_unit_ranks() -> None:
    provider = _FakeProvider(
        _bars_frame(
            rows_per_instrument={1: 30, 2: 30},
            # Rising closes: raw reversal (negated 5-day change) is negative.
            # Falling closes: raw reversal is positive and ranks higher.
            close_series={
                1: [10.0 * (1 + 0.01 * i) for i in range(30)],
                2: [20.0 * (1 - 0.005 * i) for i in range(30)],
            },
        )
    )
    history = _FakeHistory(_roster_frame((1, 2)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    scores = {
        draft.instrument_id: draft.factor_values[0].value
        for draft in request.instruments
    }
    assert scores == {1: 0.5, 2: 1.0}


def test_resolves_transitive_factor_dependencies() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30, 2: 30}))
    history = _FakeHistory(_roster_frame((1, 2)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request(factors=("volatility_factor",)))

    values = {item.name: item.value for item in request.instruments[0].factor_values}
    assert set(values) == {"volatility_factor"}
    # Constant closes yield zero volatility; the transitive chain still
    # produced a finite (not null/NaN) cross-section value.
    assert math.isfinite(values["volatility_factor"])
    factor_bindings = {
        (item.dataset_id, item.field)
        for item in request.data_fields
        if item.consumer_field == "instruments.factor_values.volatility_factor"
    }
    assert ("stock_daily", "close") in factor_bindings
    assert ("adj_factor", "adj_factor") in factor_bindings


def test_rejects_non_market_leaf_dependency() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(
        provider=provider,
        history=history,
        registry=_registry(
            value_pe=FactorSpec(
                id="value_pe", expression="-pe_ratio", dependencies=("pe_ratio",)
            )
        ),
    )
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(factors=("value_pe",)))
    assert error.value.details["reason"] == "ASSEMBLY_FACTOR_DEPENDENCY_UNSUPPORTED"
    assert error.value.details["dependency"] == "pe_ratio"


def test_rejects_dependency_cycle() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(
        provider=provider,
        history=history,
        registry=_registry(
            loop_a=FactorSpec(
                id="loop_a", expression="loop_b", dependencies=("loop_b",)
            ),
            loop_b=FactorSpec(
                id="loop_b", expression="loop_a", dependencies=("loop_a",)
            ),
        ),
    )
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(factors=("loop_a",)))
    assert error.value.details["reason"] == "ASSEMBLY_FACTOR_CYCLE"


def test_rejects_unknown_factor() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(provider=provider, history=history)
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(factors=("momentum_1m",)))
    assert error.value.details["reason"] == "ASSEMBLY_FACTOR_UNKNOWN"


def test_rejects_python_executor_factor() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(
        provider=provider,
        history=history,
        registry=_registry(
            custom=FactorSpec(
                id="custom",
                expression="",
                dependencies=(),
                computation_type="python",
            )
        ),
    )
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(factors=("custom",)))
    assert error.value.details["reason"] == "ASSEMBLY_FACTOR_EXECUTOR_UNAVAILABLE"


def test_rejects_bar_column_factor_id() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(
        provider=provider,
        history=history,
        registry=_registry(
            close=FactorSpec(
                id="close", expression="market.close", dependencies=("market.close",)
            )
        ),
    )
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(factors=("close",)))
    assert error.value.details["reason"] == "ASSEMBLY_FACTOR_COLUMN_CONFLICT"


@pytest.mark.pit
def test_rejects_backdated_cutoffs() -> None:
    process, _, _ = _happy_process()
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(knowledge_cutoff=_AS_OF - timedelta(hours=1)))
    assert error.value.details["reason"] == "ASSEMBLY_CUTOFF_BACKDATED"


def test_rejects_etf_and_naive_times() -> None:
    process, _, _ = _happy_process()
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(asset_kind="etf"))
    assert error.value.details["reason"] == "ASSEMBLY_ASSET_KIND_UNSUPPORTED"
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(as_of=datetime(2026, 9, 29, 8, 0)))
    assert error.value.details["reason"] == "ASSEMBLY_TIME_INVALID"


@pytest.mark.pit
def test_roster_member_without_bars_stays_declared_missing() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30, 2: 30}))
    history = _FakeHistory(_roster_frame((1, 2, 3)))
    process = _process(
        provider=provider, history=history, tickers={1: "000001.SZ", 2: "000002.SZ"}
    )
    request = process.assemble(_request())

    assert [draft.instrument_id for draft in request.instruments] == [1, 2, 3]
    absent = request.instruments[2]
    assert absent.declared_missing_inputs == ("bars",)
    assert absent.factor_values == ()
    assert absent.average_turnover is None
    assert absent.limit_state is None
    assert absent.listing_days == (_CROSS - date(2020, 1, 1)).days


@pytest.mark.pit
def test_unattributable_rows_are_declared_missing() -> None:
    provider = _FakeProvider(
        _bars_frame(
            rows_per_instrument={1: 30, 2: 30},
            snapshot_ids={2: None},  # type: ignore[dict-item]
        )
    )
    history = _FakeHistory(_roster_frame((1, 2)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    unattributable = request.instruments[1]
    assert unattributable.declared_missing_inputs == ("source_snapshot",)
    assert unattributable.factor_values == ()
    assert request.instruments[0].declared_missing_inputs == ()


@pytest.mark.pit
def test_limit_state_uses_st_aware_bands() -> None:
    provider = _FakeProvider(
        _bars_frame(
            rows_per_instrument={1: 30, 2: 30},
            close_overrides={1: (10.6, 10.0), 2: (10.6, 10.0)},
        )
    )
    history = _FakeHistory(_roster_frame((1, 2)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    assert request.instruments[0].limit_state == "normal"  # +6%, 9.5% band
    assert request.instruments[1].limit_state == "limit_up"  # +6%, ST 4.5% band


@pytest.mark.pit
def test_future_knowledge_rows_never_reach_the_cross_section() -> None:
    provider = _FakeProvider(
        _bars_frame(rows_per_instrument={1: 30}, future_row=(1, 99.0))
    )
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    assert request.data_to == _CROSS
    assert request.instruments[0].limit_state == "normal"
    values = {item.name: item.value for item in request.instruments[0].factor_values}
    # The 99.0 sentinel close never influenced the computed cross-section.
    assert values["reversal_1w"] == pytest.approx(1.0)


@pytest.mark.pit
def test_short_history_declares_missing_factor_value() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30, 2: 1}))
    history = _FakeHistory(_roster_frame((1, 2)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    assert request.instruments[1].declared_missing_inputs == ("factor:reversal_1w",)
    assert request.instruments[1].factor_values == ()
    # Ranks normalize by valid observations, so the surviving instrument
    # still reaches the top of the (0, 1] unit range.
    assert request.instruments[0].factor_values[0].value == pytest.approx(1.0)


@pytest.mark.pit
def test_explicit_past_knowledge_is_rejected_but_server_issuance_is_not() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(provider=provider, history=history)
    with pytest.raises(AppProcessError) as error:
        process.assemble(
            _request(
                as_of=_AS_OF - timedelta(days=1),
                knowledge_cutoff=_AS_OF - timedelta(days=1),
            )
        )
    assert error.value.details["reason"] == "ASSEMBLY_CUTOFF_BACKDATED"

    # Omitted cutoffs never exceed the decision instant, so a slightly
    # stale client as-of still assembles with honestly labeled knowledge.
    request = process.assemble(_request(as_of=_AS_OF - timedelta(minutes=1)))
    assert request.knowledge_cutoff == _AS_OF - timedelta(minutes=1)


def test_missing_knowledge_date_column_is_rejected() -> None:
    frame = _bars_frame(rows_per_instrument={1: 30}).drop("knowledge_date")
    provider = _FakeProvider(frame)
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(provider=provider, history=history)
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request())

    assert error.value.details["reason"] == "ASSEMBLY_BARS_SCHEMA"
    assert "knowledge_date" in error.value.details["columns"]


def test_uncovered_daily_window_is_rejected_before_response() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(
        provider=provider,
        history=history,
        snapshots=_FakeSnapshots(
            daily=(
                CertifiedSnapshotWindow(
                    "snapshot:tushare:stock_daily:sha256:d0",
                    date(2026, 8, 1),
                    date(2026, 8, 31),
                ),
            )
        ),
    )
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request())

    # Coverage of every consumed bar date (including the cross-section) is
    # the single fail-closed guard; the run never reaches response rendering.
    assert error.value.details["reason"] == "ASSEMBLY_SNAPSHOT_COVERAGE_MISSING"
    assert error.value.details["uncovered_count"] >= 19


def test_weight_invariants_mirror_the_strategy_spec() -> None:
    process, _, _ = _happy_process()
    with pytest.raises(AppProcessError) as error:
        process.assemble(
            _request(
                factors=("reversal_1w", "reversal_1w"),
                factor_weights=(
                    SelectionFactorWeightDraft("reversal_1w", 0.6),
                    SelectionFactorWeightDraft("reversal_1w", 0.4),
                ),
            )
        )
    assert error.value.details["reason"] == "ASSEMBLY_FACTOR_DUPLICATE"

    with pytest.raises(AppProcessError) as error:
        process.assemble(
            _request(factor_weights=(SelectionFactorWeightDraft("reversal_1w", 0.5),))
        )
    assert error.value.details["reason"] == "ASSEMBLY_FACTOR_WEIGHT_TOTAL"
    assert error.value.details["total"] == 0.5


def test_composed_factor_lookback_accumulates_windows() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(
        provider=provider,
        history=history,
        registry=_registry(
            composed=FactorSpec(
                id="composed",
                expression="ts_mean(slow, 20)",
                dependencies=("slow",),
            ),
            slow=FactorSpec(
                id="slow",
                expression="ts_mean(market.close, 20)",
                dependencies=("market.close",),
            ),
        ),
    )
    nodes = process._plan_factors(_request(factors=("composed",)))
    composed = next(node for node in nodes if node.factor_id == "composed")
    slow = next(node for node in nodes if node.factor_id == "slow")

    assert slow.lookback == 21  # ts_mean(20) consumes 21 rows
    # 21 composed rows over a dependency that itself needs 21 rows; the
    # additive guard errs one row on the safe side over the exact 41.
    assert composed.lookback == 42


@pytest.mark.pit
def test_knowledge_cutoff_before_publication_hides_same_day_bars() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(provider=provider, history=history)
    frozen = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)
    process = _process(provider=provider, history=history, clock=lambda: frozen)
    request = process.assemble(
        _request(as_of=frozen, knowledge_cutoff=frozen, publication_cutoff=frozen)
    )

    # 16:00 Asia/Shanghai is before the 18:00 bar publication claim, so the
    # cross-section falls back to the previous trade date.
    assert request.data_to == date(2026, 9, 28)


def test_invalid_excluded_limit_policy_is_rejected() -> None:
    process, _, _ = _happy_process()
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(excluded_limit_states=("normal", "limit_up")))
    assert error.value.details["reason"] == "ASSEMBLY_LIMIT_POLICY_INVALID"

    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(excluded_limit_states=("limit_up", "limit_up")))
    assert error.value.details["reason"] == "ASSEMBLY_LIMIT_POLICY_INVALID"


@pytest.mark.pit
def test_unattributable_lookback_row_declares_missing_source() -> None:
    frame = _bars_frame(rows_per_instrument={1: 30, 2: 30})
    # Null lineage on one historical row (not the cross-section row).
    frame = frame.with_columns(
        pl.when(
            (pl.col("instrument_id") == 2) & (pl.col("trade_date") == date(2026, 9, 20))
        )
        .then(None)
        .otherwise(pl.col("source_snapshot_id"))
        .alias("source_snapshot_id")
    )
    provider = _FakeProvider(frame)
    history = _FakeHistory(_roster_frame((1, 2)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    assert request.instruments[1].declared_missing_inputs == ("source_snapshot",)
    assert request.instruments[0].declared_missing_inputs == ()


@pytest.mark.pit
def test_non_finite_prices_leave_limit_state_missing() -> None:
    provider = _FakeProvider(
        _bars_frame(
            rows_per_instrument={1: 30},
            close_overrides={1: (float("nan"), 10.0)},
        )
    )
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    assert request.instruments[0].limit_state is None


def test_discovery_port_failures_propagate() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))

    def refuse(**_kwargs: object) -> HistoricalUniverseSources:
        raise AppProcessError(
            "universe membership is narrower than the certified roster lane",
            details={"reason": "ASSEMBLY_UNIVERSE_SCOPE_UNSUPPORTED"},
        )

    process = AssembleSelectionFacts(
        provider=provider,
        history=history,  # type: ignore[arg-type]
        discover_sources=refuse,  # type: ignore[arg-type]
        identities=_FakeIdentities(names={1: "平安银行"}, tickers={1: "000001.SZ"}),  # type: ignore[arg-type]
        factors=_Registry(_registry()),  # type: ignore[arg-type]
        snapshots=_FakeSnapshots(),  # type: ignore[arg-type]
        clock=lambda: _AS_OF,
    )
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request())

    assert error.value.details["reason"] == "ASSEMBLY_UNIVERSE_SCOPE_UNSUPPORTED"


def test_cross_sectional_nesting_of_time_series_is_rejected() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(
        provider=provider,
        history=history,
        registry=_registry(
            liquidity=ALL_FACTOR_SPECS["liquidity"],
        ),
    )
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(factors=("liquidity",)))

    assert error.value.details["reason"] == "ASSEMBLY_FACTOR_EXPRESSION_UNSUPPORTED"


def test_limit_band_uses_raw_prices_not_adjusted() -> None:
    raw = _bars_frame(
        rows_per_instrument={1: 30},
        close_overrides={1: (11.06, 10.0)},  # +10.6% raw move
    )
    hfq = _bars_frame(
        rows_per_instrument={1: 30},
        # Adjusted ratio must not influence the band judgement.
        close_overrides={1: (5.0, 10.0)},
    )
    provider = _FakeProvider(hfq, raw_frame=raw)
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    assert request.instruments[0].limit_state == "limit_up"


def test_non_finite_amounts_leave_turnover_missing() -> None:
    frame = _bars_frame(rows_per_instrument={1: 30}).with_columns(
        pl.when(pl.col("trade_date") == _CROSS)
        .then(float("nan"))
        .otherwise(pl.col("amount"))
        .alias("amount")
    )
    provider = _FakeProvider(frame)
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    assert request.instruments[0].average_turnover is None


def test_backdated_publication_cutoff_is_rejected() -> None:
    process, _, _ = _happy_process()
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(publication_cutoff=_AS_OF - timedelta(days=2)))
    assert error.value.details["reason"] == "ASSEMBLY_CUTOFF_BACKDATED"


def test_future_as_of_is_rejected() -> None:
    process, _, _ = _happy_process()
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request(as_of=_AS_OF + timedelta(hours=1)))
    assert error.value.details["reason"] == "ASSEMBLY_TIME_INVALID"


def test_price_factors_require_certified_adjustment_window() -> None:
    provider = _FakeProvider(_bars_frame(rows_per_instrument={1: 30}))
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(
        provider=provider, history=history, snapshots=_FakeSnapshots(adj=())
    )
    with pytest.raises(AppProcessError) as error:
        process.assemble(_request())
    assert error.value.details["reason"] == "ASSEMBLY_ADJUSTMENT_WINDOW_MISSING"


@pytest.mark.pit
def test_provider_identity_mismatch_rows_are_dropped() -> None:
    frame = _bars_frame(rows_per_instrument={1: 30}).with_columns(
        # The provider re-resolved this row to a foreign identity.
        pl.when(pl.col("trade_date") == _CROSS)
        .then(99)
        .otherwise(pl.col("instrument_id"))
        .alias("instrument_id")
    )
    provider = _FakeProvider(frame)
    history = _FakeHistory(_roster_frame((1,)))
    process = _process(provider=provider, history=history)
    request = process.assemble(_request())

    # The poisoned cross row is dropped, so the cross-section falls back to
    # the previous date; the foreign identity never produces facts.
    assert request.data_to == date(2026, 9, 28)
    assert [draft.instrument_id for draft in request.instruments] == [1]
    assert request.instruments[0].declared_missing_inputs == ()

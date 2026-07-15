# Dataset Registry Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a central `DatasetRegistry` for application ingestion so dataset fetch, write, and instrument-support routing are declared once and reused by `fetch_handlers.py`, `data_writer.py`, and `coordinator_constants.py`.

**Architecture:** Keep the registry in `ditto_application.processes.ingestion` because the current pain is application-level routing, not data package ownership. `ditto_data.models.Dataset` remains the stable dataset identifier; the new registry owns operational routing metadata and handler factories. The change is behavior-preserving except one deliberate correction: `Dataset.STOCK_STATUS` is removed from instrument-level support because the current fetcher protocol has no instrument-level stock-status method.

**Tech Stack:** Python 3.13, dataclasses, `enum.StrEnum`, `polars`, pytest, pixi, ruff, basedpyright, import-linter.

---

## Scope Check

The architecture evaluation report covers six independent remediation batches. This plan implements only Batch 1, `DataCatalog / DatasetRegistry`, because it produces working, testable software on its own and is the recommended first attack surface.

Separate follow-up plans should be written for:

- Paper Runtime + BrokerGateway
- Application Composition Boundary
- Execution/Risk/Portfolio Runtime Spine
- Large-file and naming consistency cleanup
- Product architecture gap closing

## File Structure

Create:

- `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`
  Owns `DatasetRegistry`, immutable `DatasetRegistration`, fetch contexts, `WriteKind`, and the default registry.

- `packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py`
  Tests registry invariants, route metadata, duplicate protection, and handler conformance.

- `packages/application/tests/unit/process/ingestion/test_fetch_handlers_registry_unit.py`
  Tests that `fetch_handlers.py` delegates to the registry without hardcoded dataset maps.

Modify:

- `packages/application/src/ditto_application/processes/ingestion/fetch_handlers.py`
  Replace hardcoded `Dataset -> lambda` maps with registry-generated maps.

- `packages/application/src/ditto_application/processes/ingestion/data_writer.py`
  Replace `_build_dataset_handlers()` hardcoded writer map with registry `WriteKind` dispatch.

- `packages/application/src/ditto_application/processes/ingestion/coordinator_constants.py`
  Derive `SUPPORTED_INSTRUMENT_DATASETS` from the registry.

- `packages/application/src/ditto_application/processes/ingestion/instrument_ingestion.py`
  Keep current call shape but rely on registry-derived support set and registry-backed fetch handlers.

- `packages/application/tests/unit/process/test_coordinator_constants_unit.py`
  Update expected type and remove `Dataset.STOCK_STATUS` from instrument-level expected datasets.

- `packages/application/tests/unit/process/ingestion/test_data_writer_unit.py`
  Add writer-routing assertions that prove registry metadata selects the correct writer path.

Do not modify:

- `packages/data/src/ditto_data/models/common.py`
  `Dataset` stays as a stable identifier in this batch.

- `.importlinter`
  Current boundaries already allow this application-internal refactor.

---

## Task 1: Add Registry Core Types

**Files:**
- Create: `packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py`
- Create: `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`

- [ ] **Step 1: Write the failing registry core tests**

Create `packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py` with this initial content:

```python
"""Dataset registry unit tests."""

from __future__ import annotations

import pytest
from ditto_application.processes.ingestion.dataset_registry import (
    DatasetRegistration,
    DatasetRegistry,
    WriteKind,
)
from ditto_data.models import Dataset


@pytest.mark.unit
class TestDatasetRegistryCore:
    """Registry container behavior."""

    def test_register_and_require_registration(self) -> None:
        registry = DatasetRegistry()
        registration = DatasetRegistration(
            dataset=Dataset.STOCK_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="stock_daily",
        )

        registry.register(registration)

        assert registry.require(Dataset.STOCK_DAILY) is registration
        assert list(registry.datasets()) == [Dataset.STOCK_DAILY]

    def test_duplicate_registration_raises_value_error(self) -> None:
        registry = DatasetRegistry()
        registration = DatasetRegistration(
            dataset=Dataset.STOCK_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="stock_daily",
        )

        registry.register(registration)

        with pytest.raises(ValueError, match="Dataset already registered: stock_daily"):
            registry.register(registration)

    def test_requires_registered_dataset(self) -> None:
        registry = DatasetRegistry()

        with pytest.raises(KeyError, match="Dataset is not registered: stock_daily"):
            registry.require(Dataset.STOCK_DAILY)

    def test_requires_write_dataset_for_bars(self) -> None:
        with pytest.raises(ValueError, match="write_dataset is required"):
            DatasetRegistration(
                dataset=Dataset.STOCK_DAILY,
                write_kind=WriteKind.TRADED_BARS,
            )

    def test_basic_registration_requires_asset_class(self) -> None:
        with pytest.raises(ValueError, match="basic_asset_class is required"):
            DatasetRegistration(
                dataset=Dataset.STOCK_BASIC,
                write_kind=WriteKind.BASIC,
            )
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ditto_application.processes.ingestion.dataset_registry'`.

- [ ] **Step 3: Implement the registry core**

Create `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py` with this content:

```python
"""Dataset registry for application ingestion routing."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

import polars as pl
from ditto_data.models import Dataset
from ditto_kernel.instrument import InstrumentIngestParams

from ditto_application.processes.ingestion.types import SourceFetchers

__all__ = [
    "DailyFetchContext",
    "DailyFetchFactory",
    "DailyFetchHandler",
    "DatasetRegistration",
    "DatasetRegistry",
    "InstrumentFetchContext",
    "InstrumentFetchFactory",
    "InstrumentFetchHandler",
    "WriteKind",
]

DailyFetchHandler = Callable[[], pl.DataFrame]
DailyFetchFactory = Callable[["DailyFetchContext"], DailyFetchHandler]
InstrumentFetchHandler = Callable[[], pl.DataFrame]
InstrumentFetchFactory = Callable[["InstrumentFetchContext"], InstrumentFetchHandler]


@dataclass(frozen=True)
class DailyFetchContext:
    """Runtime inputs for date-level fetch handlers."""

    fetchers: SourceFetchers
    trade_date: str
    fetch_commodity_daily: Callable[[str], pl.DataFrame]
    get_cached_index_codes: Callable[[], list[str]]


@dataclass(frozen=True)
class InstrumentFetchContext:
    """Runtime inputs for instrument-level fetch handlers."""

    fetchers: SourceFetchers
    source_ticker: str
    params: InstrumentIngestParams


class WriteKind(StrEnum):
    """Supported ingestion writer routes."""

    UNSUPPORTED = "unsupported"
    TRADED_BARS = "traded_bars"
    INSTRUMENT_CODE_BARS = "instrument_code_bars"
    STOCK_STATUS = "stock_status"
    ADJ_FACTOR = "adj_factor"
    FUNDAMENTAL = "fundamental"
    CAPITAL = "capital"
    MACRO = "macro"
    CALENDAR = "calendar"
    BASIC = "basic"


@dataclass(frozen=True)
class DatasetRegistration:
    """Operational route metadata for one Dataset value."""

    dataset: Dataset
    write_kind: WriteKind
    write_dataset: str | None = None
    daily_fetch_factory: DailyFetchFactory | None = None
    instrument_fetch_factory: InstrumentFetchFactory | None = None
    metadata_dataset: bool = False
    basic_asset_class: Literal["stock", "etf", "index"] | None = None

    def __post_init__(self) -> None:
        """Validate registration consistency."""
        if self.write_kind in {
            WriteKind.TRADED_BARS,
            WriteKind.INSTRUMENT_CODE_BARS,
        } and self.write_dataset is None:
            raise ValueError(
                f"write_dataset is required for {self.write_kind.value}"
            )
        if self.write_kind == WriteKind.BASIC and self.basic_asset_class is None:
            raise ValueError("basic_asset_class is required for basic datasets")

    @property
    def supports_instrument_ingestion(self) -> bool:
        """Return whether this dataset has an instrument-level fetch route."""
        return self.instrument_fetch_factory is not None

    @property
    def requires_year_partition(self) -> bool:
        """Return whether write routing needs a year from trade_date."""
        return not self.metadata_dataset


class DatasetRegistry:
    """Mutable registry used to declare ingestion routing once."""

    def __init__(
        self,
        registrations: tuple[DatasetRegistration, ...] = (),
    ) -> None:
        self._registrations: dict[Dataset, DatasetRegistration] = {}
        for registration in registrations:
            self.register(registration)

    def register(self, registration: DatasetRegistration) -> None:
        """Register one dataset route."""
        if registration.dataset in self._registrations:
            raise ValueError(
                f"Dataset already registered: {registration.dataset.value}"
            )
        self._registrations[registration.dataset] = registration

    def require(self, dataset: Dataset) -> DatasetRegistration:
        """Return a registration or raise a clear error."""
        try:
            return self._registrations[dataset]
        except KeyError:
            raise KeyError(f"Dataset is not registered: {dataset.value}") from None

    def datasets(self) -> Iterator[Dataset]:
        """Yield registered dataset IDs in insertion order."""
        return iter(self._registrations)

    def registrations(self) -> tuple[DatasetRegistration, ...]:
        """Return all registrations in insertion order."""
        return tuple(self._registrations.values())

    def supported_instrument_datasets(self) -> frozenset[Dataset]:
        """Return datasets with instrument-level fetch routes."""
        return frozenset(
            registration.dataset
            for registration in self._registrations.values()
            if registration.supports_instrument_ingestion
        )
```

- [ ] **Step 4: Run the registry core tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add \
  packages/application/src/ditto_application/processes/ingestion/dataset_registry.py \
  packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py
git commit -m "feat(ingestion): add dataset registry core"
```

---

## Task 2: Add Default Dataset Routes

**Files:**
- Modify: `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`
- Modify: `packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py`

- [ ] **Step 1: Add failing tests for the default registry**

In the existing import block in `packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py`, add `default_dataset_registry` to the `ditto_application.processes.ingestion.dataset_registry` import:

```python
from ditto_application.processes.ingestion.dataset_registry import (
    DatasetRegistration,
    DatasetRegistry,
    WriteKind,
    default_dataset_registry,
)
```

Then append this code to the same file:

```python
@pytest.mark.unit
class TestDefaultDatasetRegistry:
    """Default route coverage."""

    def test_registers_every_dataset_enum_value(self) -> None:
        registry = default_dataset_registry()

        assert set(registry.datasets()) == set(Dataset)

    def test_stock_daily_route_declares_fetch_and_write_metadata(self) -> None:
        registration = default_dataset_registry().require(Dataset.STOCK_DAILY)

        assert registration.write_kind is WriteKind.TRADED_BARS
        assert registration.write_dataset == "stock_daily"
        assert registration.daily_fetch_factory is not None
        assert registration.instrument_fetch_factory is not None
        assert registration.supports_instrument_ingestion is True
        assert registration.requires_year_partition is True

    def test_calendar_route_is_metadata_without_year_partition(self) -> None:
        registration = default_dataset_registry().require(Dataset.CALENDAR)

        assert registration.write_kind is WriteKind.CALENDAR
        assert registration.metadata_dataset is True
        assert registration.requires_year_partition is False

    def test_stock_basic_route_declares_basic_asset_class(self) -> None:
        registration = default_dataset_registry().require(Dataset.STOCK_BASIC)

        assert registration.write_kind is WriteKind.BASIC
        assert registration.basic_asset_class == "stock"
        assert registration.metadata_dataset is True

    def test_stock_status_is_not_instrument_supported_without_protocol_method(
        self,
    ) -> None:
        registration = default_dataset_registry().require(Dataset.STOCK_STATUS)

        assert registration.daily_fetch_factory is not None
        assert registration.instrument_fetch_factory is None
        assert registration.supports_instrument_ingestion is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py -q
```

Expected: FAIL with `ImportError: cannot import name 'default_dataset_registry'`.

- [ ] **Step 3: Add default route builders**

In `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`, update `__all__` to include:

```python
    "default_dataset_registry",
```

Then append this code to the same file:

```python
def _date_range_from_trade_date(trade_date: str) -> tuple[str, str]:
    year = trade_date[:4]
    return f"{year}-01-01", f"{year}-12-31"


def _by_instrument(
    method: Callable[..., pl.DataFrame],
    ctx: InstrumentFetchContext,
) -> pl.DataFrame:
    return method(
        source_ticker=ctx.source_ticker,
        start_date=ctx.params.start_date,
        end_date=ctx.params.end_date,
    )


def default_dataset_registry() -> DatasetRegistry:
    """Build the default application ingestion registry."""
    registry = DatasetRegistry()

    registry.register(
        DatasetRegistration(
            dataset=Dataset.CALENDAR,
            write_kind=WriteKind.CALENDAR,
            metadata_dataset=True,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.metadata.fetch_calendar(
                *_date_range_from_trade_date(ctx.trade_date)
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.STOCK_BASIC,
            write_kind=WriteKind.BASIC,
            basic_asset_class="stock",
            metadata_dataset=True,
            daily_fetch_factory=lambda ctx: ctx.fetchers.metadata.fetch_stock_basic,
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.ETF_BASIC,
            write_kind=WriteKind.BASIC,
            basic_asset_class="etf",
            metadata_dataset=True,
            daily_fetch_factory=lambda ctx: ctx.fetchers.metadata.fetch_etf_basic,
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.INDEX_BASIC,
            write_kind=WriteKind.BASIC,
            basic_asset_class="index",
            metadata_dataset=True,
            daily_fetch_factory=lambda ctx: ctx.fetchers.metadata.fetch_index_basic,
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.STOCK_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="stock_daily",
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.market.fetch_stock_daily(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.market.fetch_stock_daily, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.ETF_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="etf_daily",
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.market.fetch_etf_daily(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.market.fetch_etf_daily, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.INDEX_DAILY,
            write_kind=WriteKind.TRADED_BARS,
            write_dataset="index_daily",
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.market.fetch_index_daily(
                ctx.trade_date,
                ts_codes=ctx.get_cached_index_codes(),
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.market.fetch_index_daily, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.STOCK_STATUS,
            write_kind=WriteKind.STOCK_STATUS,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.market.fetch_stock_status(
                ctx.trade_date
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.ADJ_FACTOR,
            write_kind=WriteKind.ADJ_FACTOR,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.market.fetch_adj_factor(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: ctx.fetchers.market.fetch_adj_factor_by_ticker(
                ts_code=ctx.source_ticker,
                start_date=ctx.params.start_date.replace("-", ""),
                end_date=ctx.params.end_date.replace("-", ""),
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.FUND_ADJ,
            write_kind=WriteKind.ADJ_FACTOR,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.market.fetch_fund_adj(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.market.fetch_fund_adj, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.BALANCE_SHEET,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.fundamental.fetch_balance_sheet(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.fundamental.fetch_balance_sheet, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.INCOME_STATEMENT,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.fundamental.fetch_income_statement(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.fundamental.fetch_income_statement, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.CASH_FLOW,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.fundamental.fetch_cash_flow(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.fundamental.fetch_cash_flow, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.DIVIDEND,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.fundamental.fetch_dividend(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.fundamental.fetch_dividend, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.CORPORATE_ACTIONS,
            write_kind=WriteKind.FUNDAMENTAL,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.fundamental.fetch_corporate_actions(
                ctx.trade_date
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.VALUATION_METRICS,
            write_kind=WriteKind.CAPITAL,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.capital.fetch_valuation_metrics(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.capital.fetch_valuation_metrics, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.MARGIN_TRADING,
            write_kind=WriteKind.CAPITAL,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.capital.fetch_margin_trading(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.capital.fetch_margin_trading, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.PLEDGE_RATIO,
            write_kind=WriteKind.CAPITAL,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.capital.fetch_pledge_ratio(
                ctx.trade_date
            ),
            instrument_fetch_factory=lambda ctx: lambda: _by_instrument(
                ctx.fetchers.capital.fetch_pledge_ratio, ctx
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.MACRO_INDICATORS,
            write_kind=WriteKind.MACRO,
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.macro.fetch_macro_indicators(
                ctx.trade_date
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.FX_DAILY,
            write_kind=WriteKind.INSTRUMENT_CODE_BARS,
            write_dataset="fx_daily",
            daily_fetch_factory=lambda ctx: lambda: ctx.fetchers.macro.fetch_fx_daily(
                ts_codes=["USD/CNY", "EUR/CNY", "JPY/CNY"],
                start_date=ctx.trade_date,
                end_date=ctx.trade_date,
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.COMMODITY_DAILY,
            write_kind=WriteKind.INSTRUMENT_CODE_BARS,
            write_dataset="commodity_daily",
            daily_fetch_factory=lambda ctx: lambda: ctx.fetch_commodity_daily(
                ctx.trade_date
            ),
        )
    )
    registry.register(
        DatasetRegistration(
            dataset=Dataset.INDEX_WEIGHT,
            write_kind=WriteKind.UNSUPPORTED,
        )
    )
    return registry
```

- [ ] **Step 4: Correct FX route to use the existing FX code mapping**

Add this import near the top of `dataset_registry.py`:

```python
from ditto_data.models import FX_CODE_TO_INSTRUMENT_ID, Dataset
```

Replace the `ts_codes=[...]` argument in the `Dataset.FX_DAILY` registration with:

```python
                ts_codes=list(FX_CODE_TO_INSTRUMENT_ID.keys()),
```

- [ ] **Step 5: Run the registry tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add \
  packages/application/src/ditto_application/processes/ingestion/dataset_registry.py \
  packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py
git commit -m "feat(ingestion): declare default dataset routes"
```

---

## Task 3: Derive Instrument Support From Registry

**Files:**
- Modify: `packages/application/src/ditto_application/processes/ingestion/coordinator_constants.py`
- Modify: `packages/application/tests/unit/process/test_coordinator_constants_unit.py`

- [ ] **Step 1: Update failing tests for registry-derived support**

In `packages/application/tests/unit/process/test_coordinator_constants_unit.py`, replace `test_is_frozen_set` with:

```python
    def test_is_frozen_set(self) -> None:
        """SUPPORTED_INSTRUMENT_DATASETS is immutable."""
        assert isinstance(SUPPORTED_INSTRUMENT_DATASETS, frozenset)
```

Then replace `test_contains_expected_datasets` with:

```python
    def test_contains_expected_datasets(self) -> None:
        """Contains datasets that have instrument-level fetch routes."""
        expected = {
            Dataset.STOCK_DAILY,
            Dataset.ETF_DAILY,
            Dataset.INDEX_DAILY,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.VALUATION_METRICS,
            Dataset.BALANCE_SHEET,
            Dataset.INCOME_STATEMENT,
            Dataset.CASH_FLOW,
            Dataset.DIVIDEND,
            Dataset.MARGIN_TRADING,
            Dataset.PLEDGE_RATIO,
        }
        assert SUPPORTED_INSTRUMENT_DATASETS == expected
```

Add this test to the same class:

```python
    def test_stock_status_is_not_instrument_supported(self) -> None:
        """Stock status is date-level only with the current MarketFetcher API."""
        assert Dataset.STOCK_STATUS not in SUPPORTED_INSTRUMENT_DATASETS
```

- [ ] **Step 2: Run constants tests to verify they fail**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/test_coordinator_constants_unit.py::TestSupportedInstrumentDatasets -q
```

Expected: FAIL because `SUPPORTED_INSTRUMENT_DATASETS` is still a mutable set and still includes `Dataset.STOCK_STATUS`.

- [ ] **Step 3: Replace the hardcoded support set**

In `packages/application/src/ditto_application/processes/ingestion/coordinator_constants.py`, replace the `Dataset` import and `SUPPORTED_INSTRUMENT_DATASETS` block with:

```python
from ditto_data.models import Dataset

from ditto_application.processes.ingestion.dataset_registry import (
    default_dataset_registry,
)

# 支持按标的摄取的数据集，由 DatasetRegistry 中的 instrument_fetch_factory 决定。
SUPPORTED_INSTRUMENT_DATASETS: frozenset[Dataset] = (
    default_dataset_registry().supported_instrument_datasets()
)
```

Remove the old hardcoded set literal.

- [ ] **Step 4: Run constants tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/test_coordinator_constants_unit.py::TestSupportedInstrumentDatasets -q
```

Expected: PASS.

- [ ] **Step 5: Run instrument ingestion tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_coordinator_instrument_unit.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add \
  packages/application/src/ditto_application/processes/ingestion/coordinator_constants.py \
  packages/application/tests/unit/process/test_coordinator_constants_unit.py
git commit -m "fix(ingestion): derive instrument dataset support from registry"
```

---

## Task 4: Refactor Fetch Handlers To Use Registry

**Files:**
- Create: `packages/application/tests/unit/process/ingestion/test_fetch_handlers_registry_unit.py`
- Modify: `packages/application/src/ditto_application/processes/ingestion/fetch_handlers.py`

- [ ] **Step 1: Write failing fetch-handler delegation tests**

Create `packages/application/tests/unit/process/ingestion/test_fetch_handlers_registry_unit.py`:

```python
"""Tests for registry-backed ingestion fetch handlers."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.processes.ingestion.fetch_handlers import (
    build_daily_fetch_handlers,
    build_instrument_fetch_handlers,
)
from ditto_application.processes.ingestion.types import SourceFetchers
from ditto_data.models import Dataset
from ditto_kernel.instrument import InstrumentIngestParams


@pytest.fixture
def fetchers() -> SourceFetchers:
    metadata = MagicMock()
    market = MagicMock()
    fundamental = MagicMock()
    capital = MagicMock()
    macro = MagicMock()
    metadata.fetch_calendar.return_value = pl.DataFrame({"dataset": ["calendar"]})
    market.fetch_stock_daily.return_value = pl.DataFrame({"dataset": ["stock_daily"]})
    market.fetch_adj_factor_by_ticker.return_value = pl.DataFrame(
        {"dataset": ["adj_factor"]}
    )
    return SourceFetchers(
        metadata=metadata,
        market=market,
        fundamental=fundamental,
        capital=capital,
        macro=macro,
    )


@pytest.mark.unit
def test_daily_handlers_are_built_from_registry(fetchers: SourceFetchers) -> None:
    handlers = build_daily_fetch_handlers(
        fetchers,
        "2024-05-20",
        fetch_commodity_daily=lambda trade_date: pl.DataFrame(
            {"trade_date": [trade_date]}
        ),
        get_cached_index_codes=lambda: ["000300.SH"],
    )

    result = handlers[Dataset.CALENDAR]()

    assert result.to_dict(as_series=False) == {"dataset": ["calendar"]}
    fetchers.metadata.fetch_calendar.assert_called_once_with(
        "2024-01-01",
        "2024-12-31",
    )


@pytest.mark.unit
def test_instrument_handlers_are_built_from_registry(fetchers: SourceFetchers) -> None:
    params = InstrumentIngestParams(
        ticker="000001",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    handlers = build_instrument_fetch_handlers(
        fetchers,
        "000001.SZ",
        params,
    )
    result = handlers[Dataset.STOCK_DAILY]()

    assert result.to_dict(as_series=False) == {"dataset": ["stock_daily"]}
    fetchers.market.fetch_stock_daily.assert_called_once_with(
        source_ticker="000001.SZ",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )


@pytest.mark.unit
def test_stock_status_has_no_instrument_handler(fetchers: SourceFetchers) -> None:
    params = InstrumentIngestParams(
        ticker="000001",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    handlers = build_instrument_fetch_handlers(fetchers, "000001.SZ", params)

    assert Dataset.STOCK_STATUS not in handlers
```

- [ ] **Step 2: Run the new fetch-handler tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_fetch_handlers_registry_unit.py -q
```

Expected: FAIL on `test_stock_status_has_no_instrument_handler` until `coordinator_constants.py` and registry-backed fetch handlers are both in place.

- [ ] **Step 3: Add handler map helpers to the registry**

Append these methods inside the `DatasetRegistry` class in `dataset_registry.py`:

```python
    def daily_fetch_handlers(
        self,
        ctx: DailyFetchContext,
    ) -> dict[Dataset, DailyFetchHandler]:
        """Build date-level fetch handlers from registrations."""
        handlers: dict[Dataset, DailyFetchHandler] = {}
        for registration in self._registrations.values():
            if registration.daily_fetch_factory is not None:
                handlers[registration.dataset] = registration.daily_fetch_factory(ctx)
        return handlers

    def instrument_fetch_handlers(
        self,
        ctx: InstrumentFetchContext,
    ) -> dict[Dataset, InstrumentFetchHandler]:
        """Build instrument-level fetch handlers from registrations."""
        handlers: dict[Dataset, InstrumentFetchHandler] = {}
        for registration in self._registrations.values():
            if registration.instrument_fetch_factory is not None:
                handlers[registration.dataset] = registration.instrument_fetch_factory(
                    ctx
                )
        return handlers
```

- [ ] **Step 4: Replace fetch handler internals**

Replace the content of `packages/application/src/ditto_application/processes/ingestion/fetch_handlers.py` with:

```python
"""Dataset fetch handler builders backed by DatasetRegistry."""

from __future__ import annotations

from collections.abc import Callable

import polars as pl
from ditto_data.models import Dataset
from ditto_kernel.instrument import InstrumentIngestParams

from ditto_application.processes.ingestion.dataset_registry import (
    DailyFetchContext,
    DatasetRegistry,
    InstrumentFetchContext,
    default_dataset_registry,
)
from ditto_application.processes.ingestion.types import SourceFetchers

__all__ = [
    "build_daily_fetch_handlers",
    "build_instrument_fetch_handlers",
]


def build_daily_fetch_handlers(
    fetchers: SourceFetchers,
    trade_date: str,
    *,
    fetch_commodity_daily: Callable[[str], pl.DataFrame],
    get_cached_index_codes: Callable[[], list[str]],
    registry: DatasetRegistry | None = None,
) -> dict[Dataset, Callable[[], pl.DataFrame]]:
    """Build date-level fetch handlers from the dataset registry."""
    active_registry = registry or default_dataset_registry()
    return active_registry.daily_fetch_handlers(
        DailyFetchContext(
            fetchers=fetchers,
            trade_date=trade_date,
            fetch_commodity_daily=fetch_commodity_daily,
            get_cached_index_codes=get_cached_index_codes,
        )
    )


def build_instrument_fetch_handlers(
    fetchers: SourceFetchers,
    source_ticker: str,
    params: InstrumentIngestParams,
    registry: DatasetRegistry | None = None,
) -> dict[Dataset, Callable[[], pl.DataFrame]]:
    """Build instrument-level fetch handlers from the dataset registry."""
    active_registry = registry or default_dataset_registry()
    return active_registry.instrument_fetch_handlers(
        InstrumentFetchContext(
            fetchers=fetchers,
            source_ticker=source_ticker,
            params=params,
        )
    )
```

- [ ] **Step 5: Run fetch-handler tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_fetch_handlers_registry_unit.py -q
```

Expected: PASS.

- [ ] **Step 6: Run coordinator fetch tests**

Run:

```bash
pixi run -e dev pytest \
  packages/application/tests/unit/process/ingestion/test_coordinator_unit.py \
  packages/application/tests/unit/process/ingestion/test_coordinator_instrument_unit.py \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add \
  packages/application/src/ditto_application/processes/ingestion/dataset_registry.py \
  packages/application/src/ditto_application/processes/ingestion/fetch_handlers.py \
  packages/application/tests/unit/process/ingestion/test_fetch_handlers_registry_unit.py
git commit -m "refactor(ingestion): build fetch handlers from dataset registry"
```

---

## Task 5: Refactor Data Writer Routing To Use Registry

**Files:**
- Modify: `packages/application/src/ditto_application/processes/ingestion/data_writer.py`
- Modify: `packages/application/tests/unit/process/ingestion/test_data_writer_unit.py`

- [ ] **Step 1: Add failing tests for registry-based writer routing**

Append this class to `packages/application/tests/unit/process/ingestion/test_data_writer_unit.py`:

```python
@pytest.mark.unit
class TestRegistryBackedWriteRouting:
    """Writer dispatch uses registry route metadata."""

    def test_stock_daily_uses_registered_bars_dataset(
        self,
        data_writer,
        mock_metadata_service,
        mock_market_write_service,
    ) -> None:
        mock_metadata_service.resolve_instrument_ids_batch.return_value = {
            "000001.SZ": 1_000_001
        }
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [10.5],
                "low": [9.8],
                "close": [10.2],
                "volume": [1000],
            }
        )

        result = data_writer.write_data("stock_daily", df, "2024-01-02")

        assert result.rows_written == 1
        mock_market_write_service.save_bars.assert_called_once()
        assert mock_market_write_service.save_bars.call_args.kwargs["dataset"] == (
            "stock_daily"
        )

    def test_calendar_uses_metadata_route_without_year_partition(
        self,
        data_writer,
        mock_metadata_service,
    ) -> None:
        df = pl.DataFrame(
            {
                "cal_date": [date(2024, 1, 2)],
                "is_open": [1],
            }
        )

        result = data_writer.write_data("calendar", df, "2024-01-02")

        assert result.file_path == "calendar_store:2024-01-02"
        assert result.rows_written == 1
        mock_metadata_service.save_calendar.assert_called_once()

    def test_stock_basic_uses_registered_basic_asset_class(
        self,
        data_writer,
        mock_metadata_service,
    ) -> None:
        df = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "symbol": ["000001"],
                "name": ["平安银行"],
            }
        )

        result = data_writer.write_data("stock_basic", df, "2024-01-02")

        assert result.file_path == "instrument_store:stock_basic"
        assert result.rows_written == 1
        mock_metadata_service.register_instruments_batch.assert_called_once()
        assert (
            mock_metadata_service.register_instruments_batch.call_args.kwargs[
                "asset_class"
            ]
            == "stock"
        )
```

- [ ] **Step 2: Run the writer tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_data_writer_unit.py -q
```

Expected: PASS before refactor or FAIL only where current fixture behavior differs. If the tests pass before refactor, keep them: they lock behavior while changing implementation.

- [ ] **Step 3: Import registry write metadata**

In `data_writer.py`, add these imports:

```python
from ditto_application.processes.ingestion.dataset_registry import (
    DatasetRegistration,
    WriteKind,
    default_dataset_registry,
)
```

- [ ] **Step 4: Replace writer routing in `write_data()`**

In `IngestionDataWriter.write_data()`, replace the `metadata_datasets`, `year`, `handlers`, and `if dataset_enum not in handlers` block with:

```python
        registration = default_dataset_registry().require(dataset_enum)
        year = int(trade_date[:4]) if registration.requires_year_partition else 0

        handler = self._build_write_handler(
            registration=registration,
            dataset=dataset,
            dataset_enum=dataset_enum,
            df=df,
            year=year,
            on_duplicate=on_duplicate,
            source_ticker_col="source_ticker",
            trade_date=trade_date,
        )
        return handler()
```

- [ ] **Step 5: Replace `_build_dataset_handlers()` with `_build_write_handler()`**

Delete `_build_dataset_handlers()` and add this method in its place:

```python
    def _build_write_handler(
        self,
        *,
        registration: DatasetRegistration,
        dataset: str,
        dataset_enum: Dataset,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate,
        source_ticker_col: str,
        trade_date: str,
    ) -> Callable[[], WriteResult]:
        """Build the writer callable from registry metadata."""
        match registration.write_kind:
            case WriteKind.TRADED_BARS:
                bars_dataset = cast(
                    Literal[
                        "stock_daily",
                        "etf_daily",
                        "index_daily",
                        "fx_daily",
                        "commodity_daily",
                    ],
                    registration.write_dataset,
                )
                return lambda: self._write_traded_bars(
                    dataset,
                    df,
                    year,
                    on_duplicate,
                    source_ticker_col,
                    bars_dataset,
                )
            case WriteKind.INSTRUMENT_CODE_BARS:
                bars_dataset = cast(
                    Literal["fx_daily", "commodity_daily"],
                    registration.write_dataset,
                )
                return lambda: self._write_instrument_code_bars(
                    dataset,
                    df,
                    year,
                    on_duplicate,
                    bars_dataset,
                )
            case WriteKind.STOCK_STATUS:
                return lambda: self._write_stock_status(
                    dataset,
                    df,
                    year,
                    source_ticker_col,
                )
            case WriteKind.ADJ_FACTOR:
                return lambda: self._write_adj_factor(
                    dataset,
                    df,
                    year,
                    on_duplicate,
                    source_ticker_col,
                )
            case WriteKind.FUNDAMENTAL:
                return lambda: self._write_fundamental(
                    dataset,
                    dataset_enum,
                    df,
                    year,
                )
            case WriteKind.CAPITAL:
                return lambda: self._write_capital(
                    dataset,
                    dataset_enum,
                    df,
                    year,
                )
            case WriteKind.MACRO:
                return lambda: self._write_macro(dataset, df, year)
            case WriteKind.CALENDAR:
                return lambda: self._write_calendar(df, trade_date)
            case WriteKind.BASIC:
                asset_class = registration.basic_asset_class
                if asset_class is None:
                    raise AppProcessError(
                        f"数据集 {dataset} 缺少 basic_asset_class 定义",
                        field="dataset",
                        value=dataset,
                    )
                return lambda: self._write_basic(df, trade_date, asset_class)
            case WriteKind.UNSUPPORTED:
                raise AppProcessError(
                    f"不支持写入数据集: {dataset}",
                    field="dataset",
                    value=dataset,
                )
        raise AppProcessError(
            f"未知写入路由: {registration.write_kind.value}",
            field="dataset",
            value=dataset,
        )
```

- [ ] **Step 6: Remove unused imports and variables**

In `data_writer.py`, remove imports that become unused after the refactor. Run this command to let ruff point at any remaining import issue:

```bash
pixi run -e dev ruff check packages/application/src/ditto_application/processes/ingestion/data_writer.py
```

Expected: PASS.

- [ ] **Step 7: Run data writer tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_data_writer_unit.py -q
```

Expected: PASS.

- [ ] **Step 8: Run ingestion unit tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add \
  packages/application/src/ditto_application/processes/ingestion/data_writer.py \
  packages/application/tests/unit/process/ingestion/test_data_writer_unit.py
git commit -m "refactor(ingestion): route data writes through dataset registry"
```

---

## Task 6: Add Registry Conformance Tests

**Files:**
- Modify: `packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py`

- [ ] **Step 1: Add conformance tests**

Append this class to `test_dataset_registry_unit.py`:

```python
@pytest.mark.unit
class TestDatasetRegistryConformance:
    """Cross-route invariants for default registrations."""

    def test_every_instrument_supported_dataset_has_instrument_factory(self) -> None:
        registry = default_dataset_registry()

        for dataset in registry.supported_instrument_datasets():
            registration = registry.require(dataset)
            assert registration.instrument_fetch_factory is not None

    def test_every_date_fetchable_registration_has_daily_factory(self) -> None:
        registry = default_dataset_registry()
        date_fetchable = {
            Dataset.CALENDAR,
            Dataset.STOCK_BASIC,
            Dataset.ETF_BASIC,
            Dataset.INDEX_BASIC,
            Dataset.STOCK_DAILY,
            Dataset.ETF_DAILY,
            Dataset.INDEX_DAILY,
            Dataset.STOCK_STATUS,
            Dataset.ADJ_FACTOR,
            Dataset.FUND_ADJ,
            Dataset.BALANCE_SHEET,
            Dataset.INCOME_STATEMENT,
            Dataset.CASH_FLOW,
            Dataset.DIVIDEND,
            Dataset.VALUATION_METRICS,
            Dataset.MARGIN_TRADING,
            Dataset.PLEDGE_RATIO,
            Dataset.MACRO_INDICATORS,
            Dataset.CORPORATE_ACTIONS,
            Dataset.FX_DAILY,
            Dataset.COMMODITY_DAILY,
        }

        for dataset in date_fetchable:
            assert registry.require(dataset).daily_fetch_factory is not None

    def test_index_weight_is_registered_but_has_no_runtime_route(self) -> None:
        registration = default_dataset_registry().require(Dataset.INDEX_WEIGHT)

        assert registration.daily_fetch_factory is None
        assert registration.instrument_fetch_factory is None
        assert registration.write_kind is WriteKind.UNSUPPORTED
```

- [ ] **Step 2: Run conformance tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py -q
```

Expected: PASS.

- [ ] **Step 3: Run targeted ingestion tests**

Run:

```bash
pixi run -e dev pytest \
  packages/application/tests/unit/process/test_coordinator_constants_unit.py \
  packages/application/tests/unit/process/ingestion/test_fetch_handlers_registry_unit.py \
  packages/application/tests/unit/process/ingestion/test_data_writer_unit.py \
  packages/application/tests/unit/process/ingestion/test_coordinator_instrument_unit.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py
git commit -m "test(ingestion): add dataset registry conformance checks"
```

---

## Task 7: Document The Dataset Registry Contract

**Files:**
- Modify: `packages/application/CLAUDE.md`
- Modify: `docs/reviews/audit/2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md`

- [ ] **Step 1: Add application package guidance**

In `packages/application/CLAUDE.md`, add this section near the ingestion/process guidance:

```markdown
### DatasetRegistry 摄取路由规则

- `ditto_application.processes.ingestion.dataset_registry` 是 application ingestion 的唯一数据集运行时路由表。
- 新增数据集时，先在 `ditto_data.models.Dataset` 增加稳定 ID，再在 `default_dataset_registry()` 增加 `DatasetRegistration`。
- `fetch_handlers.py`、`data_writer.py`、`coordinator_constants.py` 不允许新增独立的 `Dataset -> handler` 映射。
- 如果数据源 Protocol 没有按标的方法，不要把该数据集加入 `SUPPORTED_INSTRUMENT_DATASETS`。
- `Dataset` enum 只保留稳定 ID 和低频兼容属性；运行时 fetch/write/support 能力由 registry 表达。
```

- [ ] **Step 2: Add completion note to the architecture report**

In `docs/reviews/audit/2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md`, under `#### Batch 1：DataCatalog / DatasetRegistry（P0）`, add this sentence after the task list:

```markdown
实施计划见 `docs/superpowers/plans/2026-05-14-dataset-registry-ingestion.md`；执行时以该计划的任务顺序和验收命令为准。
```

- [ ] **Step 3: Run documentation checks**

Run:

```bash
pixi run -e dev pre-commit run trailing-whitespace --files \
  packages/application/CLAUDE.md \
  docs/reviews/audit/2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md
pixi run -e dev pre-commit run end-of-file-fixer --files \
  packages/application/CLAUDE.md \
  docs/reviews/audit/2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md
```

Expected: both hooks pass or modify only trailing whitespace / final newline. If a hook modifies a file, review the diff and include the hook change in Step 4.

- [ ] **Step 4: Commit**

```bash
git add \
  packages/application/CLAUDE.md \
  docs/reviews/audit/2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md
git commit -m "docs(ingestion): document dataset registry routing"
```

---

## Task 8: Final Validation

**Files:**
- Validate all files changed in Tasks 1-7.

- [ ] **Step 1: Run focused tests**

Run:

```bash
pixi run -e dev pytest \
  packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py \
  packages/application/tests/unit/process/ingestion/test_fetch_handlers_registry_unit.py \
  packages/application/tests/unit/process/ingestion/test_data_writer_unit.py \
  packages/application/tests/unit/process/ingestion/test_coordinator_instrument_unit.py \
  packages/application/tests/unit/process/test_coordinator_constants_unit.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run application ingestion tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/process/ingestion -q
```

Expected: PASS.

- [ ] **Step 3: Run full project check**

Run:

```bash
pixi run -e dev check
```

Expected:

```text
ruff check . passed
ruff format . unchanged
basedpyright: 0 errors
fast tests passed
Contracts: 36 kept, 0 broken
Architecture smell check passed
```

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: only intentional files are modified or all task commits are already created. Existing unrelated untracked files may remain; do not add them.

- [ ] **Step 5: Commit final validation note if any files changed**

If Step 3 or pre-commit hooks modify files, run:

```bash
git add packages/application docs/reviews/audit
git commit -m "chore(ingestion): finalize dataset registry checks"
```

Expected: commit succeeds. If there are no modified tracked files, skip this commit.

---

## Self-Review

Spec coverage:

- Batch 1 requires a `DatasetRegistry`: Task 1 and Task 2 create it.
- Fetch routing must be centralized: Task 4 moves `fetch_handlers.py` onto the registry.
- Write routing must be centralized: Task 5 moves `data_writer.py` onto registry `WriteKind`.
- Instrument support must stop being a hardcoded set: Task 3 derives it from the registry.
- New dataset conformance must be testable: Task 6 adds registry invariant tests.
- Documentation must explain the new rule: Task 7 updates application guidance and links the plan from the architecture report.

Placeholder scan:

- No empty sections.
- No unresolved markers.
- Each task has exact file paths, commands, expected results, and concrete code snippets.

Type consistency:

- `DatasetRegistration`, `DatasetRegistry`, `WriteKind`, `DailyFetchContext`, and `InstrumentFetchContext` are defined before use.
- `default_dataset_registry()` returns `DatasetRegistry` everywhere.
- `SUPPORTED_INSTRUMENT_DATASETS` changes to `frozenset[Dataset]`, and tests are updated to match.
- Data writer dispatch uses `DatasetRegistration.write_kind` and keeps existing `WriteResult` behavior.

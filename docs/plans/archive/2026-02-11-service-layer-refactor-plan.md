# Service Layer Selective Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use @superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 重构 Service 层 API，采用选择性重构策略：保留符合规范的方法，重命名不符合规范的方法，新增缺失的语义化方法。

**Architecture:** 当前 Service 层使用统一的 `query()` / `write()` 方法，导致类型安全弱、可发现性低。重构后使用明确的 `get_` / `find_` / `list_` / `save_` 等方法，每个方法有清晰的参数和返回类型。

**Tech Stack:** Python 3.12+, Polars, Pytest, Ruff, basedpyright

---

## Background

当前 Service 层问题：
1. **类型安全弱** - 不同 dataset 的必填参数不同，但类型无法区分
2. **上游体验差** - Query 对象参数混乱，不知道该传什么
3. **可发现性低** - IDE 无法帮助用户发现有哪些查询能力

## Strategy: Selective Refactor

| 策略 | 说明 |
|------|------|
| **保留** | 已符合命名规范的方法 |
| **重命名** | 不符合规范的方法（如 `get_*` 返回 list → `list_*`） |
| **新增** | 缺失的语义化方法 |
| **删除** | 通用的 `query()` / `write()` 和废弃的 Query/Result 类型 |

## Naming Convention（严格执行）

| 前缀 | 语义 | 返回类型 | 数据不存在时 |
|------|------|---------|-------------|
| `get_` | 按唯一条件查**单条** | `T \| None` | 返回 `None` |
| `find_` | **多维条件**查询（Query 对象） | `pl.DataFrame` | 返回空 DataFrame |
| `list_` | 按条件查**多条**（参数明确） | `pl.DataFrame` / `list` | 返回空结果 |
| `save_` | 保存/写入 | 结果对象 | - |
| `is_` | 布尔判断 | `bool` | 返回 `False` |
| `resolve_` | 解析转换 | 值或 `None` | 返回 `None` |
| `count_` | 计数/统计 | `int` | 返回 `0` |

---

## Execution Order

| Priority | Service | Complexity | Changes |
|----------|---------|-------------|---------|
| P0 | SourceService | S | 1 rename |
| P1 | IngestionLogService | S | 4 rename |
| P1 | QualityRecordService | S | 2 rename |
| P2 | FactorService | M | 1 rename + 1 add |
| P2 | FeatureService | M | 1 rename + 1 add |
| P2 | MacroService | M | 2 rename + 1 add |
| P3 | CapitalService | L | delete query + 10 add |
| P3 | FundamentalService | L | delete query + 14 add |
| P4 | MarketService | L | refactor query + 4 add |
| P4 | MetadataService | XL | delete query + 9 keep + 5 rename + 4 add |

---

## Single Service Change Workflow

```
1. [Code] Add new methods (get_*/save_*/list_*/find_*)
2. [Test] Update/add tests for new methods
3. [Code] Update upstream callers
4. [Verify] grep confirm no old method calls
5. [Code] Delete old methods (query/write)
6. [Code] Delete deprecated types (Query/Result)
7. [Verify] Run pixi run -e dev check
8. [Commit] git commit
```

---

## Upstream Caller Detection

Run for each Service refactor:

```bash
# Find all Service imports
grep -r "from ditto_data.services import" packages/ apps/ --include="*.py"

# Find old method calls
grep -r "\.query(" packages/ apps/ --include="*.py"
grep -r "\.write(" packages/ apps/ --include="*.py"

# Find old type usage
grep -r "CapitalQuery" packages/ apps/ --include="*.py"
grep -r "FundamentalQuery" packages/ apps/ --include="*.py"
```

---

## Task 1: SourceService (P0)

**Files:**
- Modify: `packages/data/src/ditto_data/services/source_service.py`
- Test: `packages/data/tests/unit/services/test_source_service.py`

**Change:**
```python
# Before
def get(self, name: str | Source) -> DataSource

# After
def get_source(self, name: str | Source) -> DataSource
```

**Step 1: Rename method**

```python
# packages/data/src/ditto_data/services/source_service.py

class SourceService:
    def get_source(self, name: str | Source) -> DataSource:  # renamed from get()
        # ... existing implementation ...
```

**Step 2: Update tests**

Run: `pixi run -e dev test --unit packages/data/tests/unit/services/test_source_service.py -v`
Expected: FAIL with "attribute error: 'SourceService' has no attribute 'get'"

Fix test: `service.get("tushare")` → `service.get_source("tushare")`

**Step 3: Find upstream callers**

Run: `grep -r "\.get(" packages/ apps/ --include="*.py" | grep -i source`

Update all callers.

**Step 4: Verify no old calls**

Run: `grep -r "\.get(" packages/ apps/ --include="*.py" | grep -i source`
Expected: No results (or only unrelated)

**Step 5: Run verification**

Run: `pixi run -e dev check`
Expected: All pass

**Step 6: Commit**

```bash
git add packages/data/src/ditto_data/services/source_service.py
git add packages/data/tests/unit/services/test_source_service.py
git commit -m "refactor(services): rename SourceService.get() to get_source()"
```

---

## Task 2: IngestionLogService (P1)

**Files:**
- Modify: `packages/data/src/ditto_data/services/ingestion_log_service.py`
- Test: `packages/data/tests/unit/services/test_ingestion_log_service.py`

**Changes:**
| Old | New | Reason |
|-----|------|--------|
| `get_failed_dates()` | `list_failed_dates()` | Returns list |
| `get_failed_logs()` | `list_failed_logs()` | Returns list |
| `get_ingested_dates()` | `list_ingested_dates()` | Returns list |
| `get_success_rate()` | `count_success_rate()` | Statistical count |

**Keep:** `get_log()`, `get_last_success_date()`, `get_stats()`, `save_log()`

**Step 1: Rename methods**

```python
# packages/data/src/ditto_data/services/ingestion_log_service.py

class IngestionLogService:
    def list_failed_dates(  # renamed from get_failed_dates
        self, dataset: str, source: str, limit: int, max_attempts: int
    ) -> list[str]:
        # ... existing implementation ...

    def list_failed_logs(  # renamed from get_failed_logs
        self, dataset: str, source: str, limit: int, max_attempts: int
    ) -> list[IngestionLog]:
        # ... existing implementation ...

    def list_ingested_dates(  # renamed from get_ingested_dates
        self, dataset: str, source: str, status: IngestionStatus | None
    ) -> list[str]:
        # ... existing implementation ...

    def count_success_rate(  # renamed from get_success_rate
        self, dataset: str, source: str, start_date: str | None
    ) -> float:
        # ... existing implementation ...
```

**Step 2: Update tests**

Run: `pixi run -e dev test --unit packages/data/tests/unit/services/test_ingestion_log_service.py -v`
Expected: FAIL for renamed methods

Fix all test calls to use new method names.

**Step 3: Find upstream callers**

Run: `grep -rn "\.get_failed_dates\|\.get_failed_logs\|\.get_ingested_dates\|\.get_success_rate" packages/ apps/ --include="*.py"`

Update all callers.

**Step 4: Verify no old calls**

Run: `grep -rn "\.get_failed_dates\|\.get_failed_logs\|\.get_ingested_dates\|\.get_success_rate" packages/ apps/ --include="*.py"`
Expected: No results

**Step 5: Run verification**

Run: `pixi run -e dev check`
Expected: All pass

**Step 6: Commit**

```bash
git add packages/data/src/ditto_data/services/ingestion_log_service.py
git add packages/data/tests/unit/services/test_ingestion_log_service.py
git commit -m "refactor(services): rename IngestionLogService methods to follow naming convention"
```

---

## Task 3: QualityRecordService (P1)

**Files:**
- Modify: `packages/data/src/ditto_data/services/quality_record_service.py`
- Test: `packages/data/tests/unit/services/test_quality_record_service.py`

**Changes:**
| Old | New | Reason |
|-----|------|--------|
| `get_quarantined_data()` | `list_quarantined_data()` | Returns multi-row DataFrame |
| `get_failed_data_df()` | `get_failed_data()` | Single row, remove `_df` suffix |

**Keep:** `save_comparison()`, `get_comparison()`, `get_comparison_stats()`, `save_failed_data()`, `get_quarantine_stats()`, `get_all_stats()`, `clear_old_quarantine_records()`

**Step 1: Rename methods**

```python
# packages/data/src/ditto_data/services/quality_record_service.py

class QualityRecordService:
    def list_quarantined_data(  # renamed from get_quarantined_data
        self, dataset: str | None, rule_id: str | None, limit: int
    ) -> pl.DataFrame:
        # ... existing implementation ...

    def get_failed_data(  # renamed from get_failed_data_df
        self, row_id: int
    ) -> pl.DataFrame:
        # ... existing implementation ...
```

**Step 2: Update tests**

Run: `pixi run -e dev test --unit packages/data/tests/unit/services/test_quality_record_service.py -v`
Expected: FAIL for renamed methods

Fix test calls.

**Step 3: Find upstream callers**

Run: `grep -rn "\.get_quarantined_data\|\.get_failed_data_df" packages/ apps/ --include="*.py"`

Update all callers.

**Step 4: Verify no old calls**

Run: `grep -rn "\.get_quarantined_data\|\.get_failed_data_df" packages/ apps/ --include="*.py"`
Expected: No results

**Step 5: Run verification**

Run: `pixi run -e dev check`
Expected: All pass

**Step 6: Commit**

```bash
git add packages/data/src/ditto_data/services/quality_record_service.py
git add packages/data/tests/unit/services/test_quality_record_service.py
git commit -m "refactor(services): rename QualityRecordService methods to follow naming convention"
```

---

## Task 4: FactorService (P2)

**Files:**
- Modify: `packages/data/src/ditto_data/services/factor_service.py`
- Test: `packages/data/tests/unit/services/test_factor_service.py`

**Changes:**
| Action | Method |
|--------|---------|
| Rename | `query()` → `find_factors()` |
| Add | `list_factors(start, end, factor_ids)` - convenience method |

**Step 1: Rename query to find_factors**

```python
# packages/data/src/ditto_data/services/factor_service.py

class FactorService:
    def find_factors(self, query: FactorQuery) -> pl.DataFrame:  # renamed from query()
        # ... existing implementation ...
```

**Step 2: Add list_factors convenience method**

```python
def list_factors(
    self, start: str, end: str, factor_ids: list[str] | None = None
) -> pl.DataFrame:
    """List factors by date range (convenience method)."""
    query = FactorQuery(
        start=start,
        end=end,
        factor_ids=factor_ids,
    )
    return self.find_factors(query)
```

**Step 3: Write failing test for new method**

```python
# packages/data/tests/unit/services/test_factor_service.py

def test_list_factors_convenience():
    result = factor_service.list_factors("2024-01-01", "2024-01-31")
    assert isinstance(result, pl.DataFrame)
    # Add specific assertions based on your data
```

**Step 4: Run test to verify it passes**

Run: `pixi run -e dev test --unit packages/data/tests/unit/services/test_factor_service.py::test_list_factors_convenience -v`
Expected: PASS

**Step 5: Find upstream callers**

Run: `grep -rn "FactorService\|\.query(" packages/ apps/ --include="*.py" | grep -i factor`

Update all callers: `service.query(...)` → `service.find_factors(...)`

**Step 6: Verify no old calls**

Run: `grep -rn "\.query(" packages/ apps/ --include="*.py" | grep -i factor`
Expected: No results (or `find_factors` only)

**Step 7: Delete FactorQuery if no longer needed**

If `FactorQuery` is only used internally, consider removing it and using direct parameters.

**Step 8: Run verification**

Run: `pixi run -e dev check`
Expected: All pass

**Step 9: Commit**

```bash
git add packages/data/src/ditto_data/services/factor_service.py
git add packages/data/tests/unit/services/test_factor_service.py
git commit -m "refactor(services): rename FactorService.query() to find_factors() and add list_factors()"
```

---

## Task 5: FeatureService (P2)

**Files:**
- Modify: `packages/data/src/ditto_data/services/feature_service.py`
- Test: `packages/data/tests/unit/services/test_feature_service.py`

**Changes:**
| Action | Method |
|--------|---------|
| Rename | `query()` → `find_indicators()` |
| Add | `list_indicators(start, end, indicator_types)` - convenience method |

**Step 1: Rename query to find_indicators**

```python
# packages/data/src/ditto_data/services/feature_service.py

class FeatureService:
    def find_indicators(self, query: FeatureQuery) -> pl.DataFrame:  # renamed from query()
        # ... existing implementation ...
```

**Step 2: Add list_indicators convenience method**

```python
def list_indicators(
    self, start: str, end: str, indicator_types: list[str] | None = None
) -> pl.DataFrame:
    """List indicators by date range (convenience method)."""
    query = FeatureQuery(
        start=start,
        end=end,
        indicator_types=indicator_types,
    )
    return self.find_indicators(query)
```

**Step 3: Write failing test for new method**

```python
# packages/data/tests/unit/services/test_feature_service.py

def test_list_indicators_convenience():
    result = feature_service.list_indicators("2024-01-01", "2024-01-31")
    assert isinstance(result, pl.DataFrame)
```

**Step 4: Run test to verify it passes**

Run: `pixi run -e dev test --unit packages/data/tests/unit/services/test_feature_service.py::test_list_indicators_convenience -v`
Expected: PASS

**Step 5: Find upstream callers**

Run: `grep -rn "FeatureService\|\.query(" packages/ apps/ --include="*.py" | grep -i feature`

Update all callers.

**Step 6: Verify no old calls**

Run: `grep -rn "\.query(" packages/ apps/ --include="*.py" | grep -i feature`
Expected: No results (or `find_indicators` only)

**Step 7: Run verification**

Run: `pixi run -e dev check`
Expected: All pass

**Step 8: Commit**

```bash
git add packages/data/src/ditto_data/services/feature_service.py
git add packages/data/tests/unit/services/test_feature_service.py
git commit -m "refactor(services): rename FeatureService.query() to find_indicators() and add list_indicators()"
```

---

## Task 6: MacroService (P2)

**Files:**
- Modify: `packages/data/src/ditto_data/services/macro_service.py`
- Test: `packages/data/tests/unit/services/test_macro_service.py`

**Changes:**
| Action | Method |
|--------|---------|
| Rename | `query()` → `find_indicators()` |
| Rename | `write()` → `save_indicators()` |
| Add | `list_indicators(start, end, category)` - convenience method |
| Delete | `MacroQuery`, `MacroWriteResult` |

**Step 1: Rename methods**

```python
# packages/data/src/ditto_data/services/macro_service.py

class MacroService:
    def find_indicators(self, query: MacroQuery) -> pl.DataFrame:  # renamed from query()
        # ... existing implementation ...

    def save_indicators(self, df: pl.DataFrame) -> MacroWriteResult:  # renamed from write()
        # ... existing implementation ...
```

**Step 2: Add list_indicators convenience method**

```python
def list_indicators(
    self, start: str, end: str, category: str | None = None
) -> pl.DataFrame:
    """List indicators by date range (convenience method)."""
    query = MacroQuery(
        start=start,
        end=end,
        category=category,
    )
    return self.find_indicators(query)
```

**Step 3: Write failing test for new method**

```python
# packages/data/tests/unit/services/test_macro_service.py

def test_list_indicators_convenience():
    result = macro_service.list_indicators("2024-01-01", "2024-01-31")
    assert isinstance(result, pl.DataFrame)
```

**Step 4: Run test to verify it passes**

Run: `pixi run -e dev test --unit packages/data/tests/unit/services/test_macro_service.py::test_list_indicators_convenience -v`
Expected: PASS

**Step 5: Find upstream callers**

Run: `grep -rn "MacroService\|MacroQuery\|MacroWriteResult" packages/ apps/ --include="*.py"`

Update all callers: `service.query(...)` → `service.find_indicators(...)`, `service.write(...)` → `service.save_indicators(...)`

**Step 6: Verify no old calls**

Run: `grep -rn "\.query(\|\.write(" packages/ apps/ --include="*.py" | grep -i macro`
Expected: No results

**Step 7: Delete deprecated types**

```python
# Remove from file:
# - MacroQuery
# - MacroWriteResult
```

**Step 8: Run verification**

Run: `pixi run -e dev check`
Expected: All pass

**Step 9: Commit**

```bash
git add packages/data/src/ditto_data/services/macro_service.py
git add packages/data/tests/unit/services/test_macro_service.py
git commit -m "refactor(services): rename MacroService methods, add list_indicators(), delete deprecated types"
```

---

## Task 7: CapitalService (P3)

**Files:**
- Modify: `packages/data/src/ditto_data/services/capital_service.py`
- Test: `packages/data/tests/unit/services/test_capital_service.py`

**Changes:**
| Action | Methods |
|--------|---------|
| Delete | `query()`, `write()`, `_require_instrument_id()`, `_require_index_id()` |
| Delete | `CapitalQuery`, `CapitalWriteResult`, `CapitalDataset` |
| Add | 5 × `get_*` methods |
| Add | 5 × `save_*` methods |

**Step 1: Add get_* methods**

```python
# packages/data/src/ditto_data/services/capital_service.py

class CapitalService:
    # get_* - Single record queries

    def get_margin_trading(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get margin trading data for instrument on date."""
        return self._margin_trading_reader.get(instrument_id, as_of_date)

    def get_pledge_ratio(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get pledge ratio data for instrument on date."""
        return self._pledge_ratio_reader.get(instrument_id, as_of_date)

    def get_valuation_metrics(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get valuation metrics for instrument on date."""
        return self._valuation_metrics_reader.get(instrument_id, as_of_date)

    def get_futures(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get futures data for instrument on date."""
        return self._futures_reader.get(instrument_id, as_of_date)

    def get_index_composition(
        self, index_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get index composition on date."""
        return self._index_composition_reader.get(index_id, as_of_date)
```

**Step 2: Add save_* methods**

```python
    # save_* - Write methods

    def save_margin_trading(self, df: pl.DataFrame) -> int:
        """Save margin trading data."""
        return self._margin_trading_writer.write(df)

    def save_pledge_ratio(self, df: pl.DataFrame) -> int:
        """Save pledge ratio data."""
        return self._pledge_ratio_writer.write(df)

    def save_valuation_metrics(self, df: pl.DataFrame) -> int:
        """Save valuation metrics data."""
        return self._valuation_metrics_writer.write(df)

    def save_futures(self, df: pl.DataFrame) -> int:
        """Save futures data."""
        return self._futures_writer.write(df)

    def save_index_composition(self, df: pl.DataFrame) -> int:
        """Save index composition data."""
        return self._index_composition_writer.write(df)
```

**Step 3: Write failing tests for new methods**

```python
# packages/data/tests/unit/services/test_capital_service.py

def test_get_margin_trading():
    result = capital_service.get_margin_trading("000001.SZ", date(2024, 1, 1))
    # Add assertions

def test_save_margin_trading():
    df = pl.DataFrame({...})  # Create test data
    count = capital_service.save_margin_trading(df)
    assert count > 0

# ... similar tests for all 10 new methods ...
```

**Step 4: Run tests to verify they pass**

Run: `pixi run -e dev test --unit packages/data/tests/unit/services/test_capital_service.py -v`
Expected: PASS for all new tests

**Step 5: Find upstream callers**

Run: `grep -rn "CapitalService\|CapitalQuery\|\.query(\|\.write(" packages/ apps/ --include="*.py" | grep -i capital`

Update all callers to use new methods:
- `service.query(CapitalQuery(..., "margin_trading", ...))` → `service.get_margin_trading(...)`
- `service.write("margin_trading", df)` → `service.save_margin_trading(df)`

**Step 6: Verify no old calls**

Run: `grep -rn "\.query(\|\.write(" packages/ apps/ --include="*.py" | grep -i capital`
Expected: No results

**Step 7: Delete old methods and types**

```python
# Remove from class:
# - query()
# - write()
# - _require_instrument_id()
# - _require_index_id()

# Remove from module:
# - CapitalQuery
# - CapitalWriteResult
# - CapitalDataset
```

**Step 8: Update tests**

Update or remove tests for old methods.

**Step 9: Run verification**

Run: `pixi run -e dev check`
Expected: All pass

**Step 10: Commit**

```bash
git add packages/data/src/ditto_data/services/capital_service.py
git add packages/data/tests/unit/services/test_capital_service.py
git commit -m "refactor(services): CapitalService - replace query/write with dedicated get/save methods"
```

---

## Task 8: FundamentalService (P3)

**Files:**
- Modify: `packages/data/src/ditto_data/services/fundamental_service.py`
- Test: `packages/data/tests/unit/services/test_fundamental_service.py`

**Changes:**
| Action | Methods |
|--------|---------|
| Delete | `query()`, `write()` |
| Delete | `FundamentalQuery`, `FundamentalWriteResult`, `FundamentalDataset` |
| Add | 6 × `get_*` methods |
| Add | 1 × `list_*` method (corporate_actions needs date range) |
| Add | 7 × `save_*` methods |

**Step 1: Add get_* methods**

```python
# packages/data/src/ditto_data/services/fundamental_service.py

class FundamentalService:
    # get_* - Single record queries

    def get_balance_sheet(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get balance sheet for instrument on date."""
        return self._balance_sheet_reader.get(instrument_id, as_of_date)

    def get_income_statement(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get income statement for instrument on date."""
        return self._income_statement_reader.get(instrument_id, as_of_date)

    def get_cash_flow(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get cash flow for instrument on date."""
        return self._cash_flow_reader.get(instrument_id, as_of_date)

    def get_dividend(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get dividend data for instrument on date."""
        return self._dividend_reader.get(instrument_id, as_of_date)

    def get_forecast(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get forecast data for instrument on date."""
        return self._forecast_reader.get(instrument_id, as_of_date)

    def get_express(
        self, instrument_id: str, as_of_date: date
    ) -> pl.DataFrame | None:
        """Get express report for instrument on date."""
        return self._express_reader.get(instrument_id, as_of_date)
```

**Step 2: Add list_* method**

```python
    def list_corporate_actions(
        self, instrument_id: str, start_date: date, end_date: date
    ) -> pl.DataFrame:
        """List corporate actions for instrument in date range."""
        return self._corporate_actions_reader.get_range(instrument_id, start_date, end_date)
```

**Step 3: Add save_* methods**

```python
    # save_* - Write methods

    def save_balance_sheet(self, df: pl.DataFrame) -> int:
        """Save balance sheet data."""
        return self._balance_sheet_writer.write(df)

    def save_income_statement(self, df: pl.DataFrame) -> int:
        """Save income statement data."""
        return self._income_statement_writer.write(df)

    def save_cash_flow(self, df: pl.DataFrame) -> int:
        """Save cash flow data."""
        return self._cash_flow_writer.write(df)

    def save_dividend(self, df: pl.DataFrame) -> int:
        """Save dividend data."""
        return self._dividend_writer.write(df)

    def save_corporate_actions(self, df: pl.DataFrame) -> int:
        """Save corporate actions data."""
        return self._corporate_actions_writer.write(df)

    def save_forecast(self, df: pl.DataFrame) -> int:
        """Save forecast data."""
        return self._forecast_writer.write(df)

    def save_express(self, df: pl.DataFrame) -> int:
        """Save express report data."""
        return self._express_writer.write(df)
```

**Step 4-9:** Same as CapitalService (tests → find callers → verify → delete old → verify → commit)

---

## Task 9: MarketService (P4)

**Files:**
- Modify: `packages/data/src/ditto_data/services/market_service.py`
- Test: `packages/data/tests/unit/services/test_market_service.py`

**Changes:**
| Action | Methods |
|--------|---------|
| Rename | `query()` → `find_bars()` |
| Delete | `get_bars()` (replaced by find_bars) |
| Keep | `get_constituents()` (already follows convention) |
| Add | `list_bars(instrument_ids, start, end)` - convenience |
| Refactor | `write()` → 3 × `save_*` methods |
| Delete | `MarketWriteCommand`, `MarketWriteResult` |

**Step 1: Rename query to find_bars**

```python
# packages/data/src/ditto_data/services/market_service.py

class MarketService:
    def find_bars(self, query: BarsQuery) -> pl.DataFrame:  # renamed from query()
        # ... existing implementation ...
```

**Step 2: Delete get_bars**

Remove method (was just forwarding to query).

**Step 3: Add list_bars convenience method**

```python
    def list_bars(
        self, instrument_ids: list[int], start: str, end: str
    ) -> pl.DataFrame:
        """List bars for instruments in date range (convenience method)."""
        query = BarsQuery(
            instrument_ids=instrument_ids,
            start=start,
            end=end,
        )
        return self.find_bars(query)
```

**Step 4: Refactor write to save_* methods**

```python
    # save_* - Write methods

    def save_bars(self, dataset: str, df: pl.DataFrame, year: int) -> int:
        """Save bars data for dataset and year."""
        # Delegate to appropriate writer based on dataset
        # ... implementation ...

    def save_adj_factor(self, df: pl.DataFrame, year: int) -> int:
        """Save adjustment factor data."""
        return self._adj_factor_writer.write(df, year)

    def save_stock_status(self, df: pl.DataFrame, year: int) -> int:
        """Save stock status data."""
        return self._stock_status_writer.write(df, year)
```

**Step 5-9:** Same workflow (tests → find callers → verify → delete old → verify → commit)

---

## Task 10: MetadataService (P4)

**Files:**
- Modify: `packages/data/src/ditto_data/services/metadata_service.py`
- Test: `packages/data/tests/unit/services/test_metadata_service.py`

**Keep (9 methods):**
- `get_symbol()`, `get_source_ticker()`, `get_stock_industry()`
- `get_last_trading_day()`, `get_first_trading_day()`
- `is_trading_day()`
- `resolve_instrument_id()`, `resolve_instrument_ids_batch()`
- `register_instrument()`, `register_instruments_batch()`

**Rename (5 methods):**
| Old | New | Reason |
|-----|------|--------|
| `get_trading_days()` | `list_trading_days()` | Returns list |
| `get_industry_stocks()` | `list_industry_stocks()` | Returns list |
| `get_range_df()` | `list_calendar_range()` | Returns DataFrame (multi-row) |
| `write()` | `save_calendar()` | Write method |
| `upsert()` | `save_calendar()` | Duplicate, consolidate |

**Add (4 methods):**
| Method | Purpose |
|---------|---------|
| `get_instrument(instrument_id)` | Single instrument |
| `find_securities(...)` | Multi-dimension query (replace query) |
| `find_industries(is_active, level)` | Multi-dimension query (replace query) |
| `list_instrument_ids(asset_class)` | Convenience method |

**Delete:**
- `query()`
- `get_instruments()` (replaced by find_securities)
- `get_industries()` (replaced by find_industries)
- `MetadataQuery`, `MetadataWriteCommand`, `MetadataWriteResult`

**Step 1: Rename methods**

```python
# packages/data/src/ditto_data/services/metadata_service.py

class MetadataService:
    def list_trading_days(  # renamed from get_trading_days
        self, start: str, end: str, only_open: bool = True
    ) -> list[str]:
        # ... existing implementation ...

    def list_industry_stocks(  # renamed from get_industry_stocks
        self, industry_id: str, asof: str | None
    ) -> list[int]:
        # ... existing implementation ...

    def list_calendar_range(  # renamed from get_range_df
        self, start: str, end: str, only_open: bool = True
    ) -> pl.DataFrame:
        # ... existing implementation ...

    def save_calendar(self, records: list[dict]) -> int:  # renamed from write/upsert
        # ... consolidated implementation ...
```

**Step 2: Add get_instrument**

```python
    def get_instrument(self, instrument_id: int) -> dict | None:
        """Get single instrument by ID."""
        return self._instrument_reader.get_instrument(instrument_id)
```

**Step 3: Add find_securities**

```python
    def find_securities(
        self,
        instrument_ids: list[int] | None = None,
        source_tickers: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """Find securities by multiple criteria."""
        return self._instrument_reader.find_securities(
            instrument_ids=instrument_ids,
            source_tickers=source_tickers,
            source=source,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
            asof=asof,
        )
```

**Step 4: Add find_industries**

```python
    def find_industries(
        self, is_active: bool = True, level: str | None = None
    ) -> pl.DataFrame:
        """Find industries by criteria."""
        return self._industry_reader.get_all(is_active, level)
```

**Step 5: Add list_instrument_ids**

```python
    def list_instrument_ids(self, asset_class: str | None = None) -> list[int]:
        """List instrument IDs by asset class."""
        df = self.find_securities(asset_class=asset_class)
        return df["instrument_id"].to_list()
```

**Step 6: Delete old methods and types**

Remove: `query()`, `get_instruments()`, `get_industries()`, `MetadataQuery`, `MetadataWriteCommand`, `MetadataWriteResult`

**Step 7-9:** Same workflow (tests → find callers → verify → commit)

---

## Verification Checklist (Each Service)

- [ ] New methods added
- [ ] Old methods deleted
- [ ] Deprecated types deleted
- [ ] Unit tests updated and passing
- [ ] Upstream callers updated (grep confirmed)
- [ ] Type check passes (`pixi run -e dev type`)
- [ ] Lint passes (`pixi run -e dev lint`)
- [ ] Format passes (`pixi run -e dev fmt`)
- [ ] All tests pass (`pixi run -e dev test --fast`)

## Final Acceptance

- [ ] All 10 Services refactored
- [ ] All methods follow naming convention
- [ ] CI passes (`pixi run -e dev ci`)
- [ ] Branch coverage ≥ 80%

## Risk & Mitigation

| Risk | Mitigation |
|------|------------|
| Upstream caller missed | grep confirm no old calls after each refactor, run full test suite |
| Type check failures | Run type check after each change |
| Insufficient test coverage | Update tests synchronously |
| Naming inconsistency | Strictly follow naming convention table |

---

**Plan complete and saved to `docs/plans/2026-02-11-service-layer-refactor-plan.md`**

## Execution Options

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?

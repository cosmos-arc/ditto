# Phase 0 Completion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete all remaining Phase 0 tasks to achieve a fully functional quantitative trading system foundation with data collection, validation, and API services.

**Architecture:** Building a robust data pipeline from Tushare/AkShare → Database → Validation → API, following TDD methodology with comprehensive test coverage.

**Tech Stack:** Python, FastAPI, DuckDB, SQLite, Tushare, AkShare, Polars, Pydantic, Pytest

---

## Phase 0 Remaining Tasks Overview

### Priority 1: Fix Critical Blockers
- P0-022: Fix import error in main.py (blocking all API execution)
- P0-012: Complete ETF list storage logic
- P0-031: Fix data source initialization script

### Priority 2: Core Data Collection
- P0-013 to P0-016: Daily data, adjustment factors, trading calendar collection
- P0-017 to P0-021: Data quality validation system

### Priority 3: API Services
- P0-024 to P0-026: Data query, update, and error handling APIs

### Priority 4: Tools & Scripts
- P0-032 to P0-033: Update remaining scripts

---

## Task 1: Fix API Import Error (P0-022)

**Files:**
- Modify: `apps/server/src/main.py:1-10`
- Test: `tests/api/test_main.py`

**Step 1: Write failing test**
```python
# tests/api/test_main.py
def test_app_imports_successfully():
    """Test that main FastAPI app imports without errors."""
    from apps.server.src.main import app
    assert app is not None
    assert app.title == "Ditto Quant API"
```

**Step 2: Run test to verify it fails**
```bash
pytest tests/api/test_main.py::test_app_imports_successfully -v
# Expected: FAIL with ImportError
```

**Step 3: Fix import in main.py**
```python
# Fix the logging_config import - should be from logging_config not loguru.logging_config
import logging_config  # Remove if unused, fix import path
```

**Step 4: Run test to verify it passes**
```bash
pytest tests/api/test_main.py::test_app_imports_successfully -v
# Expected: PASS
```

**Step 5: Commit**
```bash
git add apps/server/src/main.py tests/api/test_main.py
git commit -m "fix(api): P0-022 resolve logging_config import error"
```

---

## Task 2: Complete ETF List Storage (P0-012)

**Files:**
- Modify: `packages/core/src/data/collector.py:100-150`
- Test: `tests/data/test_collector.py`

**Step 1: Write failing test**
```python
def test_store_etf_list_to_database():
    """Test that ETF list is properly stored in database."""
    collector = DataCollector(mock_factory, mock_service)

    # Mock ETF data
    etf_data = pl.DataFrame({
        'symbol': ['510300.SH', '516010.SH'],
        'name': ['沪深300 ETF', '游戏 ETF'],
        'fund_manager': ['华夏基金', '国泰基金'],
        'tracking_index': ['沪深300指数', '动漫游戏指数'],
        'establishment_date': ['2012-05-04', '2021-02-24']
    })

    # Should store to database
    result = collector._store_etf_list(etf_data)
    assert result['total_records'] == 2
```

**Step 2: Run test to verify it fails**
```bash
pytest tests/data/test_collector.py::test_store_etf_list_to_database -v
```

**Step 3: Implement storage logic**
```python
def _store_etf_list(self, etf_data: pl.DataFrame) -> dict[str, Any]:
    """Store ETF list to database."""
    try:
        sqlite = self.data_service.get_sqlite()

        # Convert to records and insert
        records = etf_data.to_dicts()

        for record in records:
            sqlite.execute("""
                INSERT OR REPLACE INTO etf_list
                (symbol, name, fund_manager, tracking_index, establishment_date)
                VALUES (?, ?, ?, ?, ?)
            """, (
                record['symbol'], record['name'],
                record['fund_manager'], record['tracking_index'],
                record['establishment_date']
            ))

        return {'total_records': len(records), 'errors': 0}
    except Exception as e:
        logger.error(f"Failed to store ETF list: {e}")
        return {'total_records': 0, 'errors': 1}
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

---

## Task 3: Implement Daily Data Collection (P0-013)

**Files:**
- Modify: `packages/core/src/data/collector.py:200-300`
- Test: `tests/data/test_collector.py`

**Step 1: Write failing test**
```python
def test_update_daily_data():
    """Test daily data update from data source."""
    collector = DataCollector(mock_factory, mock_service)

    # Mock daily data
    daily_data = pl.DataFrame({
        'symbol': ['510300.SH'],
        'trade_date': ['2024-12-09'],
        'open': [3.5],
        'high': [3.6],
        'low': [3.4],
        'close': [3.55],
        'volume': [1000000],
        'amount': [3550000]
    })

    result = collector.update_daily_data(['510300.SH'])
    assert result['total_records'] > 0
```

**Step 2: Run test to verify it fails**

**Step 3: Implement update_daily_data**
```python
def update_daily_data(
    self,
    ts_codes: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
    force_update: bool = False
) -> dict[str, Any]:
    """Update daily market data for given symbols."""
    if not start_date:
        start_date = (date.today() - timedelta(days=7)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = date.today().strftime('%Y-%m-%d')

    total_records = 0
    errors = 0

    for symbol in ts_codes:
        try:
            # Get data from primary source
            source = self.data_factory.get_client()
            data = source.get_daily_data(symbol, start_date, end_date)

            # Store to DuckDB
            if not data.is_empty():
                duckdb = self.data_service.get_duckdb()
                # Convert and insert logic here
                total_records += len(data)

        except Exception as e:
            logger.error(f"Failed to update daily data for {symbol}: {e}")
            errors += 1

    return {'total_records': total_records, 'errors': errors}
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

---

## Task 4: Implement Adjustment Factor Collection (P0-014)

**Files:**
- Modify: `packages/core/src/data/collector.py`
- Test: `tests/data/test_collector.py`

**Step 1: Write failing test**
```python
def test_update_adj_factors():
    """Test adjustment factor update."""
    collector = DataCollector(mock_factory, mock_service)

    result = collector.update_adj_factors(['510300.SH'])
    assert isinstance(result, dict)
    assert 'total_records' in result
```

**Step 2: Run test to verify it fails**

**Step 3: Implement update_adj_factors**
```python
def update_adj_factors(
    self,
    ts_codes: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
    force_update: bool = False
) -> dict[str, Any]:
    """Update adjustment factors."""
    # Similar to update_daily_data but for adj factors
    pass
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

---

## Task 5: Implement Data Quality Validators (P0-017 to P0-021)

### Task 5.1: Basic OHLC Validator

**Files:**
- Create: `packages/core/src/data/validators/__init__.py`
- Create: `packages/core/src/data/validators/ohlc.py`
- Test: `tests/data/validators/test_ohlc.py`

**Step 1: Write failing test**
```python
def test_ohlc_validator():
    """Test OHLC data validation."""
    from packages.core.src.data.validators.ohlc import OHLCValidator

    validator = OHLCValidator()

    # Valid data
    valid_data = pl.DataFrame({
        'open': [3.5, 3.6],
        'high': [3.6, 3.7],
        'low': [3.4, 3.5],
        'close': [3.55, 3.65]
    })

    result = validator.validate(valid_data)
    assert result.is_valid

    # Invalid data (high < low)
    invalid_data = pl.DataFrame({
        'open': [3.5],
        'high': [3.4],  # Error: high < low
        'low': [3.6],
        'close': [3.55]
    })

    result = validator.validate(invalid_data)
    assert not result.is_valid
    assert "high price cannot be less than low" in result.errors[0]
```

**Step 2: Run test to verify it fails**

**Step 3: Implement OHLCValidator**
```python
from dataclasses import dataclass
from typing import List

@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]

class OHLCValidator:
    """Validator for OHLC data."""

    def validate(self, data: pl.DataFrame) -> ValidationResult:
        """Validate OHLC data constraints."""
        errors = []

        # Check high >= low
        if (data['high'] < data['low']).any():
            errors.append("high price cannot be less than low")

        # Check high >= open, close
        if (data['high'] < data['open']).any():
            errors.append("high price cannot be less than open")

        # Check low <= open, close
        if (data['low'] > data['open']).any():
            errors.append("low price cannot be greater than open")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
```

**Step 4: Run test to verify it passes**

**Step 5: Commit**

### Task 5.2: Cross-Source Validator

**Files:**
- Create: `packages/core/src/data/validators/cross_source.py`
- Test: `tests/data/validators/test_cross_source.py`

**Step 1: Write failing test**
```python
def test_cross_source_validation():
    """Test cross-source data validation."""
    pass
```

**Step 2-5: Implement similar to above**

---

## Task 6: Implement Data Query APIs (P0-024)

**Files:**
- Create: `apps/server/src/api/v1/data.py`
- Modify: `apps/server/src/main.py:50-60`
- Test: `tests/api/test_data.py`

**Step 1: Write failing test**
```python
def test_get_daily_data_api():
    """Test GET /api/v1/data/daily endpoint."""
    response = client.get("/api/v1/data/daily?symbol=510300.SH&start_date=2024-12-01")
    assert response.status_code == 200
    data = response.json()
    assert 'data' in data
    assert isinstance(data['data'], list)
```

**Step 2: Run test to verify it fails**

**Step 3: Implement API endpoint**
```python
# apps/server/src/api/v1/data.py
from fastapi import APIRouter, Depends, Query
from ditto_foundation.data import DataService

router = APIRouter(prefix="/data", tags=["data"])

@router.get("/daily")
async def get_daily_data(
    symbol: str = Query(..., description="Stock symbol"),
    start_date: str = Query(..., description="Start date"),
    end_date: str | None = Query(None, description="End date"),
    data_service: DataService = Depends(get_data_service)
):
    """Get daily market data."""
    try:
        df = await data_service.get_daily_data(symbol, start_date, end_date)
        return {
            "success": True,
            "data": df.to_dicts(),
            "count": len(df)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

**Step 4: Register router in main.py**

**Step 5: Run test to verify it passes**

**Step 6: Commit**

---

## Task 7: Fix Data Scripts (P0-031 to P0-033)

### Task 7.1: Fix init_data_sources.py

**Files:**
- Modify: `scripts/init_data_sources.py`
- Test: Manual testing

**Step 1: Test current script**
```bash
pixi run python scripts/init_data_sources.py
# Expected: Should fail with import errors
```

**Step 2: Fix imports**
```python
# Fix all import paths and missing dependencies
```

**Step 3: Test script runs successfully**

**Step 4: Commit**

### Task 7.2: Fix update_data.py and check_data_quality.py

**Similar steps for both scripts**

---

## Task 8: Final Integration & Testing

**Files:**
- Multiple
- Test: `tests/integration/test_phase0_complete.py`

**Step 1: Write integration test**
```python
async def test_complete_data_flow():
    """Test complete data flow from source to API."""
    # 1. Initialize data sources
    # 2. Collect ETF list
    # 3. Collect daily data
    # 4. Validate data
    # 5. Query via API
    # All steps should pass
```

**Step 2: Run integration tests**

**Step 3: Fix any issues**

**Step 4: Final commit**

---

## Testing Strategy

### Unit Tests
- Each function should have dedicated unit tests
- Target 95%+ code coverage
- Use pytest fixtures for common setup

### Integration Tests
- Test data flow from source to database
- Test API endpoints with real data
- Test error handling paths

### Manual Testing
- Verify scripts run without errors
- Check API responses manually
- Validate data quality visually

---

## Success Criteria

1. All Phase 0 tasks marked as ✅ in phase0_tasks.md
2. All tests passing (unit + integration)
3. API endpoints returning real data
4. Scripts executing without errors
5. Data quality validation working
6. Git history shows clean, atomic commits

---

## Next Steps

After Phase 0 completion:
1. Begin Phase 0.5: Data Quality Validation
2. Set up continuous integration
3. Start Phase 1: Paper Trading Infrastructure
4. Document best practices and patterns

# ING-X-2: Concurrent Write Safety Audit

**Date**: 2026-03-19
**Scope**: All Parquet writers in the Ditto codebase
**Goal**: Identify which services have concurrent write protection (FileLock + atomic_write) and which do not

---

## Executive Summary

Of all write paths in the Ditto codebase, **only `MarketService` uses FileLock** to protect concurrent writes. All other services that write to Parquet files rely solely on `atomic_write()` (write-to-temp-then-rename) for safety.

**Key finding**: `atomic_write()` provides OS-level atomicity (no partial writes), but does NOT protect against the classic read-modify-write race condition. If two processes concurrently read the same Parquet file, merge their data in memory, and write back, the last writer wins and the first writer's data is silently lost.

**Risk distribution**:
- **HIGH risk (3 writers)**: Year-partitioned Parquet stores called outside of MarketService, where concurrent writes to the same year partition are plausible during batch ingestion
- **MEDIUM risk (3 writers)**: Stores where concurrent writes are unlikely but not impossible (research artifacts, quality comparison, derived artifacts)
- **LOW risk (many writers)**: SQLite-backed stores (inherently protected by database locking) and metadata stores

---

## Infrastructure Components

### `atomic_write()` (`packages/infra/src/ditto_infra/foundation/util/io.py`)

```python
def atomic_write(df: pl.DataFrame, path: Path, fsync: bool = True) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    df.write_parquet(temp_path, compression="zstd")
    if fsync:
        os.fsync(f.fileno())
    temp_path.replace(path)  # OS-level atomic rename
```

**What it provides**:
- No partial/corrupt files on disk (atomic rename)
- fsync for data durability
- `temp_path.replace(path)` is atomic on POSIX and NTFS

**What it does NOT provide**:
- No protection against concurrent read-modify-write cycles
- Two processes can both read `2024.parquet`, merge independently, and overwrite each other

### `FileLockManager` (`packages/infra/src/ditto_infra/foundation/concurrency/filelock.py`)

- Wraps the `filelock` library
- Provides cross-process file-based locks
- Used exclusively by `MarketService` via `self._file_lock.acquire(lock_name, timeout=60.0)`

### `ParquetStore` (`packages/datahub/src/ditto_datahub/stores/base/parquet_store.py`)

- Base class for all Parquet year-partitioned writers
- Uses `atomic_write()` for both `write()` and `delete()` operations
- NO FileLock integration at the store layer
- Vulnerable to read-modify-write race on merge operations

---

## Per-Service Audit Results

### 1. MarketService -- PROTECTED

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/services/market_service.py` |
| FileLock? | **YES** |
| atomic_write? | YES (via ParquetStore) |
| Storage backend | Parquet (year-partitioned) |
| Lock granularity | Per `dataset_year` (e.g., `bars_write_stock_daily_2024`) |
| Timeout | 60s |

**Protected write methods**:
- `save_bars()` -- stock_daily, etf_daily, index_daily, fx_daily, commodity_daily
- `save_adj_factor()` -- adj_factor
- `save_stock_status()` -- stock_status

**Risk**: LOW. FileLock + atomic_write provide full protection.

**Lock naming pattern**:
- Bars: `bars_write_{dataset}_{year}` (e.g., `bars_write_stock_daily_2024`)
- Adj factor: `adj_factor_write_adj_factor_{year}`
- Stock status: `stock_status_write_{year}`

---

### 2. FundamentalService -- NOT APPLICABLE (SQLite)

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/services/fundamental_service.py` |
| FileLock? | No (not needed) |
| atomic_write? | N/A |
| Storage backend | **SQLite** (via SQLiteClient) |

**Write methods**: `save_balance_sheet()`, `save_income_statement()`, `save_cash_flow()`, `save_dividend()`, `save_corporate_actions()`, `save_forecast()`, `save_express()`

**Risk**: LOW. SQLite provides its own concurrency control via database-level locking. All writers use `executemany()` with `ON CONFLICT DO NOTHING` and `commit()`/`rollback()`.

---

### 3. CapitalService -- NOT APPLICABLE (SQLite)

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/services/capital_service.py` |
| FileLock? | No (not needed) |
| atomic_write? | N/A |
| Storage backend | **SQLite** (via SQLiteClient) |

**Write methods**: `save_margin_trading()`, `save_pledge_ratio()`, `save_valuation_metrics()`, `save_index_composition()`

**Risk**: LOW. Same reasoning as FundamentalService -- SQLite handles concurrency.

---

### 4. MetadataService -- NOT APPLICABLE (SQLite)

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/services/metadata_service.py` |
| FileLock? | No (not needed) |
| atomic_write? | N/A |
| Storage backend | **SQLite** (via SQLiteClient) |

**Write methods**: `save_calendar()`, `update_half_days()`, `enrich_calendar()`, `register_instrument()`, `register_instruments_batch()`, `update_list_date()`

All underlying writers (CalendarWriter, InstrumentWriter, UniverseWriter, IndustryWriter, IndustryMappingWriter, NameHistoryWriter) use SQLite.

**Risk**: LOW. SQLite handles concurrency.

---

### 5. FactorWriter -- NOT PROTECTED

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/stores/factors/factor_writer.py` |
| FileLock? | **NO** |
| atomic_write? | YES (via custom _FactorParquetStore) |
| Storage backend | Parquet (`factors/factors_narrow/YYYY.parquet`) |
| Called via service? | No direct service wrapper found |

**Risk**: **HIGH**. Year-partitioned Parquet store. If factor computation runs in parallel for the same year (e.g., different factor families computed concurrently), concurrent writes to the same partition file will cause data loss.

---

### 6. TechnicalIndicatorWriter -- NOT PROTECTED

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/stores/features/technical/technical_indicator_writer.py` |
| FileLock? | **NO** |
| atomic_write? | YES (via custom _TechnicalIndicatorParquetStore) |
| Storage backend | Parquet (`features/technical/indicators_narrow/YYYY.parquet`) |
| Called via service? | No direct service wrapper found |

**Risk**: **HIGH**. Same reasoning as FactorWriter -- year-partitioned Parquet with no FileLock. Technical indicator computation for multiple instruments in the same year could race.

---

### 7. EtfNavWriter -- NOT PROTECTED

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/stores/market/etf/nav/nav_writer.py` |
| FileLock? | **NO** |
| atomic_write? | YES (via ParquetStore) |
| Storage backend | Parquet (`market/etf/nav/YYYY.parquet`) |
| Called via service? | Not through MarketService (MarketService only handles etf_bars, not etf_nav) |

**Risk**: **HIGH**. Year-partitioned Parquet store for ETF NAV data. During batch ingestion, concurrent writes to the same year partition could occur.

---

### 8. EtfStatusWriter -- NOT PROTECTED

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/stores/market/etf/status/status_writer.py` |
| FileLock? | **NO** |
| atomic_write? | YES (via ParquetStore) |
| Storage backend | Parquet (`market/etf/status/YYYY.parquet`) |
| Called via service? | Not through MarketService |

**Risk**: **HIGH**. Year-partitioned Parquet store for ETF status data. Same risk as EtfNavWriter.

---

### 9. EtfAdjFactorWriter -- NOT PROTECTED

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/stores/market/etf/adj/adj_factor_writer.py` |
| FileLock? | **NO** |
| atomic_write? | YES (via ParquetStore) |
| Storage backend | Parquet (`market/etf/adj/YYYY.parquet`) |
| Called via service? | Not through MarketService |

**Risk**: **HIGH**. Year-partitioned Parquet store for ETF adjustment factors.

---

### 10. ResearchArtifactService -- NOT PROTECTED

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/services/research_artifact_service.py` |
| FileLock? | **NO** |
| atomic_write? | **NO** (uses `frame.write_parquet(path)` directly) |
| Storage backend | Parquet (user-controlled paths) |

**Risk**: **MEDIUM**. Direct `write_parquet()` without even atomic_write. However, research artifacts are typically written to unique paths (per derived ID + version), so concurrent collision is unlikely unless users manually target the same path.

---

### 11. DerivedArtifactWriter -- PARTIALLY PROTECTED

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/stores/runtime/derived_artifact_writer.py` |
| FileLock? | **NO** |
| atomic_write? | **PARTIAL** (manual temp-replace in `write_durable_partitions`, none in `write_ephemeral_result`) |
| Storage backend | Parquet (per derived ID + version) |

**Analysis**:
- `write_ephemeral_result()`: Uses `frame.write_parquet()` directly -- no atomicity
- `write_durable_partitions()`: Manual `temp_path.replace(partition_path)` -- has atomic rename but no fsync and no FileLock
- `write_artifact_metadata()`: Uses `path.write_bytes()` -- no atomicity

**Risk**: **MEDIUM**. Paths include run_id and version, making collisions unlikely. However, the lack of atomic_write in ephemeral paths means a crash mid-write could leave a corrupt file.

---

### 12. ComparisonWriter -- NOT PROTECTED

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/stores/runtime/quality/comparison_writer.py` |
| FileLock? | **NO** |
| atomic_write? | **NO** (uses `df.write_parquet(file_path)` directly) |
| Storage backend | Parquet (`quarantine/quality_comparison/year=YYYY/month=MM/{dataset}/{trade_date}.parquet`) |

**Risk**: **MEDIUM**. File paths include trade_date and dataset, so collision is only possible if the same quality check runs in parallel for the same date/dataset. No atomicity -- crash mid-write leaves a corrupt file.

---

### 13. Publication Safety Writers -- LOW RISK

| Writer | File | Backend | atomic_write? |
|--------|------|---------|---------------|
| ManifestWriter | `.../publication_safety/manifest_writer.py` | JSON | Uses `write_json_file()` |
| CertificationWriter | `.../publication_safety/certification_writer.py` | JSON | Unknown |
| ShadowReportWriter | `.../publication_safety/shadow_report_writer.py` | JSON | Unknown |
| MinimalDQWriter | `.../publication_safety/minimal_dq_writer.py` | JSON | Unknown |

**Risk**: LOW. These write to unique paths (per derived ID + version). Concurrent writes to the same path are architecturally prevented.

---

### 14. Index Constituent Writer -- NOT APPLICABLE (SQLite)

| Property | Value |
|----------|-------|
| File: | `packages/datahub/src/ditto_datahub/stores/market/index/constituent/constituent_writer.py` |
| FileLock? | No (not needed) |
| atomic_write? | N/A |
| Storage backend | **SQLite** (`market/index/constituent.db`) |

**Risk**: LOW. SQLite handles concurrency.

---

## Summary Table

| # | Writer / Service | Backend | FileLock | atomic_write | Risk |
|---|------------------|---------|----------|--------------|------|
| 1 | **MarketService.save_bars()** | Parquet | YES | YES | LOW |
| 2 | **MarketService.save_adj_factor()** | Parquet | YES | YES | LOW |
| 3 | **MarketService.save_stock_status()** | Parquet | YES | YES | LOW |
| 4 | FundamentalService | SQLite | N/A | N/A | LOW |
| 5 | CapitalService | SQLite | N/A | N/A | LOW |
| 6 | MetadataService | SQLite | N/A | N/A | LOW |
| 7 | IndexConstituentWriter | SQLite | N/A | N/A | LOW |
| 8 | **FactorWriter** | Parquet | **NO** | YES | **HIGH** |
| 9 | **TechnicalIndicatorWriter** | Parquet | **NO** | YES | **HIGH** |
| 10 | **EtfNavWriter** | Parquet | **NO** | YES | **HIGH** |
| 11 | **EtfStatusWriter** | Parquet | **NO** | YES | **HIGH** |
| 12 | **EtfAdjFactorWriter** | Parquet | **NO** | YES | **HIGH** |
| 13 | ResearchArtifactService | Parquet | NO | **NO** | MEDIUM |
| 14 | DerivedArtifactWriter | Parquet | NO | Partial | MEDIUM |
| 15 | ComparisonWriter | Parquet | NO | **NO** | MEDIUM |
| 16 | Publication safety writers | JSON | NO | Varies | LOW |

---

## Risk Assessment

### The Read-Modify-Write Race Condition

The core vulnerability for all unprotected Parquet writers:

```
Process A: read 2024.parquet (1000 rows)
Process B: read 2024.parquet (1000 rows)        <-- both read same snapshot
Process A: merge + write (1050 rows)            <-- atomic_write succeeds
Process B: merge + write (1030 rows)            <-- atomic_write succeeds, A's 50 new rows lost!
```

`atomic_write()` ensures each individual write is atomic, but the read-modify-write cycle is NOT atomic without a lock.

### Likelihood by Writer

| Writer | Concurrent access scenario | Likelihood |
|--------|---------------------------|------------|
| FactorWriter | Factor computation is parallelizable per year | High during batch factor runs |
| TechnicalIndicatorWriter | Technical indicator computation is parallelizable per year | High during batch runs |
| EtfNavWriter | ETF NAV ingestion could be parallel per year | Medium (depends on scheduler) |
| EtfStatusWriter | ETF status ingestion could be parallel per year | Medium |
| EtfAdjFactorWriter | ETF adj factor ingestion could be parallel per year | Medium |
| ResearchArtifactService | User-driven, paths are unique | Low |
| ComparisonWriter | Quality checks typically sequential per date | Low |
| DerivedArtifactWriter | Run IDs are unique | Low |

---

## Recommendations

### Priority 1 (HIGH): Add FileLock to FactorWriter and TechnicalIndicatorWriter

These are the most likely to experience concurrent writes during batch computation.

**Approach**: Follow the MarketService pattern:
1. Create or extend the calling service to inject `FileLockManager`
2. Acquire lock per `{dataset}_{year}` before calling writer
3. Lock names: `factor_write_factors_narrow_{year}`, `indicator_write_indicators_narrow_{year}`

### Priority 2 (MEDIUM): Add FileLock to ETF writers not covered by MarketService

EtfNavWriter, EtfStatusWriter, and EtfAdjFactorWriter are not routed through MarketService and lack FileLock.

**Approach**: Either:
- (a) Add `save_etf_nav()`, `save_etf_status()`, `save_etf_adj()` methods to MarketService with FileLock, OR
- (b) Create a separate ETF service with FileLock protection

### Priority 3 (LOW): Fix atomic_write gaps

For ResearchArtifactService and ComparisonWriter, replace direct `write_parquet()` calls with `atomic_write()` to at least guarantee no corrupt files on crash.

**No FileLock needed** for these -- their paths are unique enough that concurrent collision is architecturally unlikely.

### Priority 4 (FUTURE): Consider ParquetStore-level FileLock

Currently, FileLock is applied at the service layer (MarketService). This means every new service that wraps a ParquetStore writer must remember to add FileLock.

A more robust long-term approach would be to integrate optional FileLock into `ParquetStore.write()` and `ParquetStore.delete()` methods themselves, controlled by a constructor parameter. This ensures protection is always applied when needed, regardless of the calling service.

---

## Appendix: File Paths Reference

| Component | Absolute Path |
|-----------|---------------|
| atomic_write | `packages/infra/src/ditto_infra/foundation/util/io.py` |
| FileLockManager | `packages/infra/src/ditto_infra/foundation/concurrency/filelock.py` |
| ParquetStore | `packages/datahub/src/ditto_datahub/stores/base/parquet_store.py` |
| MarketService | `packages/datahub/src/ditto_datahub/services/market_service.py` |
| FundamentalService | `packages/datahub/src/ditto_datahub/services/fundamental_service.py` |
| CapitalService | `packages/datahub/src/ditto_datahub/services/capital_service.py` |
| MetadataService | `packages/datahub/src/ditto_datahub/services/metadata_service.py` |
| FactorWriter | `packages/datahub/src/ditto_datahub/stores/factors/factor_writer.py` |
| TechnicalIndicatorWriter | `packages/datahub/src/ditto_datahub/stores/features/technical/technical_indicator_writer.py` |
| EtfNavWriter | `packages/datahub/src/ditto_datahub/stores/market/etf/nav/nav_writer.py` |
| EtfStatusWriter | `packages/datahub/src/ditto_datahub/stores/market/etf/status/status_writer.py` |
| EtfAdjFactorWriter | `packages/datahub/src/ditto_datahub/stores/market/etf/adj/adj_factor_writer.py` |
| ResearchArtifactService | `packages/datahub/src/ditto_datahub/services/research_artifact_service.py` |
| DerivedArtifactWriter | `packages/datahub/src/ditto_datahub/stores/runtime/derived_artifact_writer.py` |
| ComparisonWriter | `packages/datahub/src/ditto_datahub/stores/runtime/quality/comparison_writer.py` |

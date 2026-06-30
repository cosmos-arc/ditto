# Wave 1 Data Readiness Evidence

> Date: 2026-07-01
> Scope: backend data readiness for Wave 1a and full RC1 promotion tracking.

## Command Evidence

- `pixi run -e dev python -m ditto_apps.cli.main ops --help`
  - Result: command exists; available ops commands are `status`, `promotion-review`, `promotion-history`, `promotion-revoke`, `promotion-collect`, `dq`, and `factor-ic`.
  - Note: the final plan mentioned `ops maturity-governance --json`, but that CLI command does not exist in the current codebase. Maturity evidence was collected through `IngestionStatusQueryFacade`, the same facade used by `ops status --json`.
- `pixi run -e dev python -m ditto_apps.cli.main ops status --json`
  - Result: exit 0.
  - Important caveat: local logging is emitted with the command output, so a clean matrix was generated through the same application facade with log handlers removed.
- `pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect <dataset> --output /tmp/ditto-wave1a-promotion/<dataset>.md`
  - Datasets: `calendar`, `etf_basic`, `etf_daily`, `index_basic`, `index_daily`, `fund_adj`, `adj_factor`.
  - Result: all seven commands exited 0 and produced objective Markdown evidence reports.
- `pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py --real-data --require-promoted --output /tmp/ditto-rc1-real-data-report.json`
  - Result: exit 1.
  - Technical command results inside the report: `check`, targeted golden tests, `promotion-collect stock_daily`, real-data E2E tests, and `ops status --json` all exited 0.
  - Business gate result: failed with 72 maturity/promotion/catalog evidence failures.

## V1a Dataset Matrix

| Dataset | Maturity | Promotion Status | Latest Status | Catalog Evidence | V1a Status |
|---|---|---|---|---|---|
| `calendar` | `initial-focus` | `not_applicable` | `success` on `2025-01-01` | missing storage URI, schema hash, row count, freshness | blocked |
| `etf_basic` | `initial-focus` | `not_applicable` | none | missing storage URI, schema hash, row count, freshness | blocked |
| `etf_daily` | `initial-focus` | `not_applicable` | `success` on `2025-01-02` | missing storage URI, schema hash, row count, freshness | blocked |
| `index_basic` | `initial-focus` | `not_applicable` | none | missing storage URI, schema hash, row count, freshness | blocked |
| `index_daily` | `initial-focus` | `not_applicable` | `success` on `2025-01-02` | missing storage URI, schema hash, row count, freshness | blocked |
| `fund_adj` | `initial-focus` | `not_applicable` | `success` on `2025-01-01` | missing storage URI, schema hash, row count, freshness | blocked |
| `adj_factor` | `initial-focus` | `not_applicable` | `success` on `2025-01-02` | missing storage URI, schema hash, row count, freshness | review-blocked |

`adj_factor` is included conservatively because shared market and adjustment paths still reference it. It can be demoted from V1a if the selected ETF workflow proves it only needs `fund_adj`.

## Runtime Store Readiness

Trade intent, fill, and position stores are not ingestion catalog datasets, so promotion review is not applicable. Their V1a readiness will be verified through backend trade query/API tests and the Daily Decision report contract.

## Full RC1 Status

Full RC1 required datasets are defined by `scripts/acceptance/rc1_requirements.py`:

`stock_basic`, `stock_daily`, `stock_status`, `balance_sheet`, `income_statement`, `cash_flow`, `valuation_metrics`, `etf_basic`, `etf_daily`, `index_basic`, `index_daily`, `adj_factor`, `fund_adj`, `macro_indicators`.

Current validation result: blocked.

Main blocker classes:

- Experimental datasets still have `dataset_promotion_status=blocked`: `stock_basic`, `stock_daily`, `stock_status`, `balance_sheet`, `income_statement`, `cash_flow`, `valuation_metrics`, `macro_indicators`.
- All 14 RC1 datasets are missing catalog storage URI, schema hash, catalog row count, or freshness evidence in this local environment.
- Some datasets also have failed latest ingestion status, including `stock_daily` and `cash_flow`.

No promotion evidence was marked passed and no maturity override was written, because the collected evidence does not satisfy the launch criteria.

RC1 acceptance report path for this run: `/tmp/ditto-rc1-real-data-report.json`.

## Required Next Actions

1. Run real ingestion/backfill for the V1a ETF dataset set on the target data root.
2. Ensure catalog write-path evidence exists: storage URI, schema hash, row count, freshness timestamp/status.
3. Re-run `ops status --json` and `promotion-collect` for V1a datasets.
4. For Wave 1c RC1, promote experimental stock/fundamental/macro datasets only through `ditto ops promotion-review` after reviewer evidence exists for all criteria.

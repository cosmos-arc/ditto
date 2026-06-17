# RC-1 Release Checklist

## Scope

- Daily A-share stocks, ETFs, and macro data.
- Research and backtest production readiness.
- Manual trading signals only.
- No real broker live trading.

## Required Evidence

- `pixi run -e dev check` passes.
- ETF golden E2E passes.
- Stock-selection golden E2E passes.
- Stock-selection signal package E2E passes.
- Real-data E2E passes in the release acceptance environment.
- Promotion evidence exists for `stock_basic`, `stock_daily`, `balance_sheet`, `income_statement`, `valuation_metrics`, ETF/index daily data, industry mapping, and required macro indicators.
- `strategy publish-signals` creates persisted `TradeIntent` records readable from `/trade/signals/latest`.
- Manual fill recording recomputes positions and deviation report.

## Release Command

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py --real-data --require-promoted --output artifacts/acceptance/rc1-report.json
```

## Latest Evidence

- Report: `artifacts/acceptance/rc1-report.json`
- Generated at: `2026-06-17T11:55:03Z`
- Status: `"passed": true`

## Go Criteria

- The release command exits with code 0.
- The generated acceptance report has `"passed": true`.
- Dataset maturity gates do not require `--allow-experimental-data` for RC-1 production runs.
- The only allowed xfail is the documented cross-section expression limitation.

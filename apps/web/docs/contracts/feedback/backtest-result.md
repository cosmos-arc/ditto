# Backtest result implementation feedback

- React route: `/research/backtests/$id`
- Contract verification: 2026-08-30
- The workbench consumes the generated run, report, NAV, benchmark, trades, and audit resources independently. It adds no result aggregator, BFF, persistence table, or client-side performance recomputation.
- Run identity is fail-closed: when the run resource is unavailable, performance, NAV, trades, and audit evidence are withheld. Partial resource failures remain local and have typed retry actions.
- Missing report statistics are shown as `未评估`, and missing benchmark data is shown as `未发布`; neither is converted to zero. Instrument names, holdings, monthly returns, and comparison series are not inferred when absent from the public contracts.
- The prototype's KPI hierarchy informed the frozen result strip, while the live implementation keeps exact run, strategy version, and report period visible across all four evidence tabs.
- Prototype-only export, enable-signal, inline AI interpretation, and compare overlays are intentionally not implemented because the current backend exposes no governed API for those actions. The header instead links to the existing governed Agent evidence entry with exact run context.

# Backtest catalog implementation feedback

- React route: `/research/backtests`
- Contract verification: 2026-08-30
- The retired static rows were replaced by the generated `/backtests/runs` query and a local DTO-to-view-model adapter.
- Search, status filtering, selection, progress, benchmark publication, and the detail rail all use the same live run summary.
- A missing benchmark is shown as `未发布`; it is never converted to zero or treated as a successful comparison.
- The catalog does not fetch or infer report, NAV, trade, or replay evidence. Those remain scoped to the exact run workbench.
- The prototype compare drawer is intentionally not implemented because no governed compare contract exists in the current backend API.

# Strategy Studio implementation feedback

- React route: `/research/strategies/$id/studio`
- Contract verification: 2026-08-29
- Live identity: strategy id, base version, lifecycle, spec hash, and candidate canonical hash are sourced from strategy APIs.
- Save semantics: a current server validation is required before an idempotent append-only draft version save.
- Dry Run and backtest: both are planning handoffs. The UI does not claim execution until snapshot, dates, and registry hash are fixed by Experiment preflight.
- Factor preview: expressions and weights come from the live working spec; an unavailable materialized distribution is shown as `未评估`.
- Governance: deprecation records actor and reason and retains version history.

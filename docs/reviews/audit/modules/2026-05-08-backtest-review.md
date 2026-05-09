# Backtest Review Report

> Date: 2026-05-08
> Scope: `packages/backtest`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Backtest 是回测引擎、模拟撮合、绩效统计和 replay manifest 包。允许依赖 kernel/data/strategy/portfolio/risk/execution，当前没有发现 production 代码依赖 features/analysis/application/apps/platform。

回测能力是当前最完整的 runtime path：有 `EngineLoop`、step chain、模拟 brokerage、manifest、replay validator、统计报告和较多测试。主要缺口不是“不能跑”，而是 backtest/paper 共享 seam、OMS journal、risk/account state 恢复还没有一条统一 runtime spine。

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 31 Python source files, 40 test files, about 4,686 source LOC. |
| Largest files | `statistics.py` 627, `engine.py` 518, `manifest.py` 421, `brokerage.py` 419, `replay.py` 322. |
| Engine chain | `DataFetchStep -> RiskScanStep -> StrategyStep -> PlanningStep -> PreTradeStep -> ExecutionStep -> AuditStep`. |
| Data access | `ProviderBackedDataFeed` consumes data-owned `DataProvider`/`BarQuery`, lazy-loads a Polars frame, and filters slices in memory. |
| Runtime state | `EngineLoop` owns fills, orders, strategy context, signal queue, rule refs, bar fingerprints, and trade builder state. |
| Replay | `RunManifest` captures input refs, rule refs, hashes, config hash, seed, and artifacts; `ReplayValidator` compares manifest and NAV series. |
| Simulation | `BacktestBrokerage` owns simulated pending orders, fills, T+1 settlement/freeze behavior, and account mutation. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| BACKTEST-P1-01 | P1 | Runtime step chain is backtest-owned and in-memory; paper/live seam is not first-class. | Paper runtime may copy the backtest loop or diverge in order/risk/fill sequencing. | Extract/document a shared backtest/paper runtime seam for data slice, strategy decision, risk, planning, brokerage/gateway, fills, and audit. |
| BACKTEST-P1-02 | P1 | `ProviderBackedDataFeed` directly imports data-owned `DataProvider` and `BarQuery`. | Consumers depend on a data-layer provider instead of a backtest-owned historical portal contract. | Introduce a backtest-owned `HistoricalDataPortal`/`DataFeed` contract and adapt data providers at application boundary. |
| BACKTEST-P1-03 | P1 | Replay compares manifest/NAV, but not OMS journal, risk state snapshots, account restore, or fill idempotency. | Deterministic NAV can hide state-recovery defects before paper/live. | Extend replay proof after OMS Lite to include order journal, fills, risk state, and account state projections. |
| BACKTEST-P2-01 | P2 | `statistics.py`, `engine.py`, `manifest.py`, `brokerage.py`, and `data_feed.py` are large mixed-concern files. | New runtime modes and reporting variants will raise regression cost. | Decompose by runtime, simulation, manifest, and reporting under behavior-preserving tests. |
| BACKTEST-P2-02 | P2 | `RunMode` includes live-like vocabulary while live adapters are reserved. | Public artifacts may imply live readiness that does not exist. | Keep manifest mode language tied to maturity manifest; live mode remains reserved until gateway/OMS/reconciliation pass. |

No P0 finding was confirmed. The backtest path is usable, but not sufficient proof for paper/live readiness.

## 4. TDD 整改计划

1. Runtime seam:
   - RED: add contract test that a backtest runtime and paper runtime use the same ordered decision/risk/order/fill lifecycle.
   - GREEN: extract a narrow lifecycle interface or orchestrator around existing steps.
   - REFACTOR: keep simulation behavior in backtest and adapter behavior in execution.

2. Historical data portal:
   - RED: prove backtest can run against a backtest-owned data portal Protocol without importing data provider types in core loop.
   - GREEN: add adapter from `ditto_data.provider.DataProvider` at application boundary.
   - REFACTOR: move PIT/time context into portal query once `TimeContext` is decided.

3. Replay expansion:
   - RED: replay a run and assert same journal/fill/risk/account projections.
   - GREEN: add additional artifact comparison after OMS/risk snapshot exists.
   - REFACTOR: use a single manifest input-ref model with DataCatalog when ready.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-backtest-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/backtest/tests && pixi run -e dev arch-check && pixi run -e dev check`.

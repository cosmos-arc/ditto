# Ditto Capability Maturity Manifest

> Date: 2026-05-25
> Status: V2 evaluation synced
> Purpose: prevent global-market roadmap language from being mistaken for current production readiness.

## Maturity Levels

| Level | Meaning |
|---|---|
| production | Current user-facing capability with repeatable tests, operational path, and no known architectural blocker. |
| initial-focus | Primary near-term scope with meaningful implementation and tests, but still under architecture review. |
| experimental | Implemented or partly implemented capability that is useful for research or future direction, not yet current production scope. |
| infrastructure | Foundation capability that supports product work but is not itself a product feature. |
| reserved | Placeholder or planned namespace; must not be treated as runtime behavior. |
| historical-compat | Existing compatibility surface kept to avoid churn while a migration is planned. |

## Product Scope

| Capability Area | Maturity | Evidence / Boundary | Next Review |
|---|---|---|---|
| A-share ETF daily data, research, and backtest workflow | initial-focus | Current architecture and tests target daily A-share ETF paths; Apps review confirms E2E still has fixture skips and needs one committed synthetic golden lane. | Golden E2E remediation. |
| A-share stock/index metadata and market data | experimental | Data services/storage and strategy templates exist, but Data review confirms Dataset enum/config remain the routing spine and template maturity is mixed. | Dataset/DataCatalog remediation. |
| Fundamental/capital data | experimental | PIT schemas and APIs exist; Data/Application/Apps reviews did not confirm production readiness. | PIT/time semantics review. |
| Macro data | experimental | Macro source/category support exists; current review plan treats global macro as future expansion and API presence must not imply production maturity. | Maturity-aware API docs. |
| FX/commodity data | experimental | APIs/storage/query surfaces exist; not current initial-focus production scope. | Maturity-aware API docs. |
| Feature/factor materialization | initial-focus | Expression/materialization/publication safety are implemented; Features review confirms DataCatalog provenance and shared time semantics remain open. | Features provenance/time remediation. |
| Strategy alpha templates | initial-focus for A-share ETF, experimental for broader templates | Strategy review confirms package isolation and ETF template maturity; stock/sector templates remain experimental until explicitly promoted. ETF templates: `etf_rotation`, `etf_trend_swing` = initial-focus. Stock templates: `stock_selection_trend` = experimental (has unit tests), `stock_sector_rotation` = experimental (has snapshot integration tests). | Stage schema/template maturity remediation. |
| Portfolio accounting/rebalancing | experimental | Core accounting/rebalancing models exist; Portfolio review confirms positions/holdings/target portfolio runtime/store and event publication are incomplete. | Portfolio state projection remediation. |
| Risk checks | experimental | Pre/post checks exist; Risk review confirms continuous risk gate, typed audit payloads, and state recovery are incomplete. | Risk gate/state remediation. |
| Backtest engine | initial-focus | Engine loop and simulation exist; Backtest review confirms shared paper seam and replay recovery beyond NAV are open. | Backtest/paper seam remediation. |
| Execution OMS FSM | initial-focus | OMS Lite 完整实现：7 状态（NEW/SUBMITTED/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED/INVALID）+ 5 触发器 FSM + OrderBook + OrderTicket + 双 ID（ClientOrderId / BrokerOrderId）。 | Execution remediation — durable journal, conformance tests. |
| PaperBrokerGateway | experimental | Paper 撮合网关完整行为矩阵：submit/fill/cancel/reject/partial fill + last_prices 注入解决 fill_price=0.0 + RiskGate 集成 + 18 conformance tests。 | Live adapter seam + conformance test expansion. |
| ExecutionReconciler | experimental | reconcile() 纯函数，5 种 MismatchType。ReconciliationDiff 含 client_order_id/broker_order_id 可追溯 journal event。 | Reconciliation persistence. |
| OrderEventJournal | experimental | Protocol + InMemoryOrderEventJournal + SqliteOrderEventJournal（append-only 持久化，重启不丢失）。append/events_for/all_events API 完整。 | Multi-journal orchestration. |
| Paper trading runtime | experimental | PaperBrokerGateway 完整行为矩阵 + PaperRuntimeKernel（RealtimeClock + SimpleEventBus）实现 TradingRuntimeKernel Protocol。 | Live adapter seam. |
| Live trading adapters | reserved | BrokerGateway has no production adapter; do not treat live trading as available. | Execution remediation after OMS Lite. |
| Research dataset control-plane | initial-focus | Analysis services/storage exist, but Analysis/Application reviews confirm application-owned research ports and late-arrival policy honesty remain open. | Research port/policy remediation. |
| Analysis experiments | reserved | Package docs and guards mark this namespace as reserved/future and `__all__=[]`; no runtime API exists. Reserved list: `ditto_analysis.experiments`. | Reserved namespace guard source-of-truth remediation. |
| Analysis SHIFT_TO_NEXT_SNAPSHOT late-arrival policy | reserved | Enum member exists but has no implementation; warns and returns frame unchanged. Must not be relied upon until promoted. | Late-arrival policy implementation. |
| Platform config/observability/storage foundations | infrastructure | Platform is business-agnostic and guarded; Platform review found one P1 SQL helper validation gap and P2 storage/API polish items. | Platform SQL remediation. |
| DataCatalog runtime | experimental | InMemoryDataCatalog + DatasetMetadata 已实现（contracts 有 runtime 落地）。Lineage 仍为 contract-only。 | DataCatalog lineage remediation. |
| Runtime event/time/state/OMS spine | experimental | All W1 runtime reviews confirm EventBus/Clock exist. Typed events (B4), risk state snapshot/restore (B5), portfolio state projection (B5) are complete. TimeContext integration, OMS Lite remain incomplete. | Runtime spine remediation. |

## Guard Rules

- Reserved namespaces must be listed in this manifest before they can appear in package docs or public API.
- New market, asset, strategy template, broker, or analysis namespace must declare one maturity level.
- Public docs and API text must not describe `experimental`, `infrastructure`, or `reserved` capabilities as production-ready.
- Tests or architecture smell checks should eventually parse this file or a YAML derivative as an enforcement source.

### Reserved Namespaces (enforcement source of truth)

These namespaces exist as placeholder packages (`__all__ = []`) and must not be treated as runtime behavior:

| Namespace | Package | Since |
|-----------|---------|-------|
| `ditto_analysis.experiments` | analysis | 2026-05-08 |

### Reserved API Surface

| Surface | Package | Since | Notes |
|---------|---------|-------|-------|
| `LateArrivalPolicy.SHIFT_TO_NEXT_SNAPSHOT` | analysis | 2026-05-09 | Enum member exists, warns on use, no shift semantics |
| `DataCatalogReader` / `DataCatalogWriter` | data | 2026-05-09 | Protocol contracts + InMemoryDataCatalog runtime implementation |
| `BrokerGateway` (production adapters) | execution | 2026-05-08 | No production adapter exists; PaperBrokerGateway is experimental |

### API Route Maturity (enforcement source of truth)

| Route Prefix | Maturity | Module |
|-------------|----------|--------|
| `/backtests` | initial-focus | `api/routes/backtest.py` |
| `/market` | initial-focus | `api/routes/market.py` |
| `/metadata` | initial-focus | `api/routes/metadata.py` |
| `/strategies` | initial-focus | `api/routes/strategy.py` |
| `/universes` | initial-focus | `api/routes/universe.py` |
| `/capital` | experimental | `api/routes/capital.py` |
| `/commodity` | experimental | `api/routes/commodity.py` |
| `/fundamental` | experimental | `api/routes/fundamental.py` |
| `/fx` | experimental | `api/routes/fx.py` |
| `/macro` | experimental | `api/routes/macro.py` |
| `/trade` | experimental | `api/routes/trade.py` |
| `/ingestion` | infrastructure | `api/routes/ingestion.py` |
| `/source` | infrastructure | `api/routes/source.py` |
| `/api/v1` | debug | `api/routes/debug.py` |

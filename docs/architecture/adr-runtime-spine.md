# Runtime Spine ADR Draft

Status: Proposed

Date: 2026-05-08

Related review: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## Context

Ditto has strong package boundaries, but runtime semantics are still thin. Current evidence:

- `ditto_kernel.events.DomainEvent` is a string event name plus `dict[str, Any]` payload.
- Production `EventBus` usage is concentrated in backtest steps; subscriptions are mostly test-side.
- `ditto_kernel.clock.Clock` provides `now/today/advance_to`, but there is no shared `TimeContext`.
- PIT terms such as `knowledge_date`, `availability_time`, `as_of_date`, and `effective_from/to` are implemented locally across data, features, backtest, application, and apps.
- Execution has order/fill/broker abstractions, but OMS Lite identity, journal, idempotency, reconciliation, and paper gateway are not yet first-class.
- Execution review confirmed the adapter split is good (`Brokerage` vs `BrokerGateway`), but `broker/gateways` remains placeholder-only and reconciliation is still summary-only.
- Portfolio review confirmed account accounting is useful, but portfolio state cannot yet be rebuilt from a durable execution journal and `PositionChanged` remains reserved.
- Risk review confirmed pre/post checks are useful, but continuous risk gate, typed risk decision payloads, and state snapshot/replay remain open.
- Backtest review confirmed the current engine loop is the strongest runtime path, but backtest/paper shared seam and replay proof beyond NAV remain open.

The next architecture step needs a small runtime spine that supports backtest and paper trading without overbuilding a distributed event platform.

## Decision

### 1. Keep kernel thin, but give runtime concepts explicit ownership

`kernel` may contain only the minimum cross-plane runtime language:

- `Clock` / `SimulatedClock` / `RealtimeClock`
- `EventBus` as a synchronous in-process dispatch Protocol
- a future `TimeContext` value object if at least two core planes consume it directly

Domain-specific runtime records stay with their owning packages. For example, order state and broker reconciliation belong to `execution`; risk decisions belong to `risk`; portfolio state snapshots belong to `portfolio`.

### 2. Typed events are owned by domains; kernel provides transport

The current `DomainEvent` remains a compatibility transport while W1 is in progress. New runtime events should be typed dataclasses or value objects owned by the domain package that defines the business meaning.

An event-name catalog should map typed events to stable names such as `order.submitted`, `order.filled`, `risk.rejected`, and `portfolio.position_changed`. This catalog may start as documentation and tests before code generation or registry work.

### 3. TimeContext is a shared runtime query context, not a row-version model

`TimeContext` should represent the runtime/query perspective:

- trade date or bar time
- knowledge/as-of cutoff
- processing timestamp
- optional availability cutoff

`effective_from` / `effective_to` remain catalog/reference row version fields. They can be evaluated against `TimeContext`, but they are not the same concept.

### 4. OMS Lite starts in execution

`ClientOrderId`, `BrokerOrderId`, `OrderState`, `OrderJournal`, `FillEvent`, and `ReconciliationRecord` should be designed in `execution` first. They move to `kernel` only if portfolio or risk must directly depend on them and no narrower consumer-owned port is sufficient.

Backtest may depend on execution and can reuse the OMS Lite semantics. Risk and portfolio should receive narrow views or events rather than importing execution internals.

### 5. Backtest/Paper share a seam before Live

W1 should define a shared in-process seam for:

- data slice / portal
- strategy decision
- order planning
- risk gate
- brokerage or gateway interaction
- fill application
- journal/audit output

This seam must serve backtest and paper first. Live trading remains reserved until OMS Lite, reconciliation, idempotency, and recovery are proven.

## Consequences

- **Positive**: Runtime semantics become reviewable and replayable without introducing a heavy message broker.
- **Positive**: Backtest and paper can converge on order/risk/fill language before live adapters exist.
- **Positive**: PIT semantics get one shared context instead of many local date conventions.
- **Negative**: Some existing kernel types, especially `trading.py`, will remain transitional until reference/domain ownership is settled.
- **Negative**: Domain event ownership requires more explicit tests and naming discipline than a single generic event payload.

## Alternatives Considered

### Put all runtime types in kernel

Rejected for now. It would keep imports easy but would turn kernel into a runtime domain package and invite market/order/risk business logic into the lowest layer.

### Create a new runtime package immediately

Deferred. A new package may become useful later, but current evidence can be handled with kernel transport plus domain-owned typed records and application/backtest composition.

### Keep string events indefinitely

Rejected. String events are acceptable as a transition, but they are not enough for replay, audit, schema evolution, or cross-runtime correctness.

## Review Checkpoints

- Kernel review accepted thin kernel transport, candidate `TimeContext`, and domain-owned typed events as the direction.
- Execution review accepted OMS Lite identity, state machine, journal, gateway harness, and reconciliation as W1 remediation work.
- Portfolio review accepted state snapshot/rebuild boundaries as dependent on execution journal/fill projection.
- Risk review accepted continuous risk gate, typed risk decision payloads, and state replay as required runtime work.
- Backtest review accepted the shared backtest/paper seam and deterministic replay proof beyond NAV as required runtime work.

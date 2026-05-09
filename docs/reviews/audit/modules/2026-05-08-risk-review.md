# Risk Review Report

> Date: 2026-05-08
> Scope: `packages/risk`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Risk 是风控检查、约束和暴露度包。生产代码符合依赖规则：只依赖 `kernel` 和 `portfolio`，不依赖 data/features/strategy/execution/backtest/application/apps/platform。

现有实现把正常风控拒绝建模为返回值而不是异常，这一点健康。主要缺口是“连续风控 gate”还不是一个可恢复、可审计、跨 backtest/paper 共用的 runtime 契约；状态型风控也缺少 snapshot/replay 语言。

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 18 Python source files, 22 test files, about 1,372 source LOC. |
| Largest files | `constraints/checks.py` 319, `constraints/context.py` 191, `drawdown/rules.py` 174, `post_trade.py` 169. |
| Pre-trade | `PreTradeContext` carries account view, market snapshots, buying-power model, fee model, rules, and pending tickets. |
| Normal decisions | `PreTradeRiskCheck` returns `OrderCheckResult` and `Decision`; it does not throw for normal rejection. |
| Post-trade | `CompositePostTradeGuard.scan/reset` aggregates `RiskAction` from guard rules. |
| Stateful risk | `MaxDrawdownRule` stores `_peak_nav`; strategy risk locks/cooldowns live in `StrategyContext` and are driven by backtest steps. |
| Events | `RiskGuardTriggered` is a typed domain event class, but still includes `details: dict[str, Any]`. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| RISK-P1-01 | P1 | Pre-trade and post-trade APIs exist, but the executable gate is embedded by `backtest` steps and application wiring rather than a shared runtime contract. | Paper runtime could bypass or duplicate risk sequencing. | Define a first-class `RiskGate`/decision event contract used by backtest and paper before live. |
| RISK-P1-02 | P1 | `MaxDrawdownRule` keeps `_peak_nav`; strategy locks/cooldowns are in `StrategyContext`; neither has a durable snapshot/replay contract. | Restart/replay may produce different risk state and unlock behavior. | Add risk-state snapshot and restore tests for stateful rules and instrument locks. |
| RISK-P1-03 | P1 | `RiskGuardTriggered` has `details: dict[str, Any]`; audit records are shaped elsewhere. | Risk event payloads can drift across packages and audit output. | Introduce typed risk decision/audit payloads and map them to kernel event-name catalog. |
| RISK-P2-01 | P2 | `RiskAction` becomes backtest `RiskScanRecord`, then execution audit payloads by local mapping. | Audit lineage is split and harder to compare across runtime modes. | Publish one stable risk record catalog for pre-trade decision, post-trade action, and audit projection. |

No P0 finding was confirmed. Risk has useful primitives; it needs runtime spine integration before being treated as paper/live complete.

## 4. TDD 整改计划

1. Continuous gate:
   - RED: one shared contract test proving order submission passes through pre-trade and post-trade risk in a fixed order.
   - GREEN: add a narrow `RiskGate` facade over existing checks/guards.
   - REFACTOR: let backtest steps and paper flow call the same facade.

2. Stateful recovery:
   - RED: replay a NAV series with a restored drawdown rule and prove the same `RiskAction` sequence.
   - GREEN: add state snapshot/restore to stateful guards.
   - REFACTOR: separate transient scan input from durable state.

3. Typed audit:
   - RED: assert risk event payload schema and audit record schema are stable.
   - GREEN: replace generic `details` usage at publish boundaries.
   - REFACTOR: integrate with runtime event catalog after kernel event work.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-risk-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/risk/tests && pixi run -e dev arch-check && pixi run -e dev check`.

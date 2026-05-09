# Strategy Review Report

> Date: 2026-05-08
> Scope: `packages/strategy`
> Source plan: `docs/reviews/audit/2026-05-08-global-and-module-review-plan.md`

## 1. 当前职责与边界

Strategy owns strategy definitions, alpha pipeline, stage contracts, templates, signal contracts, and strategy storage. Production code respects the hard boundary: no data/features/portfolio/risk/execution/backtest/analysis/application/apps imports in package source. Integration tests intentionally compose those packages.

The pipeline model is healthy and well tested. The main gap is that stage contracts are still column-convention based rather than self-described schema contracts, and template maturity spans from initial-focus ETF paths to broader stock/sector experimental paths.

## 2. 源码证据

| Area | Evidence |
|---|---|
| Size | 48 Python source files, 29 test files, about 5,321 source LOC. |
| Largest files | `stock_sector_rotation.py` 640, `regime.py` 528, `strategy_run_store.py` 406, `stock_selection_trend.py` 343, `specs.py` 309. |
| Stage contract | `DecisionStage.process(frame, context) -> frame`; `DecisionFrame` is a Polars DataFrame alias. |
| Schema guard | `FrameCol` constants and `validate_frame(frame, required)` guard required columns, but stages do not declare `requires/produces`. |
| Runtime context | `StrategyContext` owns risk locks/cooldowns and positions, with no snapshot contract. |
| Target output | Strategy defines its own `TargetPortfolio`, distinct from portfolio `TargetPortfolio` store DTO. |
| Tests | Unit tests cover stages/templates/frame validation; integration tests compose data/execution/portfolio/risk under tests only. |

## 3. 发现列表

| ID | 严重度 | 证据 | 风险 | 建议 |
|---|---|---|---|---|
| STRAT-P1-01 | P1 | `DecisionStage` does not declare required/produced columns; schema checks are local `validate_frame` calls. | Pipeline changes can break downstream stages without a machine-readable stage contract. | Add optional stage metadata (`requires`, `produces`, maturity) and pipeline contract tests. |
| STRAT-P1-02 | P1 | `StrategyContext` stores risk locks/cooldowns and positions across dates, but has no durable snapshot/replay contract. | Backtest replay or paper restart can diverge on locked instruments or trailing context. | Define context snapshot/restore or move stateful risk locks into the shared risk/runtime state model. |
| STRAT-P1-03 | P1 | ETF, stock selection, and stock sector templates share package surface, but maturity differs. | Broader stock/global strategy capability may be mistaken for current initial-focus support. | Mark ETF templates initial-focus and broader stock/sector templates experimental in maturity docs/public API. |
| STRAT-P2-01 | P2 | Strategy `TargetPortfolio` name overlaps with portfolio target portfolio DTO/store. | Ownership ambiguity during application wiring and docs work. | Rename in docs/glossary as strategy target weights vs portfolio target store, or qualify public API names. |
| STRAT-P2-02 | P2 | Largest template/stage files exceed 500 LOC and combine domain logic, config, and stage implementations. | New templates can become harder to audit. | Split template config, stages, and builder functions under existing tests. |

No P0 finding was confirmed. Strategy source is well isolated; maturity and stage-schema hardening are the main work.

## 4. TDD 整改计划

1. Stage schema:
   - RED: add tests proving a pipeline can validate all stage `requires/produces` before running.
   - GREEN: add metadata to built-in stages without changing `process`.
   - REFACTOR: generate docs from the stage contract.

2. Context recovery:
   - RED: run a multi-day strategy with locks, snapshot context mid-run, restore, and assert same target output.
   - GREEN: add snapshot DTO or move locks behind risk-owned state.
   - REFACTOR: connect to runtime replay after backtest/risk work.

3. Template maturity:
   - RED: add public API or maturity tests that broad templates are not marked production.
   - GREEN: update docs/manifests.
   - REFACTOR: split large templates after current snapshots are preserved.

## 5. 验收建议

Review artifact validation: `awk 'BEGIN{f=0} /^```/{f++} END{if (f % 2 != 0) exit 1}' docs/reviews/audit/modules/2026-05-08-strategy-review.md`

Remediation validation: `pixi run -e dev pytest -v --import-mode=importlib -m 'not snapshot' -n auto --no-cov packages/strategy/tests && pixi run -e dev arch-check && pixi run -e dev check`.


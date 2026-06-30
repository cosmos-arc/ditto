# Ditto System Positioning Assessment Design

> Date: 2026-06-24
> Status: Draft for user review
> Scope: Source-level assessment design for Ditto's long-term full-stack quant platform positioning, current usable version boundary, industry gap, engineering gap, and AI/Agent-native gap.

## 1. Purpose

This assessment answers one strategic question:

**What kind of top-tier personal quant platform should Ditto become, and what is the current usable version boundary supported by the source code today?**

The report is not a generic feature inventory. It is intended to reduce target drift after many iterations. It should separate:

- Capabilities that are implemented and usable now.
- Capabilities that exist as backend primitives but do not yet form a user-facing workflow.
- Capabilities that are valuable for a long-term full-stack platform but should not drive the next phase.
- Capabilities that are overbuilt relative to current product value.
- Capabilities that are missing compared with leading quant and AI-agent systems.

## 2. Confirmed User Intent

The user wants Ditto to remain a **long-term full-stack quant platform**, not a small single-purpose tool.

The near-term need is to make stage boundaries explicit:

- Current usable version boundary.
- Next phase target.
- Long-term platform direction.
- Engineering and architecture constraints required to keep the long-term platform clean.
- Functional and AI/Agent gaps compared with leading systems.

The report should prioritize target clarity over another round of broad ambition expansion.

## 3. Non-Goals

This assessment will not treat the following as current release blockers:

- Live broker production integration.
- Intraday or high-frequency trading.
- Multi-asset expansion outside A-share stocks, ETFs, indexes, and macro indicators.
- Fully automated unsupervised trading.
- Frontend implementation in this backend repository.

These remain long-term platform concerns and will be placed in the correct stage rather than used to invalidate the current phase.

## 4. Positioning Model

Ditto will be assessed as a staged full-stack platform:

### L0 Engineering And Architecture Foundation

Core question: can the codebase sustain a long-term full-stack platform?

Covered areas:

- 12-package architecture and dependency boundaries.
- Type safety, linting, import-linter, architecture smell checks.
- Test scale and CI gates.
- Data catalog, maturity, promotion, lineage, PIT, reproducibility.
- API, CLI, jobs, storage, configuration, observability, and security posture.

### L1 Daily Research And Backtesting System

Core question: can a user reliably research and validate daily ETF, stock, and macro strategies?

Covered areas:

- Data ingestion and query readiness.
- Factor expression engine and factor evaluation.
- IC diagnostics, regime-aware evaluation, attribution utilities.
- Strategy templates and factor bridge.
- Backtest engine, replay, reports, deterministic evidence.
- Dataset maturity and research opt-in boundaries.

### L2 Portfolio And Signal Decision System

Core question: can Ditto turn research into daily actionable decisions?

Covered areas:

- Ranked stock or ETF candidates.
- Target weights and constraints.
- Portfolio construction and rebalancing.
- Risk checks and launch risk report.
- Signal packages, selection reasons, factor contributors, and manual trade intent reads.
- Human-readable decision evidence.

### L3 Semi-Automated Trading Operations Loop

Core question: can Ditto support real account operation with human control?

Covered areas:

- Paper trading maturity.
- Manual fill recording.
- Actual position and P&L reconstruction.
- Signal-vs-fill deviation reports.
- Execution audit, reconciliation, repair workflows.
- Alerts, data freshness operations, incident handling, and recovery evidence.

### L4 Long-Term Full-Stack Live Platform

Core question: what remains before Ditto resembles top full-stack systems?

Covered areas:

- Live broker gateways.
- Unified backtest/live trading model.
- Real-time event engine and streaming market data.
- Order lifecycle depth, advanced order types, execution algorithms.
- Continuous risk gate, multi-strategy, multi-account, permissions, disaster recovery, and production audit.

## 5. AI/Agent-Native Layer

AI/Agent capability is a cross-cutting layer, not an appendix. The report will evaluate how well Ditto can become an AI-native quant platform.

### Agent Roles To Assess

- **Engineering Agent:** understands code, diagnoses CI and architecture failures, proposes fixes, and verifies changes.
- **Research Agent:** generates hypotheses, queries datasets, evaluates factors, runs backtests, and explains results.
- **Decision Agent:** explains candidate selection, target weights, exposures, and trade reasons.
- **Operations Agent:** monitors data freshness, promotion gaps, signal deviations, fill issues, and remediation backlog.
- **Live Trading Agent:** long-term human-supervised assistant for risk explanation and exception handling, not unsupervised order placement.

### AI/Agent Dimensions

- Tool protocol readiness: whether Ditto exposes stable tool/API surfaces that agents can call.
- Structured context readiness: whether catalog, lineage, artifacts, reports, signal packages, audit logs, and errors are machine-readable.
- Closed-loop workflows: whether an agent can move from hypothesis to experiment to report to strategy candidate to human approval.
- Evidence grounding: whether agent outputs can cite code, datasets, run artifacts, tests, or reports.
- Safety controls: whether human approval, promotion gates, risk gates, and audit logs prevent unsafe autonomous actions.
- AI-specific product value: whether an agent would make Ditto more usable daily, rather than merely wrapping existing CLI commands.

### AI/Agent Benchmarks

The assessment will compare Ditto with current leading or representative systems:

- QuantConnect AI assistance and MCP-style workflow surfaces.
- Microsoft Qlib plus RD-Agent for automated quant R&D.
- OpenBB Copilot and OpenBB data platform patterns.
- TradingAgents-style multi-agent financial research frameworks.
- General coding/research agents only as engineering-productivity references, not as quant-domain maturity references.

## 6. Scoring Dimensions

Each stage will be scored on six dimensions:

- **Source implementation:** real code exists, not only docs or placeholders.
- **Workflow closure:** input-to-output path is runnable and meaningful.
- **Production trust:** PIT, maturity gates, promotion, CI, failure handling, and audit evidence are sufficient for the stage.
- **User usability:** the workflow is direct enough for the user to use repeatedly.
- **Architecture extensibility:** boundaries stay clean and future work does not require breaking the package model.
- **Industry gap:** distance from leading systems at the same stage.

The final report will use these ratings:

- `ready`: usable for the stage with normal operational caution.
- `partial`: implemented pieces exist but the workflow is incomplete or inconvenient.
- `experimental`: useful for research or future direction but not current production scope.
- `reserved`: placeholder or planned capability, not runtime behavior.
- `misaligned`: substantial code exists, but it does not currently serve the next strategic boundary.

## 7. Industry Benchmark Set

The report will use primary or official sources where possible and distinguish stable facts from inference.

Benchmarks:

- **QuantConnect LEAN:** full-stack research/backtest/live workflow, Algorithm Framework, portfolio/risk/execution models, optimization, cloud productization, AI assistance.
- **NautilusTrader:** event-driven architecture, live/backtest consistency, high-performance order and data model, production trading focus.
- **Microsoft Qlib:** research workflow, data/model pipeline, experiment management, factor/model evaluation, RD-Agent direction.
- **RiceQuant and JoinQuant:** China-market data breadth, fundamentals, industry classification, research usability, strategy API, A-share workflow.
- **VeighNa:** domestic broker gateway ecosystem, event engine, CTA/portfolio workflows, live trading integration.
- **PyPortfolioOpt, vectorbt, Backtrader, OpenBB:** focused references for portfolio optimization, fast research, classic backtesting, financial data and AI copilot experience.

The benchmark analysis will avoid treating every external feature as a current Ditto requirement. Each gap must be assigned to L1, L2, L3, or L4.

## 8. Source Verification Plan

The assessment will verify current source reality instead of repeating old reports.

Key files and areas to inspect:

- Root guidance: `CLAUDE.md`, `AGENTS.md`, `docs/architecture/agent-context-pack.md`, `docs/architecture/boundaries-and-abstraction-standards.md`.
- Maturity and acceptance: `docs/architecture/capability-maturity.md`, `docs/acceptance/rc1-release-checklist.md`, `artifacts/acceptance/rc1-report.json`.
- Data and catalog: `packages/data`, ingestion coordinators, catalog metadata, promotion evidence, source fallback, query facades.
- Factor and strategy: expression compiler, factor specs, production guard, factor bridge, stock selection templates, ETF templates.
- Backtest: data feed, input bundle, factor-aware bundle, engine loop, replay proof, reports.
- Portfolio and risk: rebalancing, constraints, launch risk report, pre/post-trade checks.
- Signal and operations: signal package publisher, manual fill flow, deviation report, trade API/CLI surfaces.
- Execution and reconciliation: broker protocols, paper gateway, recording gateway, reconciliation, repair workflow, audit.
- API/CLI/jobs: route maturity, OpenAPI metadata, CLI ergonomics, Prefect flows.
- CI and quality gates: `pyproject.toml`, pixi tasks, import-linter, architecture smell checks, acceptance scripts.

Known old-report conclusions will be rechecked. For example, the earlier "fundamental factors are not injected into backtests" finding must be updated because current source includes `fundamental_snapshot` and `get_fundamental_snapshot` paths.

## 9. Output Structure

The final assessment should be written as a source-grounded strategic report at:

`docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`

Proposed report sections:

1. Executive summary.
2. Current system fact base.
3. Five-stage maturity assessment.
4. Functional frontier and completeness assessment.
5. AI/Agent-native gap assessment.
6. Architecture cleanliness and extensibility assessment.
7. Industry benchmark gap matrix.
8. Repositioning recommendation.
9. Next-phase roadmap with P0/P1/P2 priorities.
10. Stop-doing or defer list to reduce target drift.

## 10. Expected Strategic Outputs

The report must make these decisions explicit:

- Current best version label for Ditto.
- Current usable workflows.
- Workflows that are not yet production-credible.
- Capabilities that should stop receiving proactive expansion for now.
- Next-phase product boundary.
- Engineering changes required to keep the full-stack platform sustainable.
- AI/Agent opportunities that can create near-term daily value.
- AI/Agent capabilities that must wait for stronger safety, audit, or live-trading foundations.

## 11. Quality Bar

The assessment is accepted only if it:

- Uses source-code evidence for claims about current Ditto.
- Separates synthetic/golden evidence from real-data production evidence.
- Does not confuse backend primitives with user-ready workflows.
- Updates stale historical findings when current source has changed.
- Explicitly separates current, next, and long-term scope.
- Includes AI/Agent comparison and AI-native readiness as a first-class section.
- Produces actionable next-phase priorities instead of an unbounded feature wish list.

## 12. Review Gate

After this design is written and committed, the user should review it before any implementation plan is created. The next skill after approval is `superpowers:writing-plans`, per the brainstorming process.

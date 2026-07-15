# Ditto System Positioning Assessment

> Date: 2026-06-24
> Scope: backend monorepo at `/home/chevy/projects/ditto`
> Method: source-level inspection, committed acceptance evidence, historical review reconciliation, and official industry benchmark references.

## Executive Summary

Ditto should remain a long-term full-stack personal quant platform, but its next usable boundary should be stated as a staged platform rather than a fully live-trading product. The current source tree shows a strong engineering and architecture foundation, a credible daily research/backtest/signals backend, and extensive execution/reconciliation primitives. The main strategic risk is target drift: large amounts of backend machinery exist before the daily user workflow is simple, real-data-proven, and AI/Agent-friendly.

## Current System Fact Base

### Repository Scale

Ditto is no longer a prototype-scale project. Current source inspection shows:

| Area | Python files | LOC |
|---|---:|---:|
| Production source | 999 | 135,100 |
| Tests | 800 | 212,559 |

The largest production packages are `data` (299 files / 35,409 LOC), `application` (152 / 31,810), `apps` (121 / 17,396), and `features` (122 / 16,129). Test weight is similarly concentrated in `application`, `data`, `apps`, `backtest`, `execution`, and `features`. This is a mature backend system with substantial governance and verification investment; its strategic question is no longer "is there enough code," but "which code forms a daily usable platform boundary."

### Architecture Frame

The active architecture model is the 12-package capability-plane structure documented in `CLAUDE.md` and `docs/architecture/agent-context-pack.md`:

```text
apps -> application -> {data, features, strategy, portfolio, risk, execution, backtest, analysis} -> kernel
platform = horizontal technical foundation
```

`application` owns use-case orchestration. `apps` owns API/CLI/jobs and composition root wiring. `data`, `features`, `strategy`, `portfolio`, `risk`, `execution`, and `backtest` are peer capability planes rather than a simple vertical stack. `analysis` is research-only and production packages must not depend on it. This model is unusually explicit for a personal quant platform and is mechanically protected by import-linter and architecture smell checks.

### Current Acceptance Evidence

The committed `artifacts/acceptance/rc1-report.json` records a successful historical acceptance bundle generated on 2026-06-17. Its key evidence includes:

- `pixi run -e dev check` passed in the recorded artifact, including lint, format, type, fast tests, import-linter, and architecture smell checks.
- The targeted synthetic golden lane passed 8 tests across ETF golden, stock-selection golden, and stock-selection signal package E2E.
- A real-data E2E lane passed 2 FRED PIT-related tests.
- The embedded maturity-status output still showed many experimental or blocked datasets with missing catalog storage/schema/freshness evidence.

This means the artifact proves strong backend gates and synthetic/golden workflows, but it must not be treated as final proof that all launch datasets are production-admitted. Real-data production credibility remains stricter than "recorded acceptance passed."

### Assessment Principle

This report does not equate code volume with product readiness. A capability is treated as usable only when it has a coherent workflow, source evidence, validation evidence, and a clear stage boundary. Backend primitives, protocol seams, and governance machinery are valuable, but they are not automatically user-ready workflows.

## Five-Stage Maturity Assessment

### Recommended Product Positioning

Ditto should be positioned as a long-term, full-stack, A-share ETF-first personal quant platform, but the current usable product boundary should be narrower:

> A daily research and decision-support backend for A-share ETF strategies, with governed data ingestion, PIT-aware backtests, factor/strategy signal generation, manual execution tracking, deviation reporting, and paper/execution protocol foundations.

This means the present system is not yet a polished live-trading platform, not yet a fully automated multi-asset alpha factory, and not yet an AI-native quant operating system. It is strongest as a governed backend platform that can produce auditable daily research, backtest, and signal artifacts. The next product goal should be to turn that backend strength into a small number of complete daily workflows.

### Stage Summary

| Stage | Target Role | Current Rating | Usable Boundary | Main Gap |
|---|---|---|---|---|
| L0 | Platform kernel and engineering governance | Strong | Package boundaries, import rules, test gates, maturity rules, lineage/catalog governance | Complexity concentration and documentation density make the system hard to operate without a curated workflow |
| L1 | Research, data, features, backtest | Partial-ready | ETF daily data, ETF strategies, factor materialization, deterministic backtest/replay evidence | Stock/fundamental/macro data are still experimental; real-data launch evidence is incomplete |
| L2 | Portfolio decision and risk control | Partial | Signal package generation, target portfolio bridge, pre/post checks, basic manual decision loop | Optimizer, portfolio analytics, risk dashboards, attribution, and decision UX are not yet product-complete |
| L3 | Paper trading and broker-simulated operations | Experimental-partial | OMS FSM, PaperBrokerGateway, broker-event recording, reconciliation/repair primitives, manual fill/deviation loop | Daily paper account lifecycle, continuous risk, scheduler, user-facing account state, and operational polish are incomplete |
| L4 | Live trading and autonomous operations | Reserved/experimental | Protocol seams, descriptors, conformance fixtures, recording gateway | No real broker adapter, no live credentials/runtime, no product UI in this repo, no AI/Agent operating layer |

### L0: Backend Platform Kernel

L0 is the most mature layer. The architecture is explicit, well-tested, and unusually disciplined for a personal quant codebase. The 12-package model keeps `apps`, `application`, capability packages, `platform`, and `kernel` separated, and the maturity manifest defines guardrails for experimental versus initial-focus behavior. Source evidence includes the architecture contract in `CLAUDE.md`, the capability-plane reference in `docs/architecture/agent-context-pack.md`, the maturity rules in `docs/architecture/capability-maturity.md`, and import-linter/architecture-smell gates recorded in the RC1 acceptance artifact.

The main L0 issue is not lack of engineering quality. It is cognitive load. The backend has accumulated enough governance, DTOs, lineage, source fallback, repair, and maturity machinery that a user cannot infer the practical daily workflow from code structure alone. For the next stage, L0 should serve L1-L3 workflows, not continue expanding as an end in itself.

### L1: Research, Data, Features, and Backtest

L1 is the first layer that can become genuinely useful soon. The strongest current boundary is A-share ETF daily research and backtest. `docs/architecture/capability-maturity.md` marks A-share ETF daily data/research/backtest, feature/factor materialization, ETF strategy templates, and the backtest engine as `initial-focus`. The backtest stack has deterministic replay, checkpoint/resume, PIT policy propagation, source-snapshot propagation, and artifact evidence.

The stock/fundamental/macro side is promising but should remain experimental until launch datasets are promoted with real evidence. The system already has stricter safeguards than many hobby quant stacks: catalog-backed maturity gates fail closed unless callers explicitly set `allow_experimental_data` or a persisted promotion override exists. The newer fundamental bridge is important because it closes a previous class of factor-readiness gap: `packages/application/src/ditto_application/processes/execution/fundamental_snapshot.py` builds a PIT-aware snapshot with `roe`, `net_margin`, and `eps`, and `packages/application/src/ditto_application/processes/execution/factor_bridge.py` injects that snapshot into current-day rows using `knowledge_date`, then derives `pe_ratio` from close and EPS. This is the right architectural direction because backtest orchestration receives a closure instead of importing PIT query policy directly.

The remaining L1 gap is real-data completeness. `packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py` shows a token-gated Tushare E2E path for metadata, market bars, valuation metrics, universe creation, signal publication, and experimental-data opt-in. That proves the direction, but it does not yet prove all launch datasets, promotion evidence, repeatable daily refresh, and failure-handling needed for a product boundary. L1 should therefore target "ETF production-ready plus stock-selection research beta", not "full A-share quant research platform" yet.

### L2: Portfolio Decision and Risk Control

L2 is present but not product-complete. The strategy layer can emit target portfolios and signal packages, and the application layer has bridges such as canonical target IDs and strict identity mapping. `packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py` proves a valuable end-to-end loop: manual signal -> fill -> position -> deviation. That is the embryo of a daily trader workflow.

The gap is that a top personal quant system needs portfolio decisioning, not only signal production. The maturity manifest still marks portfolio accounting/rebalancing and risk checks as experimental. Pre/post checks exist, but continuous risk, typed audit payloads, and state recovery are incomplete. The next L2 boundary should be: "Given today's approved signals and current account state, produce a target portfolio, explain the sizing/risk tradeoffs, and show what changed from the previous day." Until that exists, Ditto remains a research backend with execution primitives rather than an integrated decision platform.

### L3: Paper Trading and Operational Loop

L3 has substantial low-level machinery but only partial daily workflow readiness. The execution package has an `initial-focus` OMS FSM with seven states, order book/ticket concepts, and dual client/broker IDs. `PaperBrokerGateway` is experimental but broad: submit/fill/cancel/reject/partial-fill behavior, broker event recording, broker-order ID query, reconciliation links, repair actions, retry semantics, and SQLite-backed claim guards are all represented in the maturity manifest.

This is strong backend infrastructure. The product gap is the missing operating loop. A daily user should be able to run paper mode, inspect account state, review open orders/fills/reconciliation, apply or reject repair actions, and compare actual versus target weights. Today, those pieces exist as backend contracts, fixtures, and tests, but not as a compact workflow with scheduler, status page/API narrative, and "what should I do next" guidance. L3 should be promoted only after daily paper-run ergonomics are proven.

### L4: Live Trading and Autonomous Operation

L4 should stay explicitly out of the current usable boundary. The maturity manifest says live trading adapters are `reserved`, and the backend scope explicitly excludes real broker adapter implementation and product UI. That is a good constraint. It prevents protocol work from being mistaken for live-trading readiness.

For a long-term full-stack platform, L4 will eventually require broker-specific adapters, credential isolation, kill switches, continuous risk gates, reconciliation against broker truth, outage recovery, audit trails, and operator controls. For an AI/Agent-native platform, it will also require agent-safe tool contracts, permissioned action scopes, explainable recommendations, dry-run/approval gates, memory over runs, and benchmarked research automation. Current Ditto has many of the ingredients for audited backend actions, but not yet the AI/Agent layer itself.

## Functional Completeness Gap Matrix

### Capability Heatmap

| Capability Area | What Exists Now | Current Gap Versus a Top Personal Quant Platform | Stage |
|---|---|---|---|
| Data ingestion and catalog governance | Date/instrument ingestion, DataCatalog runtime, lineage, freshness/schema/source-health reports, dataset maturity gates, source fallback policy state | Launch datasets still need repeated real-data promotion evidence and a user-visible daily data readiness workflow | L1 |
| PIT and research safety | `knowledge_date` PIT gates, unsafe trade-date fallback controls, source snapshots, factor-history leakage fixtures, fundamental/classification snapshot injection | Broader real-data PIT regression coverage and clearer operator proof surfaces are still needed | L1 |
| Feature/factor research | Factor expression/materialization, production guard, IC/ICIR, IC decay, turnover-adjusted IR, long-short, CVaR/tail risk, optional regime and attribution reports | Factor library and diagnostics are strong, but experiment management, comparison history, and research notebook/product ergonomics are not yet first-class | L1 |
| Strategy templates | ETF rotation and ETF trend/swing initial-focus; stock-selection and sector-rotation experimental with canonical ID and snapshot evidence | Strategy breadth is still narrow; stock/fundamental strategies depend on experimental datasets and need promotion-grade evidence | L1-L2 |
| Portfolio allocation | Equal weight, score weight, inverse-vol allocators; max weight, max positions, industry cap, liquidity, tradability, max turnover constraints | No production mean-variance, HRP/risk parity, Black-Litterman, robust covariance, objective/constraint optimizer, or optimizer explainability | L2 |
| Risk | Buying-power/lot-size/no-short/price-validity/concentration/daily-turnover pre-checks; max-drawdown and concentration post-trade guards; kill-switch model; launch risk report with concentration, active weight, drawdown, VaR/CVaR and simple stress scenarios | Continuous risk runtime, persistent risk state recovery, richer stress library, scenario attribution, and risk-review UX are incomplete | L2-L3 |
| Backtest and simulation | Deterministic engine, replay/checkpoint/resume, A-share fees/slippage/settlement, limit-up/down/suspension behavior, partial fill via participation, report/audit artifacts | Real-data coverage and strategy/template promotion are the bottleneck; parameter sweeps, walk-forward, experiment registry, and result comparison UX are limited | L1-L2 |
| Signal and manual decision loop | Deterministic signal packages, selection reasons, factor values, dataset snapshots, persisted trade intents, manual fill -> position -> deviation test | The daily user loop needs a cohesive review surface: "new signals, why, risk, current holdings, proposed orders, expected tracking error" | L2 |
| Actual portfolio and comparison | Trade/position/P&L query routes; backtest-vs-actual comparison metrics; application deviation facade computes position-weight deviation | Portfolio-level attribution, factor/cost attribution, and polished actual-vs-target reporting are not yet user-ready | L2-L3 |
| EOD operations | Prefect EOD flow chains ingestion -> materialization -> strategy, with cron deployment scaffolding and failure alerts | EOD is backend orchestration, not yet a full operating console with approvals, retries, readiness summaries, and paper/account review | L1-L3 |
| Paper trading and reconciliation | PaperTradingRuntime, PaperBrokerGateway, broker-event recording, reconciliation/repair/audit primitives and conformance fixtures | Paper mode lacks a compact account lifecycle workflow and a daily operator experience; real broker adapters remain reserved | L3-L4 |
| Product/API/UI boundary | FastAPI routes, CLI, OpenAPI maturity metadata, DTO-heavy backend surfaces | The current repo intentionally has no product UI; usability depends on `ditto-app` or another client consuming the contracts | Cross-cutting |
| AI/Agent-native operation | Some agent-friendly ingredients exist: typed DTOs, audit trails, maturity gates, explicit approvals, deterministic artifacts | There is no dedicated quant agent layer, no tool permission model, no research planner/evaluator agent, no agent memory over runs, and no safe autonomous action loop | Cross-cutting |

### Most Important Functional Conclusion

Ditto's functional center of gravity is stronger in governed infrastructure than in daily user productivity. The system has many pieces that top platforms need: lineage, PIT safety, maturity gates, deterministic backtests, signal packages, risk checks, paper gateway conformance, and EOD orchestration. But top systems become useful because they compress these pieces into a short path:

1. Data is ready or the system says exactly what is missing.
2. Strategies produce candidate trades with explanations.
3. Portfolio/risk converts candidates into a constrained target.
4. The user approves, executes manually or in paper mode, and sees deviations.
5. The next day the system compares expected versus actual behavior.

Ditto has parts of all five steps, but the steps are not yet one product-grade loop. That is why the system can feel heavily built yet still "not especially usable": the backend depth is real, but the daily workflow boundary is under-defined.

### Priority Functional Gaps

The highest-leverage functional gap is portfolio construction. Current allocation is simple and transparent, which is good for an early boundary, but a top personal quant platform needs at least one robust allocation module that jointly solves weights under constraints. A pragmatic first version should support long-only mean-variance/min-vol or risk-budget allocation, max weight, industry cap, turnover cap, and fallback to inverse-vol when the covariance problem is ill-conditioned. This would make L2 feel materially better without pretending to be institutional-grade from day one.

The second gap is launch-grade real-data evidence. Stock selection, valuation, fundamental, macro, and source fallback are architecturally present, but current maturity still says experimental for most non-ETF datasets. The next usable boundary should define a small launch dataset set, collect freshness/schema/storage/PIT evidence repeatedly, promote it through the existing data-owned mechanism, and make the readiness report the first page of the daily workflow.

The third gap is daily decision ergonomics. Signal packages already persist target weights, factor IDs, risk flags, selection reasons, and checksums. That is a strong substrate. The missing layer is a single review contract that merges signal package, current position, risk report, expected orders, cost/slippage assumptions, and historical actual-vs-backtest comparison. This should be implemented as backend DTO/API first, then consumed by the frontend.

The fourth gap is operational closure for paper mode. Paper trading should not be judged by gateway conformance alone. It needs an operator-facing lifecycle: run EOD, generate signals, stage paper orders, run/inspect fills, reconcile, approve repair actions, and persist a daily account snapshot. Current primitives are impressive, but the loop is not yet compact.

The fifth gap is AI/Agent-native functionality. Ditto already has useful safety primitives for agents: explicit maturity states, approval-backed remediation, deterministic artifacts, typed DTOs, and audit events. But those are not yet organized as agent tools with scopes, permissions, dry-runs, memory, and evaluation. This should become a first-class platform layer rather than an afterthought.

## Industry Benchmark

### Benchmark Sources Reviewed

This section uses official or primary project sources reviewed on 2026-06-24:

- [QuantConnect Algorithm Framework](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview), [portfolio construction](https://www.quantconnect.com/docs/v1/algorithm-framework/portfolio-construction), and [risk management](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/key-concepts)
- [NautilusTrader live trading](https://nautilustrader.io/docs/latest/concepts/live/), [backtesting](https://nautilustrader.io/docs/latest/concepts/backtesting/), and [architecture](https://nautilustrader.io/docs/latest/concepts/architecture/)
- [Microsoft Qlib GitHub](https://github.com/microsoft/qlib) and [Qlib introduction](https://qlib.readthedocs.io/en/v0.8.5/introduction/introduction.html)
- [PyPortfolioOpt documentation](https://pyportfolioopt.readthedocs.io/en/latest/)
- [VectorBT documentation](https://vectorbt.dev/)
- [VeighNa/vn.py README](https://github.com/vnpy/vnpy/blob/master/README_ENG.md)
- [RQAlpha GitHub](https://github.com/ricequant/rqalpha)
- [OpenBB Copilot docs](https://docs.openbb.co/workspace/analysts/ai-features/copilot-basics), [Agents Integration](https://docs.openbb.co/workspace/developers/agents-integration), [OpenBB AI SDK](https://docs.openbb.co/workspace/developers/openbb-ai-sdk), and [OpenBB Workspace](https://openbb.co/products/workspace/)

### Benchmark Table

| Reference System | What It Represents | Where Ditto Is Competitive | Where Ditto Trails |
|---|---|---|---|
| QuantConnect / LEAN | Mature full-stack algorithmic platform with universe -> alpha -> portfolio construction -> risk -> execution flow | Ditto's package boundaries and TargetPortfolio/signal/risk/execution separation are philosophically aligned; Ditto has stronger local A-share ETF specificity and explicit dataset maturity governance | QuantConnect is far ahead in integrated portfolio construction, reusable risk/execution models, live trading workflow, broker/data ecosystem, research UI, and community modules |
| NautilusTrader | Production-grade event-driven trading engine with backtest/live parity and strong runtime architecture | Ditto has an unusually disciplined backend boundary model and good paper/reconciliation primitives; its A-share daily simulator has domain-specific fee, settlement, limit and suspension handling | NautilusTrader is far ahead in live runtime maturity, node operations, execution adapters, high-performance core, backtest-live code parity, and operational deployment readiness |
| Qlib | AI-oriented quantitative research platform covering data, models, workflow, signals, decision generation and execution environment concepts | Ditto is stronger as a typed, multi-domain backend with governance, data maturity gates, execution/reconciliation and A-share operational semantics | Qlib is far ahead in ML-first research workflow, model zoo, supervised/RL paradigms, factor/model experimentation, and AI research automation ecosystem |
| PyPortfolioOpt | Focused portfolio optimization library with efficient frontier, Black-Litterman, shrinkage, HRP and related optimizers | Ditto has the broader platform context where an optimizer could be embedded into data/risk/execution workflows | PyPortfolioOpt is far ahead in portfolio optimizer breadth, optimizer API maturity, covariance/expected-return utilities, and practitioner ergonomics |
| VectorBT | High-speed vectorized research/backtesting for large strategy grids and parameter exploration | Ditto is stronger in event-driven realism, PIT governance, lineage, and execution semantics | VectorBT is far ahead in fast exploratory iteration, large parameter sweeps, notebook/research ergonomics, and interactive analysis scale |
| VeighNa/vn.py | China-oriented full-stack quant trading framework with backtesting, live trading, modules, and AI-powered multi-factor direction | Ditto has cleaner modern package boundaries, stricter test/gate culture, and deeper data-governance language | vn.py is far ahead in domestic broker ecosystem, live trading, user community, GUI/module completeness, and practical trader adoption |
| RQAlpha | Extendable, replaceable Python algorithmic backtest/trading framework for multiple securities | Ditto has a more ambitious governance and full-stack backend design | RQAlpha is more mature as a compact backtest/trading framework and has simpler adoption for users who want a direct algorithm runtime |
| OpenBB Workspace | Financial data workspace with Copilot, custom agent integration, type-safe AI SDK, dashboards, access control and audit trail positioning | Ditto has proprietary quant-domain backend artifacts that could become excellent agent tools | OpenBB is far ahead in user-facing workspace, dashboard composition, agent integration contracts, agent streaming, governed AI UX, and analyst workflow polish |

### Strategic Reading

Ditto should not try to become all of these systems at once. Its plausible winning position is narrower and sharper:

> A local-first, A-share-aware, evidence-governed quant backend that turns daily data into explainable ETF/stock decisions, with AI agents operating through audited, permissioned workflows.

This positioning avoids competing head-on with QuantConnect's global cloud ecosystem, NautilusTrader's live trading engine focus, Qlib's ML research breadth, OpenBB's workspace product, or PyPortfolioOpt/vectorbt's specialized ergonomics. Instead, Ditto can use its existing strengths: strict maturity gates, PIT safety, A-share simulation semantics, deterministic artifacts, backend DTO contracts, and execution auditability.

The strategic gap is that the current codebase has not yet converted those strengths into a single obvious product surface. Top systems are recognizable because their core loop is explicit: QuantConnect has algorithm modules; Nautilus has one runtime model across backtest/live; Qlib has an AI quant workflow; OpenBB has workspace + agents. Ditto's equivalent should be the Daily Quant Operating Loop:

1. Data readiness and promotion evidence.
2. Factor/strategy signal generation.
3. Portfolio/risk construction.
4. Manual or paper execution.
5. Deviation, attribution, and next-day learning.

Every near-term feature should strengthen this loop. Features that do not improve this loop should be deferred, even if they are technically elegant.

## AI/Agent-Native Gap Assessment

### Agent Benchmark Sources Reviewed

This section uses official or primary project sources reviewed on 2026-06-24:

- [OpenBB Copilot Basics](https://docs.openbb.co/workspace/analysts/ai-features/copilot-basics), [OpenBB Agents Integration](https://docs.openbb.co/workspace/developers/agents-integration), and [OpenBB AI SDK](https://docs.openbb.co/workspace/developers/openbb-ai-sdk)
- [RD-Agent Finance Quant Agent](https://rdagent.readthedocs.io/en/latest/scens/quant_agent_fin.html)
- [TradingAgents GitHub](https://github.com/tauricresearch/tradingagents)
- [FinRobot GitHub](https://github.com/AI4Finance-Foundation/FinRobot)

### Current AI-Ready Assets In Ditto

Ditto does not yet have a real AI/Agent layer, but it has unusually good ingredients for one. The most important asset is not a model wrapper. It is the amount of structured, auditable backend state that an agent could safely read and cite.

The existing system already exposes data readiness, maturity, source-health, lineage, promotion evidence, signal packages, factor diagnostics, risk reports, execution audit, reconciliation, and remediation approval state as typed backend contracts. `packages/application/src/ditto_application/queries/catalog_source_health.py` is especially agent-friendly because it returns fixed reason codes, status counts, attention severity counts, selected source evidence, fallback policy effects, and blockers. `packages/apps/src/ditto_apps/models/remediation.py` exposes remediation backlog, evidence requirements, approval intents, approval requests, decisions, executions, and append-only audit events as explicit API models. `packages/application/src/ditto_application/commands/catalog_remediation.py` already uses an action-code executor registry and fails closed for unsupported or unsafe remediation actions. `packages/execution/src/ditto_execution/reconciliation/repair.py` separates side-effect-free repair planning from state-changing actions that require manual review.

Those traits matter because a quant agent must not just "answer questions." It must know what evidence it is using, what maturity boundary applies, what action is allowed, what requires approval, and what was actually executed. Ditto is closer to that safety substrate than many personal quant projects.

The only direct AI-specific source hook found in production code is `packages/features/src/ditto_features/expression/hypothesis.py`. It defines an `Hypothesis` object and a `hypothesis_to_expression(...)` bridge, but the implementation is intentionally only a placeholder that passes through `expression_draft`. That file is a useful marker of intent, not an AI research loop.

### What Is Actually Missing

The gap is clear: Ditto has agent-readable artifacts, but not agent behavior.

There is no first-class LLM runtime, no agent service, no tool registry, no tool permission model, no scoped read/write action contract, no streaming response protocol, no durable agent memory, no research-plan state machine, no hypothesis-to-experiment automation, no role-based multi-agent debate, no agent evaluation harness, no prompt/version governance, no citation policy over internal artifacts, and no AI UI contract. There is also no explicit trade authorization boundary that says which agent can propose, stage, approve, submit, cancel, repair, or only explain an order.

This distinction is important for positioning. Ditto should not claim to be AI-native today. It should claim to be AI-ready at the backend artifact and governance level. The next AI milestone should be a read-only copilot over daily quant artifacts, not autonomous trading.

### AI/Agent Benchmark Table

| Reference | What The Frontier Looks Like | Ditto Current State | Concrete Gap |
|---|---|---|---|
| OpenBB Workspace Copilot and Agents | Integrated financial copilot, workspace context, dashboard data access, streaming agent protocol through `/agents.json` and `/query`, step-by-step reasoning, citations, artifacts, and custom agent integration | Ditto has typed backend artifacts that could feed a copilot, but no copilot surface or agent HTTP/SSE contract | Build a read-only `ditto-agent` service with artifact citation, streaming output, and explicit tool scopes |
| RD-Agent / Finance Quant Agent | Multi-agent quant R&D that automates factor/model co-optimization, hypothesis generation, experiment execution, coding, running, and feedback | Ditto has factor expressions, IC reports, backtests, materialization, and a placeholder hypothesis bridge | Add a research-agent loop: hypothesis -> candidate expression -> validation -> backtest -> report -> human promotion decision |
| TradingAgents | Role-specialized LLM trading framework with analysts, researchers, traders, risk review, debate rounds, and a final decision process | Ditto has risk reports and signal packages, but no role-specific agents or adversarial review | Add separate read-only analyst, portfolio, and risk reviewer roles before any execution-adjacent agent |
| FinRobot | Locally deployable financial assistant that fetches financial data, runs multi-agent analysis, and generates professional equity research reports | Ditto has stronger internal quant artifacts than generic market-data assistants, but no report-generation agent | Generate daily ETF/stock decision memos from Ditto artifacts with citations, uncertainty, and follow-up actions |
| General agent platforms | Tool calling, memory, workflow orchestration, human-in-the-loop controls, observability, and evaluation | Ditto has human approval and audit concepts in remediation/reconciliation, but not generalized for agents | Generalize approval/action semantics into an agent-safe tool and policy layer |

### Recommended AI Layer

AI should be introduced as staged product capability, not sprinkled into individual modules.

| AI Stage | Scope | Allowed Actions | Promotion Criteria |
|---|---|---|---|
| A0 Read-Only Copilot | Explain data readiness, latest signals, factor values, risk flags, backtest artifacts, fills, positions, and deviations | Read-only queries; cite exact artifacts; no writes | Answers are reproducible, cite internal object IDs, and refuse missing or experimental evidence |
| A1 Research Agent | Generate factor/strategy hypotheses, compile expressions, run offline evaluations, compare experiments, and draft promotion reports | Create research artifacts only; no production promotion | Every proposal includes data scope, PIT status, leakage checks, IC/backtest evidence, and failure cases |
| A2 Decision Assistant | Combine signal package, current holdings, risk report, cost/slippage assumptions, and proposed target portfolio into a daily decision memo | Stage proposed intents only; human approval required | Memo explains sizing, constraints, risk deltas, and actual-vs-backtest context |
| A3 Operations Agent | Triage source-health, lineage, freshness, promotion, reconciliation, and remediation backlog | Draft approval requests and execute only pre-approved non-trading remediation actions | All writes pass existing approval/audit paths and fail closed on blocked source-selection evidence |
| A4 Live Trading Agent | Long-term reserved scope for broker-connected trading assistance | No autonomous live order submission in current roadmap | Requires real broker adapter maturity, permissions, kill switch, DR plan, audit replay, and human override |

The strongest near-term path is A0 plus a narrow A1. A0 would immediately make the current backend more usable by answering questions like "what changed today?", "why was 510300 selected?", "which data source is stale?", and "how far is the actual portfolio from target?" A1 would turn the placeholder `Hypothesis` bridge into a supervised research loop, while keeping all promotion and execution decisions human-controlled.

### AI Design Boundary

The AI layer should sit above `application`, not inside data, strategy, portfolio, or execution packages. It should call stable application queries/commands, carry a session/run ID, persist prompts and tool results, cite artifact IDs, and distinguish `read`, `draft`, `request_approval`, and `execute_approved` scopes. Any write path must reuse existing command handlers or approval workflows; agents should never write directly to data stores, broker adapters, or package internals.

For trading specifically, the first durable rule should be simple: an agent may explain, compare, and propose, but it may not place live orders. That keeps Ditto's long-term AI ambition aligned with the current maturity boundary instead of letting an impressive demo create false operational confidence.

## Architecture, Extensibility, and Engineering Quality

### Overall Judgment

Ditto's architecture is not the weak point. The source tree shows a rare level of discipline for a personal quant platform: package boundaries are explicit, import contracts are executable, API maturity is surfaced, PIT and maturity rules fail closed, tests are broad, and acceptance artifacts record full lint/type/test/import checks passing.

The main architecture risk is different: the system is now powerful enough that more backend abstraction can reduce product clarity. The next phase should measure architecture by how quickly it lets the user complete the Daily Quant Operating Loop, not by how many additional seams, DTOs, and governance contracts it can add.

### Architecture Strengths

| Dimension | Current Assessment | Evidence |
|---|---|---|
| Package boundaries | Strong | `CLAUDE.md` and `docs/architecture/agent-context-pack.md` define `apps -> application -> capability packages -> kernel`, with `platform` as horizontal infrastructure |
| Machine-enforced architecture | Strong | `.importlinter` contains broad layer contracts plus explicit forbidden contracts for data, features, strategy, portfolio, risk, execution, backtest, analysis, apps, and application |
| Architecture smell checks | Strong | `scripts/architecture/check_architecture_smells.py` checks low-noise smells including oversized files, cross-package re-export, platform business leakage, app capability imports, generic helper namespaces, route maturity annotations, and explicit `__all__` |
| CQRS and composition | Strong | Application separates `queries`, `commands`, `processes`, `builders`, and providers; apps registry acts as composition root |
| Data and maturity governance | Strong | Dataset maturity gates, promotion evidence, source-health, fallback policy effects, lineage reports, and remediation approvals all have typed contracts |
| Test and static quality | Strong | Historical RC1 evidence records lint, format, type, fast tests, import-linter, and architecture smell checks passing; quality reports note zero production `TYPE_CHECKING`, zero pandas imports, and strict pyright/ruff gates |
| Domain safety | Strong | PIT rules, explicit `allow_experimental_data`, deterministic signal package checksums, replay/checkpoint evidence, A-share simulation semantics, and manual fill/deviation tests reduce silent failure risk |

This is above the architecture baseline of most open-source personal quant projects. Ditto is not a notebook collection, not a single backtest engine, and not a tangled app. It is a governed backend platform.

### Architecture Gaps Versus Top Systems

| Gap | Why It Matters | Recommended Direction |
|---|---|---|
| Product workflow is less explicit than architecture workflow | Top systems have an obvious entry point: QuantConnect has algorithm framework modules, Nautilus has one backtest/live runtime model, Qlib has workflow/data/model loops, OpenBB has workspace plus copilot | Define one primary backend contract for the daily decision cockpit and make every near-term capability feed it |
| Application and apps layers carry high cognitive load | Many use cases are correctly placed, but the user must understand many facades, DTOs, maturity reports, and remediation paths to operate the system | Introduce thin, curated "daily loop" facades that compose existing contracts without weakening package boundaries |
| Governance is stronger than operational UX | Maturity, source-health, lineage, promotion and remediation are well-modeled, but they are not yet compressed into an operator-ready readiness narrative | Create a daily data readiness report as the first screen/API of the product |
| Portfolio/risk abstractions lag data/execution abstractions | Portfolio has simple allocators and constraints; risk has useful reports, but not a mature optimizer/attribution/control loop | Build one constrained optimizer plus attribution report before adding more execution infrastructure |
| Observability infrastructure is ahead of business instrumentation | Prior quality review found logging/config foundations strong, while business metrics and tracing were not broadly instrumented | Add spans and metrics for ingestion, materialization, strategy run, portfolio construction, paper execution, and reconciliation |
| Security and permissions are not yet product-grade | API routes and future agent tools need authentication, authorization, action scopes, and audit controls before multi-user or live usage | Add API auth for product deployment and design agent/action scopes before AI writes are introduced |
| Quantitative technical-debt tooling is incomplete | Current gates are strong, but duplication, maintainability index, dead code, and SQALE-style debt are not fully measured | Add radon/vulture/jscpd or equivalent baselines, but avoid blocking product progress on vanity metrics |

### Extensibility Assessment

Ditto is structurally extensible in three important ways.

First, capability packages are peer domains. Adding a factor expression, strategy template, portfolio allocator, risk checker, broker protocol implementation, or data source has a predictable home. This is the kind of extensibility a long-lived quant system needs.

Second, application-owned ports prevent many dependencies from leaking in the wrong direction. The fundamental and factor bridge work is a good pattern: the backtest path receives prepared snapshots and closures from application orchestration instead of importing data query details directly.

Third, the maturity and approval systems can support safe expansion. Experimental data, fallback policy, remediation actions, and approval workflows already have states and evidence. This creates a useful platform for future AI agents, real-data promotion, and paper-trading operations.

The extensibility weakness is that the system has many "where to put it" answers and fewer "what user workflow does it improve" answers. Extensibility should now be constrained by a product rule: a new extension point is justified only if it improves data readiness, signal quality, portfolio decisioning, paper execution, attribution, or AI-assisted review.

### Engineering Quality Rating

| Area | Rating | Why |
|---|---|---|
| Code quality | High | Typed Python, strict lint/type gates, package ownership, low reliance on ignores, no pandas dependency, clear naming standards |
| Architecture quality | Very high | Executable import contracts, smell checks, CQRS conventions, package-level manuals, and explicit maturity metadata |
| Test quality | High | Large unit/integration/e2e surface, deterministic and golden lanes, real-data gated tests, and acceptance artifact evidence |
| Domain correctness | High for ETF daily, partial for stock/fundamental/macro | A-share costs/settlement/fill rules and PIT discipline are strong; non-ETF launch datasets still require promotion evidence |
| Operations quality | Medium | EOD/Paper/reconciliation primitives exist, but observability, status UX, account lifecycle, security, and incident practices are incomplete |
| Product usability | Medium-low | The backend is deep, but the default user path is not yet a compact daily product loop |
| AI readiness | Medium substrate, low product | Strong artifacts and approval paths, but no agent runtime, memory, tools, evals, or UI |

### Clean Architecture Risks To Watch

The biggest near-term risk is "DTO gravity." As the system adds more query facades and API response models, apps and application can become a mapping-heavy shell around scattered capability contracts. The correct fix is not to collapse layers. It is to introduce product-specific orchestration contracts that are intentionally small: daily readiness, daily signals, daily portfolio decision, daily paper account, and daily review.

The second risk is "governance inflation." Maturity gates, source fallback, remediation and approval are valuable, but they can make the system feel like a compliance engine before it feels like a quant platform. The next iterations should make governance disappear into a clear operator answer: ready, blocked, needs review, or safe to proceed.

The third risk is "execution overhang." Execution/reconciliation work is sophisticated, but live trading remains reserved and paper trading is not yet a complete daily account product. More broker-edge work should wait until L1/L2 workflows produce stable decisions and L3 paper operations are useful every day.

The fourth risk is "AI demo temptation." Because Ditto has structured artifacts, it would be easy to wrap an LLM around the API and call it an agent. That would be strategically weak. The AI layer needs scoped tools, citations, approvals, memory, and evaluation from the start.

### Engineering North Star

The architecture should now serve one sentence:

> Every trading day, Ditto should tell the user whether data is ready, what changed, what to hold, why, what risk changed, what to do manually or in paper mode, and how yesterday's decision behaved.

If a module, abstraction, or workflow does not make that sentence easier to execute, it should be deferred.

## Recommended Positioning and Stage Boundaries

### Final Positioning

Ditto should keep the long-term ambition of a full-stack quant platform, but its product story should be staged:

> Ditto is a local-first, A-share-aware, evidence-governed personal quant platform. Its near-term product is a daily ETF and stock-research decision cockpit backed by PIT-safe data, deterministic backtests, signal packages, portfolio/risk construction, manual or paper execution tracking, attribution, and read-only AI assistance.

The words "full-stack" should describe the long-term architecture, not the current usable promise. The current promise should be: daily research, decision support, and audited manual or paper operations. Live trading and autonomous agents remain reserved.

### Stage Boundary Table

| Stage | Product Name | User-Ready Promise | Must Not Claim Yet |
|---|---|---|---|
| V0 Current Backend Foundation | Governed backend platform | The backend has strong package boundaries, PIT/maturity governance, deterministic backtest/signal infrastructure, execution primitives, and acceptance evidence | It is not yet a simple end-user product, live platform, or AI-native operating system |
| V1 Daily ETF Decision Cockpit | First usable product | A daily ETF workflow can answer data readiness, signals, reasons, target weights, launch risk, manual fills, current positions, and target-vs-actual deviation | It is not yet full stock alpha, autonomous execution, or broad portfolio optimization |
| V1.5 Stock Selection Research Beta | Experimental research expansion | Stock/fundamental/valuation datasets can be used with explicit maturity evidence, PIT snapshots, factor IC reports, and stock-selection signal packages | It is not yet production stock selection unless launch datasets are promoted and repeatedly validated |
| V2 Portfolio and Attribution Layer | Decision-quality upgrade | Signals become constrained target portfolios with optimizer explanation, risk deltas, cost assumptions, and factor/portfolio attribution | It is not yet live trading or institutional optimizer breadth |
| V3 Paper Trading Operating Loop | Semi-automated operations | Paper account lifecycle, staged orders, fills, reconciliation, repair approvals, P&L, deviation, and daily review are one loop | It is not yet real broker live trading |
| V4 AI-Assisted Quant Workflow | Read-only and supervised agents | Copilot explains artifacts, research agent drafts experiments, operations agent triages issues, all with citations and scoped approvals | It is not autonomous trading or self-promoting alpha |
| V5 Live Trading Platform | Long-term reserved | Real broker adapters, credential isolation, live risk, kill switches, disaster recovery, and audit replay are proven | No date should be promised until V1-V3 are boringly reliable |

### The Minimum Lovable Version

The next usable version should be V1, not V5. It should feel small, sharp, and daily.

V1 should have one backend entry point or small API family that returns:

1. Data readiness: launch datasets, source freshness, maturity status, missing evidence, and blocking reasons.
2. Today's signal package: instruments, scores, factor values, selection reasons, risk flags, dataset snapshots, checksum.
3. Portfolio proposal: current holdings, target weights, proposed trades, turnover, cost/slippage assumptions, constraint hits.
4. Risk review: concentration, active weights, drawdown context, VaR/CVaR or simple tail risk, stress scenarios, and warnings.
5. Manual execution tracking: approved intents, fills, positions, target-vs-actual deviation, unfilled targets.
6. Review memo: what changed from yesterday, what failed, what needs operator action, and where to inspect evidence.

If V1 does only this for ETF strategies, it will be more valuable than a broader system that exposes twenty unrelated backend endpoints.

### Roadmap

| Priority | Workstream | Deliverable | Why It Comes First |
|---|---|---|---|
| P0 | Daily readiness contract | One DTO/API/CLI report that merges source-health, catalog freshness, maturity governance, promotion evidence, and lineage attention into `ready / blocked / review` | Without this, the user cannot trust the daily run |
| P0 | Daily signal review contract | One contract that wraps latest signal package, reasons, factor values, dataset snapshots, checksums, and prior signal diff | This turns strategy output into a usable decision artifact |
| P0 | ETF V1 acceptance lane | Repeatable ETF daily run with synthetic and real-data evidence, no experimental opt-in for launch datasets, and a stable report artifact | This is the smallest credible product boundary |
| P1 | Portfolio optimizer v1 | Long-only constrained optimizer or robust min-vol/mean-variance module with inverse-vol fallback and explanation | This closes the biggest L2 gap against top systems |
| P1 | Target-vs-actual review | Unified current holdings, target weights, fills, unfilled intents, deviation bps, P&L and cost drag | This makes manual execution measurable |
| P1 | Factor and portfolio attribution | Factor contribution, cost attribution, holdings attribution, and actual-vs-backtest explanation | This creates the learning loop |
| P1 | Stock-selection beta promotion | Promote a small stock/fundamental/valuation dataset set with repeated evidence and PIT tests | This prevents stock alpha from remaining permanently experimental |
| P2 | Paper trading operating loop | Staged paper orders, fill simulation, account snapshots, reconciliation, repair approvals, and daily review | This turns execution primitives into an operator workflow |
| P2 | Read-only AI copilot | Artifact-citing copilot for data readiness, signals, risk, deviations, and remediation explanations | This directly improves usability without adding trading risk |
| P3 | Research agent | Supervised hypothesis -> expression -> factor eval -> backtest -> report loop | This is the right AI expansion after read-only answers are reliable |
| P4 | Live broker adapters | Real adapter, credential isolation, live risk, kill switch, disaster recovery, and audit replay | This should wait until paper mode is mature |

### Acceptance Criteria By Boundary

| Boundary | Acceptance Evidence |
|---|---|
| V1 ETF daily cockpit | One command/API run produces readiness, signal package, risk report, target portfolio, manual fill/deviation report, and review memo for the same trade date |
| Launch data readiness | Required ETF datasets are `initial-focus` or `stable`; promotion status is `ready`, `promoted`, or not applicable; blocked datasets explain exact missing evidence |
| Signal credibility | Signal package includes factor IDs, factor values, selection reasons, risk flags, dataset snapshots, checksum, and deterministic replay proof |
| Portfolio credibility | Proposed weights satisfy max weight, max positions, tradability/liquidity, turnover, and one optimizer objective or fallback path |
| Risk credibility | Risk report shows concentration, active weights, drawdown, tail risk or stress proxy, and explicit blocking/warning flags |
| Manual execution credibility | Fills and positions persist; deviation report links target, actual, unfilled targets, and current weights |
| Stock-selection beta | Stock/fundamental/valuation datasets have PIT evidence, real-data E2E, promotion history, and at least one end-to-end signal package without hidden experimental bypass |
| Paper trading | Account snapshot, order state, fills, reconciliation report, repair approval state, and audit events are visible in one workflow |
| AI read-only copilot | Answers cite Ditto artifact IDs, refuse missing evidence, separate experimental from promoted data, and perform no writes |
| AI research agent | Every generated hypothesis has data scope, PIT check, expression diff, factor report, backtest report, and human promotion gate |

### Defer List

These should be intentionally deferred until the earlier boundary is real:

- Real broker live trading adapters and live order submission.
- Autonomous trading agents.
- Multi-asset global coverage beyond A-share ETF/stock focus.
- Intraday execution algorithms unless V3 paper operations require them.
- Deep RL, broad model zoo, or large-scale AutoML before the factor/backtest loop is productized.
- Full OpenBB-style workspace clone inside this backend repo.
- Multi-user SaaS permissions beyond the minimum needed for API safety.
- More execution/reconciliation edge cases unless they improve the paper daily loop.
- Additional data-source abstractions without concrete launch-dataset evidence.
- New architecture layers that do not feed the Daily Quant Operating Loop.

### How To Decide Future Work

Future issues should answer four questions before implementation:

1. Which stage boundary does this improve?
2. Which daily loop artifact does it change?
3. What evidence will prove it is usable, not just implemented?
4. What should now be removed, deferred, or hidden from the user?

This is the simplest way to keep the long-term full-stack ambition without letting the platform become a museum of unfinished capability.

## Final Recommendation

Ditto should not shrink its ambition. It should shrink its next promise.

The source-level evidence supports a confident but staged positioning. The platform foundation is strong enough to sustain a top personal quant system over time. The industry gap is not primarily "bad architecture" or "not enough code." It is functional closure: portfolio construction, attribution, daily workflow ergonomics, real-data promotion, paper-account operations, and AI/Agent productization.

The most important strategic move is to declare V1 as the target:

> A daily ETF decision cockpit with governed data readiness, deterministic signals, constrained target portfolio, risk review, manual execution tracking, deviation reporting, and artifact-citing read-only AI explanations.

Once that version is genuinely pleasant to use, stock-selection beta, optimizer depth, paper trading, and supervised AI research can compound naturally. Until then, more long-tail platform features will make the system more impressive in source code while not making it more useful in daily life.

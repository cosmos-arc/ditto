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

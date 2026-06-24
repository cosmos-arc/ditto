# Ditto System Positioning Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a source-grounded strategic assessment that clarifies Ditto's long-term full-stack quant platform positioning, current usable version boundary, engineering gap, industry gap, and AI/Agent-native gap.

**Architecture:** This is a documentation and research deliverable, not a code change. The only intended product artifact is `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`; supporting evidence comes from the existing source tree, committed acceptance artifacts, historical reviews, and official external documentation. Keep claims evidence-backed and separate current, next-phase, and long-term scope.

**Tech Stack:** Markdown, git, `rg`, `sed`, `find`, `wc`, pixi validation commands, official web documentation for industry and AI/Agent benchmarks.

---

## File Map

- Create: `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`
  - Owns the final strategic assessment.
  - Contains executive summary, fact base, L0-L4 maturity, functional gap, AI/Agent gap, architecture assessment, industry benchmark matrix, repositioning recommendation, roadmap, and defer list.
- Read: `docs/superpowers/specs/2026-06-24-ditto-system-positioning-assessment-design.md`
  - Source of approved scope, stage model, scoring dimensions, and required AI/Agent coverage.
- Read: `CLAUDE.md`, `AGENTS.md`, `docs/architecture/agent-context-pack.md`, `docs/architecture/boundaries-and-abstraction-standards.md`
  - Project rules and package boundary model.
- Read: `docs/architecture/capability-maturity.md`, `docs/acceptance/rc1-release-checklist.md`, `artifacts/acceptance/rc1-report.json`
  - Current maturity and release evidence.
- Read: `docs/reviews/2026-06-14-production-readiness-eval.md`, `docs/reviews/2026-06-16-quality-eval.md`, older benchmark reports under `docs/reviews/`
  - Historical context to update, confirm, or correct.
- Read: selected files under `packages/`
  - Source evidence for data, factor, strategy, backtest, portfolio, risk, execution, apps, application, and AI-readiness surfaces.
- Do not touch: `docs/plans/2026-06-24-strategic-positioning-and-functional-gap-analysis.md`
  - It is an unrelated untracked file at plan creation time.

## Task 1: Build The Evidence Frame

**Files:**
- Create: `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`
- Read: `docs/superpowers/specs/2026-06-24-ditto-system-positioning-assessment-design.md`
- Read: `CLAUDE.md`
- Read: `docs/architecture/agent-context-pack.md`
- Read: `docs/architecture/boundaries-and-abstraction-standards.md`
- Read: `artifacts/acceptance/rc1-report.json`

- [ ] **Step 1: Confirm clean scope**

Run:

```bash
git status --short
```

Expected:

```text
?? docs/plans/2026-06-24-strategic-positioning-and-functional-gap-analysis.md
```

If other files appear, inspect them and do not include unrelated paths in this assessment.

- [ ] **Step 2: Re-read approved design**

Run:

```bash
sed -n '1,280p' docs/superpowers/specs/2026-06-24-ditto-system-positioning-assessment-design.md
```

Expected: the output includes the L0-L4 model, AI/Agent-native layer, scoring dimensions, source verification plan, and target report path.

- [ ] **Step 3: Capture source and test scale**

Run:

```bash
find packages/*/src -type f -name '*.py' -print0 | xargs -0 wc -l | tail -n 1
find packages/*/tests -type f -name '*.py' -print0 | xargs -0 wc -l | tail -n 1
find packages/*/src -type f -name '*.py' | wc -l
find packages/*/tests -type f -name '*.py' | wc -l
```

Expected: four numeric outputs. Record them in the report as approximate source/test scale.

- [ ] **Step 4: Capture package distribution**

Run:

```bash
find packages/*/src -type f -name '*.py' -print0 | xargs -0 wc -l | awk '/packages\// {split($2,a,"/"); sum[a[2]]+=$1; files[a[2]]++} END {for (p in sum) printf "%s %d files %d loc\n", p, files[p], sum[p]}' | sort
find packages/*/tests -type f -name '*.py' -print0 | xargs -0 wc -l | awk '/packages\// {split($2,a,"/"); sum[a[2]]+=$1; files[a[2]]++} END {for (p in sum) printf "%s %d files %d loc\n", p, files[p], sum[p]}' | sort
```

Expected: package-level file and LOC distribution for src and tests. Use it to identify concentration in `data`, `application`, `apps`, and `features`.

- [ ] **Step 5: Create the initial report with fact base**

Create `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md` with these completed sections:

```markdown
# Ditto System Positioning Assessment

> Date: 2026-06-24
> Scope: backend monorepo at `/home/chevy/projects/ditto`
> Method: source-level inspection, committed acceptance evidence, historical review reconciliation, and official industry benchmark references.

## Executive Summary

Ditto should remain a long-term full-stack personal quant platform, but its next usable boundary should be stated as a staged platform rather than a fully live-trading product. The current source tree shows a strong engineering and architecture foundation, a credible daily research/backtest/signals backend, and extensive execution/reconciliation primitives. The main strategic risk is target drift: large amounts of backend machinery exist before the daily user workflow is simple, real-data-proven, and AI/Agent-friendly.

## Current System Fact Base

### Repository Scale

Record the source/test file counts and LOC values gathered in Task 1. Summarize that Ditto is a mature backend codebase, not a prototype.

### Architecture Frame

Summarize the 12-package model from `CLAUDE.md` and `agent-context-pack.md`: `apps -> application -> capability packages -> kernel`, with `platform` as horizontal infrastructure.

### Current Acceptance Evidence

Summarize `artifacts/acceptance/rc1-report.json`: `pixi run -e dev check` passed in the recorded artifact, targeted synthetic golden tests passed, and real-data/promotion evidence must still be distinguished from synthetic evidence.

### Assessment Principle

State that this report does not equate code volume with product readiness. A capability is treated as usable only when it has a coherent workflow, evidence, and a clear stage boundary.
```

Before committing this task, convert the "Repository Scale" text into concrete numbers from Steps 3-4.

- [ ] **Step 6: Verify no unresolved markers**

Run:

```bash
rg -n "T[B]D|TO[D]O|待[定]|FIXM[E]|f[i]ll in|Repository Scale text" docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
```

Expected: no matches.

- [ ] **Step 7: Commit the fact base**

Run:

```bash
git add docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
git commit -m "docs: add ditto positioning assessment fact base"
```

Expected: commit succeeds. If the shell cannot find `pre-commit`, run:

```bash
pixi run -e dev git commit -m "docs: add ditto positioning assessment fact base"
```

## Task 2: Audit L0-L4 Current Maturity From Source

**Files:**
- Modify: `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`
- Read: `docs/architecture/capability-maturity.md`
- Read: `packages/backtest/src/ditto_backtest/data_feed.py`
- Read: `packages/application/src/ditto_application/processes/execution/factor_bridge.py`
- Read: `packages/application/src/ditto_application/processes/execution/fundamental_snapshot.py`
- Read: `packages/application/src/ditto_application/processes/execution/classification_snapshot.py`
- Read: `packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py`
- Read: `packages/apps/tests/integration/test_stock_selection_golden_e2e.py`
- Read: `packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py`

- [ ] **Step 1: Inspect stage evidence**

Run:

```bash
sed -n '60,120p' docs/architecture/capability-maturity.md
sed -n '1,220p' packages/application/src/ditto_application/processes/execution/fundamental_snapshot.py
sed -n '260,460p' packages/application/src/ditto_application/processes/execution/factor_bridge.py
sed -n '1,220p' packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py
sed -n '1,260p' packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py
```

Expected: source confirms stock/fundamental/macro data remain experimental unless promoted, fundamental snapshot injection exists, factor-aware bundle enriches current-day market data, manual signal-fill-deviation integration exists, and real-data stock-selection E2E is token-dependent.

- [ ] **Step 2: Add five-stage maturity section**

Append this section to the report, replacing each bracketed evidence phrase with concrete source-backed wording from Step 1:

```markdown
## Five-Stage Maturity Assessment

| Stage | Current Rating | Usable Boundary | Main Gap |
|---|---|---|---|
| L0 Engineering and architecture foundation | ready | Strong enough to sustain a long-term platform if scope is controlled. | Observability/security/product workflow polish still lag architecture quality. |
| L1 Daily research and backtesting | partial-ready | ETF daily research/backtest is the cleanest current boundary; stock selection is source-supported but production maturity depends on real data promotion. | Real-data catalog/promotion evidence and repeatable user workflow remain weaker than synthetic proof. |
| L2 Portfolio and signal decision | partial | Signal package, reasons, risk checks, and manual intents exist as backend workflow pieces. | Portfolio optimization, richer attribution, and daily operator UX are incomplete. |
| L3 Semi-automated trading operations | experimental-partial | Manual fill, stored positions, deviation report, audit and reconciliation primitives exist. | Paper/live operational workflow is not yet a daily account-management product. |
| L4 Full-stack live platform | experimental-reserved | Protocols, paper gateway, recording, reconciliation and repair seams exist. | Real broker gateway, streaming data, continuous risk, permissions, disaster recovery and live ops are long-term work. |

### L0 Engineering And Architecture Foundation

Summarize package boundaries, tests, import-linter, type/lint gates and the risk of complexity concentration.

### L1 Daily Research And Backtesting

State that the old fundamental-factor-backtest gap is partly corrected by the `fundamental_snapshot` and `factor_bridge` paths. Separate this from production credibility, because real-data promotion and full launch dataset evidence are still harder than synthetic golden evidence.

### L2 Portfolio And Signal Decision

Explain that signal packages, target weights, selection reasons and launch risk reports exist, but robust portfolio optimization and decision UX are still incomplete.

### L3 Semi-Automated Trading Operations

Explain the manual signal -> fill -> position -> deviation lane and the extensive reconciliation machinery. Mark it as operationally promising but not yet a polished daily account loop.

### L4 Long-Term Full-Stack Live Platform

Explain that broker protocols, paper gateway, recording and reconciliation are valuable future foundations, but real broker adapters and live trading controls remain outside the current usable boundary.
```

Do not leave bracketed text in the report. Keep the stage ratings exactly as written unless source evidence contradicts them.

- [ ] **Step 3: Verify stage coverage**

Run:

```bash
rg -n "L0|L1|L2|L3|L4|fundamental_snapshot|factor_bridge|manual signal|real-data" docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
```

Expected: matches in the five-stage section and fact base.

- [ ] **Step 4: Commit stage assessment**

Run:

```bash
git add docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
git commit -m "docs: add staged ditto maturity assessment"
```

Expected: commit succeeds.

## Task 3: Assess Functional Completeness And User-Ready Workflows

**Files:**
- Modify: `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`
- Read: `README.md`
- Read: `docs/reviews/2026-06-14-production-readiness-eval.md`
- Read: `docs/reviews/2026-06-16-quality-eval.md`
- Read: `packages/portfolio/src/ditto_portfolio/rebalancing`
- Read: `packages/risk/src/ditto_risk`
- Read: `packages/features/src/ditto_features/evaluation`
- Read: `packages/apps/src/ditto_apps/cli/commands/strategy.py`
- Read: `packages/apps/src/ditto_apps/cli/commands/ops.py`

- [ ] **Step 1: Search functional gaps**

Run:

```bash
rg -n "mean_variance|risk_parity|Black|optimizer|optimization|cvxpy|scipy|brinson|attribution|VaR|CVaR|walk|optuna|grid" packages docs/reviews docs/operations -g '*.py' -g '*.md'
rg -n "publish-signals|factor-ic|allow_experimental_data|promotion|deviation|launch risk" packages/apps packages/application packages/risk -g '*.py'
```

Expected: the first command shows optimization and advanced attribution mostly in docs or limited evaluation utilities; the second command shows real backend surfaces for signals, factor IC, maturity gates, deviation and launch risk.

- [ ] **Step 2: Add functional frontier section**

Append this section to the report:

```markdown
## Functional Frontier And Completeness

| Domain | Current Strength | Missing For Top-Tier Personal Platform | Stage |
|---|---|---|---|
| Data and governance | Strong catalog, maturity, promotion, lineage, PIT and source-health machinery. | Full launch dataset promotion evidence, multi-source redundancy, simpler operator workflow. | L0-L1 |
| Factor research | Strong expression compiler, PIT-aware codegen patterns, IC diagnostics and production guard. | Broader production factor registry, materialized intermediate workflow for unsafe nested factors, AI-assisted experiment loop. | L1 |
| Strategy and backtest | ETF daily path and synthetic stock-selection path are credible; fundamental snapshot path now exists. | Real-data stock-selection release evidence, more complete reports, parameter and walk-forward validation. | L1 |
| Portfolio and allocation | Target portfolios, simple allocators, constraints and risk checks exist. | Mean-variance, HRP/risk parity, Black-Litterman or another robust optimizer are not present as production code. | L2 |
| Risk | Pre/post checks and launch risk report exist. | Continuous risk gate, VaR/CVaR/ES, stress testing and live alerting are incomplete. | L2-L4 |
| Execution and operations | Manual signal-fill-deviation lane, paper/recording gateway and reconciliation repair primitives are strong. | Real broker integration, live account workflow, permissions, disaster recovery, and operator cockpit are not current-ready. | L3-L4 |
| Analysis and attribution | Factor evaluation has attribution utilities. | Portfolio-level Brinson, factor attribution to P&L, cost attribution and explainable daily review are not user-ready. | L1-L2 |

### User-Ready Workflow Judgment

State the current most credible workflow as: daily ETF and research/backtest/signals backend, with stock-selection moving from synthetic proof toward real-data proof. State that the system is not yet a smooth daily personal cockpit because data promotion, report interpretation, AI assistance, and operations UX require too much manual backend knowledge.
```

Adjust the table only where source inspection shows stronger or weaker evidence.

- [ ] **Step 3: Verify no false claims about optimizers**

Run:

```bash
rg -n "Mean-variance|HRP|Black-Litterman|optimizer|Brinson|VaR|CVaR" docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
```

Expected: the report describes these as missing, limited, or future unless source code proves otherwise.

- [ ] **Step 4: Commit functional section**

Run:

```bash
git add docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
git commit -m "docs: assess ditto functional completeness"
```

Expected: commit succeeds.

## Task 4: Add Official Industry Benchmark Gap Matrix

**Files:**
- Modify: `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`
- Read: official documentation or primary project pages for QuantConnect LEAN, NautilusTrader, Microsoft Qlib, RD-Agent, OpenBB, PyPortfolioOpt, vectorbt, VeighNa, RiceQuant, JoinQuant, and TradingAgents.

- [ ] **Step 1: Gather official sources**

Use web search and official docs. Prefer official project documentation, GitHub repositories, or vendor docs. Collect links for:

```text
QuantConnect LEAN Algorithm Framework, portfolio construction, risk management, execution, live trading, optimization, AI assistance or MCP surfaces.
NautilusTrader backtesting/live trading architecture, event-driven model, adapters, order model.
Microsoft Qlib workflow, data, model, backtest, evaluation, RD-Agent.
OpenBB Platform and Copilot or AI/data platform surfaces.
PyPortfolioOpt efficient frontier, Black-Litterman, HRP.
vectorbt research/backtesting speed and portfolio simulation.
VeighNa event engine, gateway ecosystem, CTA/portfolio apps.
RiceQuant and JoinQuant A-share fundamentals, research, industry data, strategy APIs.
TradingAgents multi-agent financial research/trading framework.
```

Expected: at least one official or primary source per benchmark family. If a Chinese commercial platform has limited accessible official detail, state that the comparison uses public docs and source-visible API patterns.

- [ ] **Step 2: Add benchmark matrix**

Append this section to the report:

```markdown
## Industry Benchmark Gap Matrix

| Benchmark | What It Represents | Ditto Advantage | Ditto Gap | Stage Assignment |
|---|---|---|---|---|
| QuantConnect LEAN | Mature full-stack research/backtest/live platform. | Ditto has stricter local architecture boundaries and A-share/PIT-specific backend governance. | LEAN is far ahead in integrated live trading, cloud workflow, optimization, product UX and mature algorithm framework ecosystem. | L2-L4 |
| NautilusTrader | Event-driven, high-performance backtest/live trading engine. | Ditto is more specialized for A-share daily PIT governance and personal backend workflows. | NautilusTrader is ahead in event-driven live/backtest consistency, order/data model depth and production trading orientation. | L4 |
| Qlib and RD-Agent | Quant research workflow and AI-assisted R&D direction. | Ditto has stronger custom backend governance and A-share trading-rule emphasis. | Qlib/RD-Agent are ahead in model/experiment workflow and AI-assisted research iteration. | L1 and AI |
| RiceQuant and JoinQuant | China-market research platform usability and data breadth. | Ditto owns its architecture and can enforce PIT/maturity policy more explicitly. | They are ahead in immediately usable A-share data, fundamentals, industry classification and researcher experience. | L1-L2 |
| VeighNa | Domestic live trading gateway ecosystem. | Ditto has cleaner research/data governance and stronger typed backend boundaries. | VeighNa is ahead in gateway ecosystem, event engine and practical live connectivity. | L4 |
| PyPortfolioOpt and vectorbt | Focused optimizer and fast research tools. | Ditto integrates data governance, strategy, risk and execution primitives in one backend. | They are ahead in portfolio optimization breadth or fast exploratory research ergonomics. | L1-L2 |
| OpenBB | Financial data platform and AI-assisted research experience. | Ditto is more domain-specific to A-share quant workflows. | OpenBB is ahead in data connectivity, interactive research UX and AI/Copilot-facing surfaces. | AI and L1 |
```

After the table, add a short "Interpretation" paragraph: Ditto should not copy every benchmark; it should prioritize the gaps that make the next stage usable.

- [ ] **Step 3: Add source links**

Add a `Sources` subsection with bullet links grouped by benchmark. Each bullet must include the source name and URL. Keep quotes short and paraphrase claims.

- [ ] **Step 4: Commit benchmark section**

Run:

```bash
git add docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
git commit -m "docs: add industry benchmark gap matrix"
```

Expected: commit succeeds.

## Task 5: Add AI/Agent-Native Readiness Assessment

**Files:**
- Modify: `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`
- Read: `docs/architecture/capability-maturity.md`
- Read: `packages/application/src/ditto_application/queries`
- Read: `packages/apps/src/ditto_apps/api`
- Read: `packages/apps/src/ditto_apps/cli`
- Read: `packages/application/src/ditto_application/processes/execution/signal_package.py`
- Read: `packages/execution/src/ditto_execution/audit`

- [ ] **Step 1: Inspect AI-readable backend surfaces**

Run:

```bash
find packages/application/src/ditto_application/queries -maxdepth 1 -type f -name '*.py' | sort
find packages/apps/src/ditto_apps/api/routes -maxdepth 1 -type f -name '*.py' | sort
rg -n "artifact|lineage|report|signal|deviation|promotion|remediation|maturity|OpenAPI|operationId|x-ditto-maturity" packages/application packages/apps packages/execution -g '*.py'
```

Expected: query facades, route DTOs, lineage/report/signal/promotion/remediation surfaces exist and can become agent-readable context.

- [ ] **Step 2: Add AI/Agent section**

Append this section to the report:

```markdown
## AI/Agent-Native Gap Assessment

### Current AI-Native Assets

Ditto already has unusually good backend evidence for future agents: catalog maturity, promotion evidence, lineage, source-health reports, run artifacts, backtest reports, signal packages, execution audit and remediation records. These are better raw materials for grounded agents than a system that only stores notebooks and logs.

### Current AI-Native Gaps

| Agent Role | Current Readiness | Main Gap | Safety Boundary |
|---|---|---|---|
| Engineering Agent | partial | Codebase has strong checks, but no dedicated agent tool layer that exposes architecture checks, failing tests and remediation context as structured tools. | Agent may propose and verify changes, but commits remain reviewed. |
| Research Agent | partial | Factor reports and backtests exist, but no first-class hypothesis -> experiment -> report -> candidate loop. | Agent can recommend experiments; promotion requires human approval. |
| Decision Agent | experimental-partial | Signal reasons and risk flags exist, but no conversational daily decision surface. | Agent explains signals; it does not authorize trades. |
| Operations Agent | partial | Catalog remediation, maturity and source-health data exist, but no agent workflow turns them into prioritized operator actions. | Agent can draft remediation actions; approval gates stay mandatory. |
| Live Trading Agent | reserved | Live broker integration is not current scope. | Agent must never place unsupervised live orders. |

### AI/Agent Benchmark Gap

QuantConnect, OpenBB, Qlib/RD-Agent and TradingAgents show that the frontier is moving from "tool with APIs" to "agentic research and operations loop." Ditto's backend evidence model is promising, but it needs an explicit tool protocol, agent-safe command surface, report citations, and human approval workflow before AI becomes a real product advantage.

### Near-Term AI Opportunity

The highest-value AI scope is not autonomous trading. It is a grounded research and operations copilot that can answer: what data is stale, why a dataset is blocked, why a stock was selected, what changed since the last run, what validation failed, and what experiment should be run next.
```

- [ ] **Step 3: Verify AI section exists and avoids autonomous trading**

Run:

```bash
rg -n "AI/Agent|Engineering Agent|Research Agent|Decision Agent|Operations Agent|Live Trading Agent|unsupervised live orders|autonomous trading" docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
```

Expected: matches show AI is a first-class section and live trading autonomy is explicitly rejected.

- [ ] **Step 4: Commit AI section**

Run:

```bash
git add docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
git commit -m "docs: assess ditto ai agent readiness"
```

Expected: commit succeeds.

## Task 6: Assess Architecture Cleanliness And Target Drift

**Files:**
- Modify: `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`
- Read: `docs/reviews/2026-06-16-quality-eval.md`
- Read: `docs/architecture/boundaries-and-abstraction-standards.md`
- Read: `scripts/architecture/check_architecture_smells.py`
- Read: package-level `CLAUDE.md` files as needed.

- [ ] **Step 1: Gather architecture quality evidence**

Run:

```bash
sed -n '1,220p' docs/reviews/2026-06-16-quality-eval.md
find packages/*/src -type f -name '*.py' -print0 | xargs -0 wc -l | sort -nr | sed -n '1,30p'
rg -n "TYPE_CHECKING|import pandas|type: ignore|import \\*" packages/*/src -g '*.py'
rg -n "broker|reconciliation|repair|fallback|remediation|promotion|maturity" docs/architecture/capability-maturity.md
```

Expected: quality eval reports strong code/architecture/test scores; largest files cluster in application/apps/data/backtest; forbidden patterns are absent or limited; capability maturity shows heavy execution/reconciliation and catalog governance investment.

- [ ] **Step 2: Add architecture and drift section**

Append this section to the report:

```markdown
## Architecture Cleanliness And Target Drift

### What Is Excellent

Ditto's package model, import-linter contracts, type discipline, no-pandas rule, PIT culture and test volume are unusually strong for a personal quant platform. The architecture is capable of supporting long-term full-stack ambitions.

### What Is Risky

The architecture is now strong enough that the main risk is no longer "can the system scale technically." The main risk is that architecture becomes a substitute for product closure. Heavy investment in execution reconciliation, catalog remediation and governance can be justified for L3-L4, but it should not keep outranking the daily L1-L2 user workflow.

### Complexity Concentration

Discuss concentration in `data`, `application`, `apps` and long query/process files. Explain whether this is acceptable domain weight or a sign that read models/process orchestration need more focused extraction.

### Architecture Verdict

State that the architecture should be preserved, not simplified into a toy system. The next phase should use that architecture to close daily research-decision-operations workflows, not expand every long-term subsystem equally.
```

- [ ] **Step 3: Verify target drift language**

Run:

```bash
rg -n "target drift|product closure|execution reconciliation|catalog remediation|Architecture Verdict|Complexity Concentration" docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
```

Expected: matches in the architecture section.

- [ ] **Step 4: Commit architecture section**

Run:

```bash
git add docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
git commit -m "docs: assess architecture drift risk"
```

Expected: commit succeeds.

## Task 7: Write Repositioning Recommendation And Roadmap

**Files:**
- Modify: `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`
- Read: all sections already written in the report.

- [ ] **Step 1: Add repositioning recommendation**

Append this section to the report:

```markdown
## Repositioning Recommendation

### Long-Term Identity

Ditto should remain a personal full-stack quant platform for A-share ETF, stock and macro workflows. Its distinguishing identity should be: evidence-grounded, PIT-safe, strongly typed, AI-agent-ready, and optimized for disciplined daily research-to-decision operations.

### Current Best Version Label

The most honest current label is:

**V1 Backend: daily research/backtest/signal-decision platform with experimental operations and live-trading foundations.**

This is stronger than a research script library and weaker than a live full-stack trading platform.

### Next Phase Boundary

The next phase should be:

**V1.1: AI-assisted daily research-to-signal operations loop.**

The release boundary should require:

- Real-data launch dataset evidence for the chosen daily workflow.
- One clear daily command/API path from data freshness -> factor/strategy evaluation -> signal package -> risk/deviation review.
- A first agent-readable context layer over catalog status, factor reports, backtest reports and signal reasons.
- Fewer new long-term execution features unless they directly support the L3 manual/paper operations loop.
```

- [ ] **Step 2: Add P0/P1/P2 roadmap**

Append this section:

```markdown
## Next-Phase Roadmap

### P0: Clarify And Prove The Daily Workflow

1. Make the daily A-share ETF/stock research-to-signal workflow one documented operator lane.
2. Complete or explicitly narrow real-data promotion evidence for launch datasets used by that lane.
3. Produce one report/API/CLI path that explains candidates, weights, factor reasons, risk flags, and signal-vs-fill deviation.
4. Add an agent-readable evidence endpoint or command group for "what should I look at today".

### P1: Upgrade Decision Quality

1. Add a modest portfolio optimizer or robust allocation module suitable for personal daily use.
2. Add portfolio-level attribution and factor/cost explanation tied to signal packages and backtest runs.
3. Add parameter stability, out-of-sample, or walk-forward validation for promoted strategy templates.
4. Add source redundancy where it directly protects the daily workflow.

### P2: Prepare For True Full-Stack Live Platform

1. Define the live broker adapter boundary and approval model before adding real broker credentials or SDKs.
2. Convert paper trading into a daily operations product rather than only protocol evidence.
3. Add continuous risk and alerting after manual/paper operations are smooth.
4. Add permissions, incident logs, backup/restore drills and security hardening before live trading.

## Stop-Doing Or Defer List

- Do not proactively expand broker repair/conformance matrices unless tied to a concrete L3/L4 acceptance need.
- Do not add more catalog governance surfaces without reducing daily operator friction.
- Do not pursue intraday/high-frequency or broad multi-asset support in the next phase.
- Do not build autonomous trading agents. Build grounded advisory agents first.
- Do not treat synthetic golden success as production proof for real-data stock selection.
```

- [ ] **Step 3: Add final executive summary refinement**

Return to the top `Executive Summary` and add 5 bullets:

```markdown
- Current best version label: V1 Backend daily research/backtest/signal-decision platform.
- Most usable current workflow: ETF daily research/backtest and backend signal-decision flow.
- Most important partial workflow: A-share stock selection with fundamental snapshot support, still needing stronger real-data and promotion evidence.
- Biggest strategic risk: target drift toward L4 machinery before L1-L2 daily usability is obvious.
- Highest-value AI direction: grounded research/operations copilot, not autonomous trading.
```

Keep this summary consistent with the body.

- [ ] **Step 4: Commit recommendation and roadmap**

Run:

```bash
git add docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
git commit -m "docs: recommend ditto next platform boundary"
```

Expected: commit succeeds.

## Task 8: Final Verification And Report Self-Review

**Files:**
- Modify: `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md` if review finds issues.
- Read: `docs/superpowers/specs/2026-06-24-ditto-system-positioning-assessment-design.md`

- [ ] **Step 1: Check spec coverage**

Run:

```bash
rg -n "Executive Summary|Current System Fact Base|Five-Stage Maturity|Functional Frontier|AI/Agent-Native|Architecture Cleanliness|Industry Benchmark|Repositioning Recommendation|Next-Phase Roadmap|Stop-Doing" docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
```

Expected: every required report section appears.

- [ ] **Step 2: Check no unresolved markers or ambiguous scaffolding**

Run:

```bash
rg -n "T[B]D|TO[D]O|待[定]|FIXM[E]|f[i]ll in|simil[a]r to|empty marker" docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
```

Expected: no matches. If the scan catches maturity wording that only describes a reserved namespace, rewrite it as "reserved namespace" to keep the report clean.

- [ ] **Step 3: Check source distinction language**

Run:

```bash
rg -n "synthetic|real-data|promotion|PIT|AI|Agent|autonomous|L4" docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
```

Expected: the report distinguishes synthetic from real-data evidence, includes PIT and promotion, covers AI/Agent, rejects autonomous live trading, and assigns live platform gaps to L4.

- [ ] **Step 4: Run markdown-safe git check**

Run:

```bash
git diff --check
pixi run -e dev pre-commit run --files docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
```

Expected: no whitespace errors and pre-commit passes for the markdown file.

- [ ] **Step 5: Commit final review fixes if any**

If Step 2 or Step 4 required edits, run:

```bash
git add docs/reviews/2026-06-24-ditto-system-positioning-assessment.md
git commit -m "docs: polish ditto positioning assessment"
```

Expected: commit succeeds. If no edits were needed, do not create an empty commit.

- [ ] **Step 6: Report final status**

Run:

```bash
git status --short
git log --oneline -8
```

Expected: only unrelated untracked files remain, especially `docs/plans/2026-06-24-strategic-positioning-and-functional-gap-analysis.md` if it was still present at task start. Summarize the report path and latest relevant commits to the user.

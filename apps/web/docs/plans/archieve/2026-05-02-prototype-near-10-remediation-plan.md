# Prototype Near-10 Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 `prototype/` 全量 27 个 active route prototypes 从 8.7/10 推进到接近 10 分的专业量化工作台候选版。

**Architecture:** 先把“接近 10 分”定义成可测试合同，再按页面族修复。共享底线进入 `scripts/` 与 `shared/`；页面业务判断留在对应 `page-*.html`；跨页规范同步写回 `design/specs/`，避免原型、合同、规范三套语言分叉。

**Tech Stack:** HTML prototypes, shared prototype CSS/JS, Design Tokens, Vitest, JSDOM, Playwright, Bun, Biome.

---

## Context

本计划基于 2026-05-02 当前评审结果：

- 27/27 active prototypes 覆盖，`page-home.html` 已纳入。
- `page-home.html` 当前已有唯一 `h1`、唯一 Primary Answer、无横向溢出，主动作 `复核信号` 为 72x28px。
- 26 个非 home 页面已生成评审截图与结构指标：
  - `test-results/prototype-review-current/contact-sheet-standard.png`
  - `test-results/prototype-review-current/structure-metrics.json`
- Home 单页指标：
  - `test-results/prototype-review-current-home/home-standard.png`
  - `test-results/prototype-review-current-home/home-structure-metrics.json`

当前总体判断：

| Dimension | Baseline | Near-10 Target |
|---|---:|---:|
| 决策清晰度 | 8.2 | 9.7 |
| 信息密度 | 8.8 | 9.6 |
| 专业工作台感 | 8.9 | 9.7 |
| 功能完整性 | 8.4 | 9.5 |
| 交互可用性 | 7.7 | 9.5 |
| 跨页一致性 | 9.0 | 9.7 |

参考标准：

- W3C WCAG 2.2 Target Size Minimum: pointer targets should be at least 24x24 CSS pixels or have a documented spacing/equivalent exception.
- W3C WCAG 2.2 Use of Color: business state cannot depend on color alone.
- Nielsen Norman Group usability heuristics: visibility of system status, match with user mental model, recognition over recall, and efficiency of use.

## Scope

Active prototype files:

- `prototype/page-home.html`
- `prototype/page-cross-market.html`
- `prototype/page-a-shares.html`
- `prototype/page-markets-intelligence.html`
- `prototype/page-markets-screener.html`
- `prototype/page-markets-calendar.html`
- `prototype/page-watchlist.html`
- `prototype/page-instrument-hub.html`
- `prototype/page-research.html`
- `prototype/page-regime-monitor.html`
- `prototype/page-factor-analysis.html`
- `prototype/page-factor-list.html`
- `prototype/page-strategy-list.html`
- `prototype/page-strategies-detail.html`
- `prototype/page-strategy-studio.html`
- `prototype/page-backtest-list.html`
- `prototype/page-backtest-result.html`
- `prototype/page-experiment-list.html`
- `prototype/page-universe-list.html`
- `prototype/page-trading-overview.html`
- `prototype/page-portfolio.html`
- `prototype/page-orders-ledger.html`
- `prototype/page-signals-inbox.html`
- `prototype/page-risk-center.html`
- `prototype/page-platform.html`
- `prototype/page-agent-console.html`
- `prototype/page-platform-settings.html`

Shared and test files:

- `prototype/shared/layout-base.css`
- `prototype/shared/prototype-interactions.js`
- `prototype/tokens-style.css`
- `scripts/prototype-design-consistency.test.ts`
- `scripts/prototype-interaction-ux-contract.test.ts`
- `scripts/page-home-prototype.test.ts`
- `scripts/run-prototype-gates.ts`
- `design/specs/04_interaction_state_spec.md`
- `design/specs/11_ditto_page_pattern_library.md`
- `design/specs/12_ditto_data_views_spec.md`
- `design/specs/20_interaction_ux_audit.md`

Out of scope:

- New dependencies.
- React implementation parity work in `src/`.
- IA route restructuring.
- CI/CD changes.
- Design Token semantic changes unless approved first.

## Approach Options

Recommended approach: contract-first remediation.

- Pros: prevents cosmetic fixes from weakening professional workflow; makes “near-10” measurable.
- Cons: slower first step because gates must be tightened before page edits.

Alternative 1: visual-first polish.

- Pros: fast visible improvement.
- Cons: likely repeats old cycle where pages look better but decision clarity remains uneven.

Alternative 2: rebuild prototypes by page family.

- Pros: strongest long-term consistency.
- Cons: too disruptive; high regression risk across 27 pages.

Decision: use contract-first remediation, then page-family upgrades.

## Definition Of Done

- `bun run check` passes.
- `bun run prototype:gates` passes for all active prototypes.
- `bun run prototype:interaction` passes.
- Every visible interactive target is at least 24px in both dimensions, or has a documented equivalent/spacing exception in test output.
- 27/27 pages expose one and only one Primary Answer.
- Every Primary Answer includes:
  - `data-answer-judgment`
  - `data-answer-metric`
  - at least two `data-answer-evidence`
  - one visible `data-answer-action`
  - an impact scope in visible copy or `aria-label`
- Home remains a true Global Command Center, not a dashboard card wall.
- Catalog pages are distinguishable in blind screenshot review by task, not only by title.
- AI / Agent / Command actions expose input, output, destination, and approval state.
- Updated specs match implemented prototype facts.

---

### Task 1: Add Near-10 Audit Gates

**Files:**

- Modify: `scripts/prototype-design-consistency.test.ts`
- Modify: `scripts/prototype-interaction-ux-contract.test.ts`
- Create: `scripts/prototype-near-10-contract.test.ts`
- Read: `prototype/.edition-manifest.json`
- Read: `test-results/prototype-review-current/structure-metrics.json`
- Read: `test-results/prototype-review-current-home/home-structure-metrics.json`

**Step 1: Add active page loader**

Create helpers in `scripts/prototype-near-10-contract.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../prototype");
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);

type ManifestPage = {
	id: string;
	file: string;
	shellFamily?: string;
};

type EditionManifest = {
	pages: ManifestPage[];
};

function readManifest(): EditionManifest {
	return JSON.parse(
		readFileSync(join(prototypesDir, ".edition-manifest.json"), "utf8"),
	) as EditionManifest;
}

function activePages(): ManifestPage[] {
	return readManifest().pages.filter(
		(page) =>
			page.file?.startsWith("page-") &&
			page.file.endsWith(".html") &&
			page.id !== "token-showcase" &&
			!archivedPrototypeIds.has(page.id),
	);
}

function readDocument(page: ManifestPage): Document {
	return new JSDOM(readFileSync(join(prototypesDir, page.file), "utf8")).window.document;
}
```

**Step 2: Add Primary Answer 2.0 tests**

Add tests:

```ts
describe("near-10 primary answer contract", () => {
	for (const page of activePages()) {
		it(`${page.id} exposes one complete primary answer`, () => {
			const document = readDocument(page);
			const answers = document.querySelectorAll(
				"[data-primary-answer], [data-primary-answer-equivalent]",
			);

			expect(answers, `${page.id}: expected exactly one primary answer`).toHaveLength(1);

			const answer = answers[0];
			expect(answer.querySelectorAll("[data-answer-judgment]").length).toBeGreaterThanOrEqual(1);
			expect(answer.querySelectorAll("[data-answer-metric]").length).toBeGreaterThanOrEqual(1);
			expect(answer.querySelectorAll("[data-answer-evidence]").length).toBeGreaterThanOrEqual(2);
			expect(answer.querySelectorAll("[data-answer-action]").length).toBeGreaterThanOrEqual(1);
			expect((answer.textContent ?? "").replace(/\s+/g, " ").trim().length).toBeGreaterThan(40);
		});
	}
});
```

Run:

```bash
bun test scripts/prototype-near-10-contract.test.ts
```

Expected: FAIL on pages whose current Primary Answer is too thin, such as `signals-inbox`, `cross-market`, `universe-list`, `regime-monitor`, and several Catalog pages.

**Step 3: Add target size audit**

In `scripts/prototype-interaction-ux-contract.test.ts`, add a Playwright test for visible interactive controls at `1366x768` and `1536x1080`.

Selectors:

```ts
const interactiveSelector = [
	"button",
	"a[href]",
	"[role='button']",
	"[role='tab']",
	"label[role='button']",
	"[data-answer-action]",
].join(",");
```

Fail when a visible target is smaller than 24x24 unless it has `data-target-size-exception`.

Run:

```bash
bun run prototype:interaction
```

Expected: FAIL on known small controls:

- `signals-inbox` scope status button.
- `trading-overview` day/week/month tabs.
- `regime-monitor` time buttons.
- multiple Catalog filter chips.
- `orders-ledger` strip actions.

**Step 4: Add counter fallback audit**

In `scripts/prototype-design-consistency.test.ts`, add a scan:

```ts
const counterElements = document.querySelectorAll("[data-counter]");
for (const element of counterElements) {
	const value = element.getAttribute("data-counter");
	const text = (element.textContent ?? "").trim();
	expect(text, `${page.id}: data-counter fallback must match ${value}`).toContain(value ?? "");
}
```

Allow formatting differences only with explicit `data-counter-fallback-exception`.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL on `page-regime-monitor.html` where a `data-counter="72"` element has fallback text `0%`.

**Step 5: Commit**

```bash
git add scripts/prototype-design-consistency.test.ts scripts/prototype-interaction-ux-contract.test.ts scripts/prototype-near-10-contract.test.ts
git commit -m "test(prototypes): add near-10 product quality gates"
```

---

### Task 2: Fix Interaction Target Size And Focus Baseline

**Files:**

- Modify: `prototype/shared/layout-base.css`
- Modify: `prototype/page-trading-overview.html`
- Modify: `prototype/page-signals-inbox.html`
- Modify: `prototype/page-orders-ledger.html`
- Modify: `prototype/page-risk-center.html`
- Modify: `prototype/page-regime-monitor.html`
- Modify: `prototype/page-markets-screener.html`
- Modify: `prototype/page-markets-calendar.html`
- Modify: `prototype/page-watchlist.html`
- Modify: `prototype/page-factor-list.html`
- Modify: `prototype/page-strategy-list.html`
- Modify: `prototype/page-backtest-list.html`
- Modify: `prototype/page-experiment-list.html`
- Modify: `prototype/page-universe-list.html`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Run failing target-size test**

Run:

```bash
bun run prototype:interaction
```

Expected: FAIL with visible controls below 24px.

**Step 2: Add shared compact hit-area utilities**

In `layout-base.css`, add utilities:

```css
.hit-target-24 {
  min-width: 24px;
  min-height: 24px;
}

.hit-target-y-24 {
  min-height: 24px;
}

.hit-target-inline-24 {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
}
```

Use these only where the existing local selector cannot be safely widened.

**Step 3: Fix known small controls**

Update local CSS selectors:

```css
.scope-status-item,
.order-tab,
.regime-time-btn,
.filter-chip,
.strip-action,
.trace-action-btn,
.health-summary-item,
.perf-item,
.backtest-summary-item,
.experiment-summary-item,
.batch-summary__hint {
  min-height: 24px;
}
```

Do not increase visual noise. Prefer vertical padding and line-height changes over larger borders.

**Step 4: Mark valid exceptions**

If a dense data visualization cell must remain below 24px, add:

```html
data-target-size-exception="dense-data-viz"
```

Only use this for true data-viz targets, not buttons, tabs, filters, or primary actions.

**Step 5: Re-run interaction tests**

Run:

```bash
bun run prototype:interaction
```

Expected: PASS.

**Step 6: Commit**

```bash
git add prototype/shared/layout-base.css prototype/page-*.html scripts/prototype-interaction-ux-contract.test.ts
git commit -m "fix(prototypes): normalize compact interaction targets"
```

---

### Task 3: Upgrade Home To Command Center 10 Candidate

**Files:**

- Modify: `prototype/page-home.html`
- Modify: `scripts/page-home-prototype.test.ts`
- Test: `test-results/prototype-review-current-home/home-structure-metrics.json`

**Step 1: Extend home tests**

In `scripts/page-home-prototype.test.ts`, assert:

- `data-primary-answer` includes before/after impact rows for concentration, VaR, and risk budget.
- `data-operating-summary` has at least 8 metrics.
- `data-worklist-row` has at least 6 rows with level, domain, object, impact, SLA, and action.
- `data-command-center-rail` has market pulse, global alerts, execution constraints, and data health.

Run:

```bash
bun run test:run scripts/page-home-prototype.test.ts
```

Expected: FAIL until the DOM exposes the explicit contract.

**Step 2: Add explicit home data attributes**

In `page-home.html`, annotate existing sections:

```html
<section data-operating-summary>
```

```html
<section data-primary-answer data-command-decision-card>
```

```html
<div data-decision-impact>
```

```html
<tr data-worklist-row>
```

```html
<aside data-command-center-rail>
```

**Step 3: Improve decision card copy**

Required visible content:

- Judgment: “优先复核贵州茅台卖出信号，组合回撤接近预警线。”
- Key metric: `VaR 95% -> 92%`
- Evidence:
  - `科技集中度 37.2% -> 34.8%`
  - `风险预算 21% -> 27%`
  - `预估冲击成本 ¥5.9K`
- Action: `复核信号`
- Scope: `全局账户 · 交易信号 · 风控集中度`
- Consequence: `交易后仍保留消费核心仓位`

**Step 4: Preserve compact viewport fit**

Run:

```bash
bun run prototype:gates -- --prototype prototype/page-home.html
```

Expected: PASS in standard, compact, and narrow default wrapper viewports.

**Step 5: Commit**

```bash
git add prototype/page-home.html scripts/page-home-prototype.test.ts
git commit -m "fix(prototypes): sharpen home command center decision flow"
```

---

### Task 4: Upgrade Radar And Analytical Primary Answers

**Files:**

- Modify: `prototype/page-cross-market.html`
- Modify: `prototype/page-a-shares.html`
- Modify: `prototype/page-markets-intelligence.html`
- Modify: `prototype/page-research.html`
- Modify: `prototype/page-trading-overview.html`
- Modify: `prototype/page-portfolio.html`
- Modify: `prototype/page-risk-center.html`
- Modify: `prototype/page-regime-monitor.html`
- Test: `scripts/prototype-near-10-contract.test.ts`

**Step 1: Run Primary Answer tests**

Run:

```bash
bun test scripts/prototype-near-10-contract.test.ts
```

Expected: FAIL on thin analytical strips.

**Step 2: Cross Market**

Upgrade `page-cross-market.html` Primary Answer from a 13px context strip into a compact radar readout:

- Judgment: `港股弹性领跑，黄金避险仍强，美元走弱支撑成长。`
- Metric: `强相关焦点 黄金 / 美元 -0.84`
- Evidence: `港股 +1.4%`, `黄金 +1.1%`, `DXY -0.4%`
- Action: `查看相关矩阵`
- Scope: `全球市场 · 1D · FOMC 前夜`

**Step 3: A Shares**

Keep the strong heatmap, but make the Primary Answer action more explicit:

- Action text: `查看 AI / 半导体主线`
- Add second action candidate as quiet text: `对比地产 / 银行拖累`
- Ensure the heatmap still includes non-color markers for direction.

**Step 4: Regime Monitor**

Fix the fallback:

```html
<span data-counter="72" data-counter-decimals="0" data-counter-suffix="%" data-answer-metric>72%</span>
```

Add decision consequence:

- `策略暴露建议：成长 +0.8，防御 -0.3`
- `若 IVIX > 22，切换为 Mixed watch`

**Step 5: Trading / Portfolio / Risk**

Make each Primary Answer answer “next action”:

- `trading-overview`: signal review vs order execution priority.
- `portfolio`: attribution problem and rebalance consequence.
- `risk-center`: closest risk limit and exact de-risk action.

**Step 6: Re-run tests**

Run:

```bash
bun test scripts/prototype-near-10-contract.test.ts
bun run prototype:gates -- --prototype prototype/page-cross-market.html
bun run prototype:gates -- --prototype prototype/page-regime-monitor.html
```

Expected: PASS.

**Step 7: Commit**

```bash
git add prototype/page-cross-market.html prototype/page-a-shares.html prototype/page-markets-intelligence.html prototype/page-research.html prototype/page-trading-overview.html prototype/page-portfolio.html prototype/page-risk-center.html prototype/page-regime-monitor.html
git commit -m "fix(prototypes): strengthen analytical primary answers"
```

---

### Task 5: Differentiate Catalog Family Workflows

**Files:**

- Modify: `prototype/page-markets-screener.html`
- Modify: `prototype/page-markets-calendar.html`
- Modify: `prototype/page-watchlist.html`
- Modify: `prototype/page-factor-list.html`
- Modify: `prototype/page-strategy-list.html`
- Modify: `prototype/page-backtest-list.html`
- Modify: `prototype/page-experiment-list.html`
- Modify: `prototype/page-universe-list.html`
- Modify: `design/specs/11_ditto_page_pattern_library.md`
- Test: `scripts/prototype-near-10-contract.test.ts`

**Step 1: Add task-specific summary attributes**

Each Catalog page must include a distinct page-family marker:

```html
data-catalog-task="strategy-health"
data-catalog-task="backtest-comparison"
data-catalog-task="experiment-result-matrix"
data-catalog-task="factor-validity"
data-catalog-task="universe-impact"
data-catalog-task="watchlist-next-action"
data-catalog-task="event-calendar"
data-catalog-task="screener-result-routing"
```

**Step 2: Strategy List**

Primary Answer must focus on run readiness:

- `可运行 5`
- `需处理 2`
- `最佳健康策略 Alpha-Momentum-v3`
- `暂停原因：回撤 / 数据延迟`
- Action: `运行回测` or `查看最佳策略`

**Step 3: Backtest List**

Primary Answer must focus on comparison:

- `可加入对比 7 / 10`
- `失败 1`
- `当前基线 MOM-v2`
- `最佳 Sharpe 2.12`
- Action: `加入对比`

**Step 4: Experiment List**

Primary Answer must focus on statistical decision:

- `胜出参数 4`
- `参数稳定性 高`
- `显著性 p<0.05`
- `失败原因：数据漂移`
- Action: `查看胜出`

**Step 5: Factor List**

Primary Answer must focus on factor validity:

- `平均 IC 0.041`
- `平均 IR 1.32`
- `衰减 3`
- `覆盖率 86%`
- Action: `诊断衰减`

**Step 6: Universe List**

Current summary is too thin. Expand to:

- `12 个股票池`
- `1,932 只标的`
- `18 个策略引用`
- `2 项过期`
- `本周成分变更 46`
- Action: `查看引用影响`

**Step 7: Update pattern spec**

In `11_ditto_page_pattern_library.md`, add Catalog subtypes and their Primary Answer formulas.

**Step 8: Re-run tests**

Run:

```bash
bun test scripts/prototype-near-10-contract.test.ts
bun run prototype:gates -- --prototype prototype/page-strategy-list.html
bun run prototype:gates -- --prototype prototype/page-backtest-list.html
bun run prototype:gates -- --prototype prototype/page-experiment-list.html
bun run prototype:gates -- --prototype prototype/page-factor-list.html
bun run prototype:gates -- --prototype prototype/page-universe-list.html
```

Expected: PASS.

**Step 9: Commit**

```bash
git add prototype/page-markets-screener.html prototype/page-markets-calendar.html prototype/page-watchlist.html prototype/page-factor-list.html prototype/page-strategy-list.html prototype/page-backtest-list.html prototype/page-experiment-list.html prototype/page-universe-list.html design/specs/11_ditto_page_pattern_library.md
git commit -m "fix(prototypes): differentiate catalog decision workflows"
```

---

### Task 6: Upgrade Ops, Execution, And Studio Workflows

**Files:**

- Modify: `prototype/page-signals-inbox.html`
- Modify: `prototype/page-orders-ledger.html`
- Modify: `prototype/page-platform.html`
- Modify: `prototype/page-agent-console.html`
- Modify: `prototype/page-platform-settings.html`
- Modify: `prototype/page-strategy-studio.html`
- Modify: `design/specs/04_interaction_state_spec.md`
- Test: `scripts/prototype-near-10-contract.test.ts`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Signals Inbox**

Replace thin Primary Answer:

Current:

```text
待复核: 12 · T+1: 2 项 · 两融: 合规
```

Target:

```text
优先处理贵州茅台买入信号：置信度 82%，T+1 今日已买入，若批准后组合 Beta 0.94。
```

Required evidence:

- `置信度 82%`
- `T+1 今日已买入`
- `两融合规`
- `调整后持仓 8.2%`

Required actions:

- `批准`
- `拒绝`
- `查看证据`

**Step 2: Orders Ledger**

Primary Answer must state reconciliation priority:

- `1 笔部分成交需处理`
- `2 笔待提交`
- `失败/撤单 12`
- Action: `重试失败订单` or `撤单`

**Step 3: Agent Console**

Make the Agent page operational, not only progress-based:

- Judgment: `Factor 挖掘 Agent 正在分析动量因子，下一审批点为策略验证。`
- Metric: `62%`
- Evidence: `已读取 4,832 行`, `产出 8 个因子`, `3 个策略候选`
- Output destination: `发送到 Factor List / Strategy Studio / Signals`
- Approval state: `等待研究员复核`

**Step 4: Platform / Settings**

Make configuration risk actionable:

- `Bloomberg 未连接 required`
- `华泰证券 Token 过期`
- `配置漂移 2 pending`
- Action: `重新授权` or `查看配置 Diff`

**Step 5: Strategy Studio**

Primary Answer must include build/run status and next failure:

- `校验通过 11 / 12`
- `1 项警告`
- `Dry Run 可执行`
- `提交回测`
- Explicit target: `Backtest Result`

**Step 6: Re-run tests**

Run:

```bash
bun test scripts/prototype-near-10-contract.test.ts
bun run prototype:interaction
bun run prototype:gates -- --prototype prototype/page-signals-inbox.html
bun run prototype:gates -- --prototype prototype/page-agent-console.html
```

Expected: PASS.

**Step 7: Commit**

```bash
git add prototype/page-signals-inbox.html prototype/page-orders-ledger.html prototype/page-platform.html prototype/page-agent-console.html prototype/page-platform-settings.html prototype/page-strategy-studio.html design/specs/04_interaction_state_spec.md
git commit -m "fix(prototypes): make ops and studio workflows decision-first"
```

---

### Task 7: Add Object Hub Consequence Previews

**Files:**

- Modify: `prototype/page-instrument-hub.html`
- Modify: `prototype/page-factor-analysis.html`
- Modify: `prototype/page-strategies-detail.html`
- Modify: `prototype/page-backtest-result.html`
- Modify: `design/specs/12_ditto_data_views_spec.md`
- Test: `scripts/prototype-near-10-contract.test.ts`

**Step 1: Add object consequence contract**

In the new near-10 test file, assert Object Hub pages include:

```html
data-object-consequence-preview
```

The preview must include at least two impact rows and one destination action.

**Step 2: Instrument Hub**

For `贵州茅台`, add:

- `加入观察`: future alert impact.
- `发送到研究`: creates research note input.
- `加入标的池`: affects universe count.

**Step 3: Factor Analysis**

For factor actions, add:

- `加入回测`: target backtest scope.
- `加入实验`: target experiment matrix.
- `AI 解读`: output destination and confidence.

**Step 4: Strategies Detail**

For strategy actions, add:

- `提交回测`: expected queue and risk check.
- `编辑策略`: draft impact.
- `复制`: clone lineage.

**Step 5: Backtest Result**

For result actions, add:

- `启用信号`: approval and Signals Inbox destination.
- `加入对比`: comparison tray effect.
- `导出报告`: report scope.

**Step 6: Re-run tests**

Run:

```bash
bun test scripts/prototype-near-10-contract.test.ts
bun run prototype:gates -- --prototype prototype/page-instrument-hub.html
bun run prototype:gates -- --prototype prototype/page-backtest-result.html
```

Expected: PASS.

**Step 7: Commit**

```bash
git add prototype/page-instrument-hub.html prototype/page-factor-analysis.html prototype/page-strategies-detail.html prototype/page-backtest-result.html design/specs/12_ditto_data_views_spec.md
git commit -m "fix(prototypes): add object hub consequence previews"
```

---

### Task 8: Make Command Palette Context-Aware

**Files:**

- Modify: `prototype/shared/prototype-interactions.js`
- Modify: `prototype/shared/layout-base.css`
- Modify: active `prototype/page-*.html`
- Modify: `design/specs/04_interaction_state_spec.md`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`

**Step 1: Extend command context contract**

For each page with a selected object, add:

```html
data-command-context-object="600519"
data-command-context-actions="approve,reject,view-evidence"
```

Use page-appropriate actions:

- Home: `review-signal`, `open-risk`, `open-orders`, `explain-priority`
- Watchlist: `generate-signal`, `open-instrument-hub`, `send-to-research`, `remove-watch`
- Strategy List: `run-backtest`, `clone-strategy`, `view-recent-runs`, `pause-strategy`
- Backtest List: `add-to-compare`, `view-curve`, `copy-params`, `generate-report`
- Signals Inbox: `approve`, `reject`, `send-to-order`, `view-evidence`
- Platform: `retry`, `view-logs`, `mute-alert`, `create-incident`

**Step 2: Update shared JS**

In `prototype-interactions.js`, make command suggestions read the nearest selected object region:

```js
var context = document.querySelector("[data-command-context-object]");
var actions = (context && context.getAttribute("data-command-context-actions") || "")
  .split(",")
  .filter(Boolean);
```

Render suggestions only as prototype-visible items; do not implement full command execution.

**Step 3: Add tests**

In `prototype-interaction-ux-contract.test.ts`, assert:

- every page in `commandContextActionsByPageId` has required actions.
- command suggestions appear when command shell is opened.
- actions remain keyboard reachable.

Run:

```bash
bun run prototype:interaction
```

Expected: PASS.

**Step 4: Commit**

```bash
git add prototype/shared/prototype-interactions.js prototype/shared/layout-base.css prototype/page-*.html design/specs/04_interaction_state_spec.md scripts/prototype-interaction-ux-contract.test.ts
git commit -m "fix(prototypes): add context-aware command actions"
```

---

### Task 9: Tighten Visual Semantics And Non-Color Encoding

**Files:**

- Modify: `prototype/tokens-style.css`
- Modify: `prototype/shared/layout-base.css`
- Modify: `prototype/page-a-shares.html`
- Modify: `prototype/page-cross-market.html`
- Modify: `prototype/page-markets-intelligence.html`
- Modify: `prototype/page-risk-center.html`
- Modify: `design/specs/20_interaction_ux_audit.md`
- Test: `scripts/prototype-design-consistency.test.ts`

**Step 1: Add non-color marker test**

For important market/risk/system states, assert text or marker exists:

- market up/down: sign `+`, `-`, arrow, or label.
- risk warning: `!`, `突破`, `接近`, or explicit severity.
- system stale/degraded: `stale`, `降级`, `延迟`, or equivalent Chinese text.

Run:

```bash
bun test scripts/prototype-design-consistency.test.ts
```

Expected: FAIL only where color is the sole state cue.

**Step 2: Fix data-viz labels**

Ensure A Shares heatmap cells and Cross Market correlation cells have:

- readable text fallback.
- sign markers for positive/negative.
- legend explaining scale.
- no real information label below 10px.

**Step 3: Light mode quick regression**

Run:

```bash
bun scripts/prototype-visual-matrix.ts
```

Inspect:

- `test-results/edition-review/visual-matrix/a-shares/light-compact.png`
- `test-results/edition-review/visual-matrix/watchlist/light-compact.png`
- `test-results/edition-review/visual-matrix/risk-center/light-compact.png`

Expected: no dark-mode chart island effect; no color-only state.

**Step 4: Commit**

```bash
git add prototype/tokens-style.css prototype/shared/layout-base.css prototype/page-a-shares.html prototype/page-cross-market.html prototype/page-markets-intelligence.html prototype/page-risk-center.html design/specs/20_interaction_ux_audit.md scripts/prototype-design-consistency.test.ts
git commit -m "fix(prototypes): strengthen non-color state semantics"
```

---

### Task 10: Full Review Artifacts And Final Verification

**Files:**

- Create: `docs/reviews/2026-05-02-prototype-near-10-remediation-review.md`
- Modify: `prototype/.edition-manifest.json`
- Verify: all active prototypes.

**Step 1: Run targeted checks**

Run:

```bash
bun test scripts/prototype-near-10-contract.test.ts
bun run prototype:interaction
bun run prototype:gates
bun run audit:routes
bun run audit:tokens:contrast
```

Expected: PASS.

**Step 2: Regenerate visual evidence**

Run:

```bash
bun scripts/prototype-visual-matrix.ts
```

If needed, run the existing gate wrapper to regenerate per-page screenshots:

```bash
bun run prototype:gates
```

Expected: new screenshots in `test-results/`.

**Step 3: Write review report**

Create `docs/reviews/2026-05-02-prototype-near-10-remediation-review.md` with:

- scope.
- before/after scoring.
- list of changed pages.
- remaining accepted exceptions.
- command evidence.
- screenshot artifact paths.

**Step 4: Run full repository verification**

Run:

```bash
bun run check
```

Expected: Biome, TypeScript, and Vitest pass.

**Step 5: Commit**

```bash
git add docs/reviews/2026-05-02-prototype-near-10-remediation-review.md prototype/.edition-manifest.json test-results
git commit -m "docs(prototypes): record near-10 remediation results"
```

Only add `test-results` artifacts if the repository already tracks the relevant output path. If they are untracked and noisy, leave them out and list paths in the report.

---

## Execution Order

1. Task 1: gates first.
2. Task 2: interaction baseline.
3. Task 3: Home.
4. Task 4: Radar / Analytical.
5. Task 5: Catalog.
6. Task 6: Ops / Studio.
7. Task 7: Object Hub.
8. Task 8: Command context.
9. Task 9: visual semantics.
10. Task 10: verification and report.

Do not start page-family edits before Task 1 and Task 2 pass. Otherwise visual changes can hide the actual product-quality failures.

## Risk Register

| Risk | Mitigation |
|---|---|
| Target-size fixes reduce density | Increase hit area with padding or pseudo-area; preserve compact visual rhythm. |
| Primary Answer becomes verbose | Enforce one sentence judgment and compact evidence strip; no paragraph blocks. |
| Catalog pages become visually inconsistent | Differences must come from task-specific summary and right-rail content, not new decorative styles. |
| Command context becomes fake UI | Expose actions as prototype-visible contract only; defer real execution to React backlog. |
| Token changes require approval | Avoid semantic token changes unless Design Token owner approves. |

## Final Acceptance Checklist

- [ ] 27/27 active pages pass Primary Answer 2.0.
- [ ] 0 non-exempt visible targets below 24x24.
- [ ] `page-home.html` remains command-center first viewport and passes narrow viewport.
- [ ] `signals-inbox` names the highest-priority signal, not only count totals.
- [ ] `agent-console` names next approval and output destinations.
- [ ] `regime-monitor` has truthful counter fallback text.
- [ ] Catalog pages are distinguishable by task-specific summary.
- [ ] Object Hub actions preview consequences.
- [ ] Command Palette has context actions for core object pages.
- [ ] Non-color indicators exist for important business states.
- [ ] `bun run prototype:gates` passes.
- [ ] `bun run prototype:interaction` passes.
- [ ] `bun run check` passes.

# Prototype Excellent Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise `docs/designs/specs/prototypes/` active route prototypes from Good-high final review quality to Excellent by tightening A-Shares map semantics, complex-page cognitive load, high-risk action gates, and light-mode readability.

**Architecture:** Keep the existing Graphite Studio visual language and static prototype architecture. Add stricter Vitest/JSDOM/Playwright gates first, then make minimal HTML/CSS changes inside the existing prototype files and shared consistency tests. Do not add dependencies, do not change design tokens unless a human explicitly approves a token change, and do not reopen the overall visual direction.

**Tech Stack:** Bun, Vitest, JSDOM, Playwright, static HTML/CSS prototypes, `npx impeccable --json --fast`, existing Ditto design-cycle scripts.

---

## Scope

Target quality bar: **Excellent, 38+/40**.

In scope:

- A-Shares Treemap and Heatmap semantic clarity.
- Cognitive-load budget on the four heaviest expert pages.
- Production-grade high-risk action documentation in prototype markup.
- Light-mode contrast and weak-text cleanup for selected high-density pages.
- Machine gates that prevent regression.
- Final review record.

Out of scope:

- New dependencies.
- Global design-token changes without approval.
- React implementation.
- Backend or API behavior.
- Mobile structural redesign beyond existing viewport guard.
- Replacing the Graphite Studio direction.

## File Structure

- Modify `scripts/page-a-shares-prototype.test.ts`
  - Owns page-specific market map tests for A-Shares Treemap/Heatmap semantics.
- Modify `docs/designs/specs/prototypes/page-a-shares.html`
  - Owns A-Shares market structure map copy, CSS variable naming, Treemap cell sign markers, label budget, and light/dark map readability.
- Modify `scripts/prototype-expert-efficiency.test.ts`
  - Owns global expert-efficiency tests for complex page decision budgets.
- Modify `docs/designs/specs/prototypes/page-alpha-explorer.html`
  - Owns Alpha Explorer first-screen decision cluster and disclosure structure.
- Modify `docs/designs/specs/prototypes/page-agent-console-v2.html`
  - Owns Agent Console V2 first-screen decision cluster and inspector disclosure structure.
- Modify `docs/designs/specs/prototypes/page-strategy-studio.html`
  - Owns Strategy Studio first-screen decision cluster and AI assistant disclosure structure.
- Modify `docs/designs/specs/prototypes/page-instrument-hub.html`
  - Owns Instrument Hub first-screen action cluster and tab/action discoverability.
- Modify `scripts/prototype-design-consistency.test.ts`
  - Owns cross-page consistency gates: high-risk action pages, light-mode readable surfaces, and data-viz semantics.
- Modify `docs/designs/specs/prototypes/page-strategies-detail.html`
  - Owns destructive strategy deletion confirmation semantics.
- Modify `docs/designs/specs/prototypes/page-universe-list.html`
  - Owns destructive stock-pool deletion confirmation semantics.
- Modify `docs/designs/specs/prototypes/page-signals-inbox.html`
  - Owns batch signal approval/rejection impact semantics.
- Modify `docs/designs/specs/prototypes/page-trading-overview.html`
  - Owns trade pause/resume and signal-review high-risk action semantics.
- Modify `docs/designs/specs/prototypes/page-platform-settings.html`
  - Owns config rollback/save/authorization high-risk action semantics and light-mode weak text.
- Create `docs/reviews/2026-05-11-prototype-excellent-optimization-results.md`
  - Records final evidence, scores, and remaining React implementation caveats.

## Execution Rules

- Work on a feature branch or isolated worktree, not directly on `main`.
- Run tests immediately after each task-specific change.
- Preserve user changes already in the workspace.
- Use `apply_patch` for manual edits.
- Use `bun`, never npm/yarn/pnpm.
- Run `bun run check` before declaring completion.

---

### Task 1: Add A-Shares Excellent Market Map Tests

**Files:**

- Modify: `scripts/page-a-shares-prototype.test.ts`
- Test: `scripts/page-a-shares-prototype.test.ts`

- [ ] **Step 1: Add stricter tests for explicit A-share color semantics, Treemap signs, and label budget**

Append these tests inside `describe("page-a-shares market structure map", () => { ... })`, after the current `"documents size, color, grouping..."` test.

```ts
	it("makes A-share map color semantics explicit instead of relying on perceived purple-cyan tint", () => {
		const document = loadPage();
		const html = loadHtml();
		const map = document.querySelector(".map-container");

		expect(elementText(map, "[data-map-color]")).toContain("涨跌幅");
		expect(elementText(map, "[data-map-color]")).toContain("A股：红涨绿跌");
		expect(elementText(map, "[data-map-metric-switcher]")).toContain("行业 Size 成交额占比");
		expect(elementText(map, "[data-map-metric-switcher]")).toContain("个股 Size 成交额");
		expect(elementText(map, "[data-map-metric-switcher]")).toContain("Color 涨跌幅");
		expect(elementText(map, "[data-map-breadcrumb]")).toContain("申万一级");
		expect(html).toContain("--map-market-up-1");
		expect(html).toContain("--map-market-down-1");
		expect(html).not.toContain("--map-positive-1");
		expect(html).not.toContain("--map-negative-1");
	});

	it("requires sector treemap cells to encode direction through sign, text, and aria labels", () => {
		const document = loadPage();
		const cells = [...document.querySelectorAll<HTMLElement>(".treemap-cell-iv")];

		expect(cells.length).toBeGreaterThanOrEqual(16);

		for (const [index, cell] of cells.entries()) {
			const direction = cell.getAttribute("data-direction");
			const label = cell.getAttribute("aria-label") ?? "";
			const sign = cell.querySelector<HTMLElement>(':scope > .treemap-cell-sign[aria-hidden="true"]');

			expect(direction).toMatch(/^(up|down|flat)$/);
			if (direction === "up") {
				expect(sign?.textContent?.trim(), `cell ${index + 1}`).toBe("▲");
				expect(label, `cell ${index + 1}`).toContain("涨幅");
			}
			if (direction === "down") {
				expect(sign?.textContent?.trim(), `cell ${index + 1}`).toBe("▼");
				expect(label, `cell ${index + 1}`).toContain("跌幅");
			}
			if (direction === "flat") {
				expect(sign?.textContent?.trim(), `cell ${index + 1}`).toBe("•");
				expect(label, `cell ${index + 1}`).toMatch(/持平|涨跌幅/);
			}
		}
	});

	it("applies a deterministic treemap label budget so small rectangles do not become text clutter", () => {
		const document = loadPage();
		const cells = [...document.querySelectorAll<HTMLElement>(".treemap-cell-iv")];

		expect(cells.length).toBeGreaterThanOrEqual(16);

		for (const [index, cell] of cells.entries()) {
			const budget = cell.getAttribute("data-label-budget");
			const name = cell.querySelector(".treemap-cell-name");
			const change = cell.querySelector(".treemap-cell-change");
			const volume = cell.querySelector(".treemap-cell-vol");

			expect(budget, `cell ${index + 1}`).toMatch(/^(full|compact|name-only)$/);
			expect(name, `cell ${index + 1}`).not.toBeNull();

			if (budget === "full") {
				expect(change, `cell ${index + 1}`).not.toBeNull();
				expect(volume, `cell ${index + 1}`).not.toBeNull();
			}
			if (budget === "compact") {
				expect(change, `cell ${index + 1}`).not.toBeNull();
				expect(volume, `cell ${index + 1}`).toBeNull();
			}
			if (budget === "name-only") {
				expect(change, `cell ${index + 1}`).toBeNull();
				expect(volume, `cell ${index + 1}`).toBeNull();
			}
		}
	});
```

- [ ] **Step 2: Update existing A-Shares palette test expectations to the new semantic variable names**

In the existing `"uses a calibrated stepped diverging palette..."` test, replace the variable assertions with this exact block.

```ts
		for (const step of [1, 2, 3, 4]) {
			expect(html).toContain(`--map-market-up-${step}`);
			expect(html).toContain(`--map-market-down-${step}`);
			expect(html).toContain(`--heat-up-${step}`);
			expect(html).toContain(`--heat-down-${step}`);
		}

		expect(html).not.toContain("--map-positive-");
		expect(html).not.toContain("--map-negative-");
```

- [ ] **Step 3: Run the page-specific test and verify it fails**

Run:

```bash
bun vitest run scripts/page-a-shares-prototype.test.ts
```

Expected: FAIL with missing `A股：红涨绿跌`, missing `.treemap-cell-sign`, missing `data-label-budget`, and old `--map-positive-*` / `--map-negative-*` variable names.

- [ ] **Step 4: Commit the failing tests**

```bash
git add scripts/page-a-shares-prototype.test.ts
git commit -m "test: require excellent a-shares map semantics"
```

---

### Task 2: Implement A-Shares Market Map Semantics

**Files:**

- Modify: `docs/designs/specs/prototypes/page-a-shares.html`
- Test: `scripts/page-a-shares-prototype.test.ts`

- [ ] **Step 1: Rename local Treemap palette aliases from generic positive/negative to market up/down**

In `docs/designs/specs/prototypes/page-a-shares.html`, perform these exact replacements.

```text
--map-positive-base      -> --map-market-up-base
--map-negative-base      -> --map-market-down-base
--map-positive-1         -> --map-market-up-1
--map-positive-2         -> --map-market-up-2
--map-positive-3         -> --map-market-up-3
--map-positive-4         -> --map-market-up-4
--map-negative-1         -> --map-market-down-1
--map-negative-2         -> --map-market-down-2
--map-negative-3         -> --map-market-down-3
--map-negative-4         -> --map-market-down-4
--map-positive-edge-1    -> --map-market-up-edge-1
--map-positive-edge-2    -> --map-market-up-edge-2
--map-positive-edge-3    -> --map-market-up-edge-3
--map-positive-edge-4    -> --map-market-up-edge-4
--map-negative-edge-1    -> --map-market-down-edge-1
--map-negative-edge-2    -> --map-market-down-edge-2
--map-negative-edge-3    -> --map-market-down-edge-3
--map-negative-edge-4    -> --map-market-down-edge-4
```

The first CSS block should read like this after the replacement.

```css
      --map-market-up-base: color-mix(in oklch, var(--market-up-fg) 14%, var(--surface-panel-base));
      --map-market-down-base: color-mix(in oklch, var(--market-down-fg) 14%, var(--surface-panel-base));
      --map-market-up-1: color-mix(in oklch, var(--market-up-fg) 5%, var(--map-market-up-base));
      --map-market-up-2: color-mix(in oklch, var(--market-up-fg) 11%, var(--map-market-up-base));
      --map-market-up-3: color-mix(in oklch, var(--market-up-fg) 18%, var(--map-market-up-base));
      --map-market-up-4: color-mix(in oklch, var(--market-up-fg) 26%, var(--map-market-up-base));
      --map-market-down-1: color-mix(in oklch, var(--market-down-fg) 5%, var(--map-market-down-base));
      --map-market-down-2: color-mix(in oklch, var(--market-down-fg) 11%, var(--map-market-down-base));
      --map-market-down-3: color-mix(in oklch, var(--market-down-fg) 18%, var(--map-market-down-base));
      --map-market-down-4: color-mix(in oklch, var(--market-down-fg) 26%, var(--map-market-down-base));
```

- [ ] **Step 2: Update heat aliases to point at the renamed variables**

Replace the heat alias block with this exact block.

```css
      --heat-flat: var(--map-neutral-fill);
      --heat-up-1: var(--map-market-up-1);
      --heat-up-2: var(--map-market-up-2);
      --heat-up-3: var(--map-market-up-3);
      --heat-up-4: var(--map-market-up-4);
      --heat-down-1: var(--map-market-down-1);
      --heat-down-2: var(--map-market-down-2);
      --heat-down-3: var(--map-market-down-3);
      --heat-down-4: var(--map-market-down-4);
      --heat-up-line-1: var(--map-market-up-edge-1);
      --heat-up-line-2: var(--map-market-up-edge-2);
      --heat-up-line-3: var(--map-market-up-edge-3);
      --heat-up-line-4: var(--map-market-up-edge-4);
      --heat-down-line-1: var(--map-market-down-edge-1);
      --heat-down-line-2: var(--map-market-down-edge-2);
      --heat-down-line-3: var(--map-market-down-edge-3);
      --heat-down-line-4: var(--map-market-down-edge-4);
```

- [ ] **Step 3: Add Treemap sign and label-budget CSS**

Add this block after the existing `.treemap-cell-name, .hm-name { ... }` rules.

```css
    .treemap-cell-sign {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 0.85rem;
      height: 0.85rem;
      border-radius: var(--radius-3);
      color: var(--market-map-cell-value);
      background: color-mix(in oklch, var(--surface-panel-base) 34%, transparent);
      box-shadow: inset 0 0 0 1px color-mix(in oklch, var(--heat-line) 42%, transparent);
      font-family: var(--font-family-ui);
      font-size: var(--font-size-10);
      font-weight: var(--font-weight-semibold);
      line-height: 1;
    }

    .treemap-cell-iv[data-label-budget="compact"] .treemap-cell-vol,
    .treemap-cell-iv[data-label-budget="name-only"] .treemap-cell-change,
    .treemap-cell-iv[data-label-budget="name-only"] .treemap-cell-vol {
      display: none;
    }

    .treemap-cell-iv[data-label-budget="name-only"] {
      justify-content: center;
      padding: var(--space-5);
    }
```

- [ ] **Step 4: Add explicit color semantics to the map copy**

Update the readout and metric switcher to this content.

```html
<span class="map-readout-item" data-map-size>Size <strong>成交额占比</strong></span>
<span class="map-readout-item" data-map-color>Color <strong>涨跌幅（A股：红涨绿跌）</strong></span>
<span class="map-readout-item" data-map-grouping>Grouping <strong>申万一级</strong></span>
```

```html
<span data-map-metric-switcher>行业 Size 成交额占比 · 个股 Size 成交额 · Color 涨跌幅（A股：红涨绿跌）</span>
```

Update the breadcrumb text to include the hierarchy explicitly.

```html
<span data-map-breadcrumb>A股 / 申万一级 / 今日</span>
```

- [ ] **Step 5: Add sign markers and label budgets to Treemap cells**

For every `.treemap-cell-iv`, add:

- `data-label-budget="full"` for large cells that keep name, change, and volume.
- `data-label-budget="compact"` for medium cells that keep name and change.
- `data-label-budget="name-only"` for tiny cells that keep only name.
- A first child sign span matching `data-direction`.

Use this exact pattern for an up full cell.

```html
<div class="treemap-cell-iv tm-cell-1" role="button" data-direction="up" data-heat="up-4" data-sector-family="growth" data-reveal="fade-up" data-size-metric="turnover-share" data-color-metric="change-pct" data-label-budget="full" aria-label="电子 — 涨幅 +2.34%，成交额占比 15.2%" data-tooltip="电子 — 涨幅 +2.34%，成交额占比 15.2%" tabindex="0" onclick="document.getElementById('overlay-sector-detail').checked=true">
  <span class="treemap-cell-sign" aria-hidden="true">▲</span>
  <span class="treemap-cell-name">电子</span>
  <span class="treemap-cell-change up">+2.34%</span>
  <span class="treemap-cell-vol">占比 15.2%</span>
</div>
```

Use this exact pattern for a down compact cell.

```html
<div class="treemap-cell-iv tm-cell-4" role="button" data-direction="down" data-heat="down-1" data-sector-family="defensive" data-reveal="fade-up" data-size-metric="turnover-share" data-color-metric="change-pct" data-label-budget="compact" aria-label="医药 — 跌幅 -0.23%，成交额占比 5.1%" data-tooltip="医药 — 跌幅 -0.23%，成交额占比 5.1%" tabindex="0" onclick="document.getElementById('overlay-sector-detail').checked=true">
  <span class="treemap-cell-sign" aria-hidden="true">▼</span>
  <span class="treemap-cell-name">医药</span>
  <span class="treemap-cell-change down">-0.23%</span>
</div>
```

Use this exact pattern for a flat name-only cell when a flat cell exists.

```html
<div class="treemap-cell-iv tm-cell-flat" role="button" data-direction="flat" data-heat="flat" data-sector-family="defensive" data-reveal="fade-up" data-size-metric="turnover-share" data-color-metric="change-pct" data-label-budget="name-only" aria-label="公用事业 — 涨跌幅持平，成交额占比 2.8%" data-tooltip="公用事业 — 涨跌幅持平，成交额占比 2.8%" tabindex="0" onclick="document.getElementById('overlay-sector-detail').checked=true">
  <span class="treemap-cell-sign" aria-hidden="true">•</span>
  <span class="treemap-cell-name">公用事业</span>
</div>
```

If no flat sector exists in the current data, do not create fake flat data. Keep all actual cells `up` or `down`.

- [ ] **Step 6: Run A-Shares tests**

Run:

```bash
bun vitest run scripts/page-a-shares-prototype.test.ts
```

Expected: PASS.

- [ ] **Step 7: Run A-Shares gate screenshot**

Run:

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-a-shares.html
```

Expected: PASS for `VP-STANDARD`, `VP-COMPACT`, and `VP-NARROW`.

- [ ] **Step 8: Commit A-Shares implementation**

```bash
git add docs/designs/specs/prototypes/page-a-shares.html scripts/page-a-shares-prototype.test.ts
git commit -m "fix: clarify a-shares market map semantics"
```

---

### Task 3: Add Complex Page Decision-Budget Gates

**Files:**

- Modify: `scripts/prototype-expert-efficiency.test.ts`
- Test: `scripts/prototype-expert-efficiency.test.ts`

- [ ] **Step 1: Add complex page budget constants**

Add these constants near the existing `expertPages` and `rowContextMenuPages` constants.

```ts
const complexDecisionBudgetPages = [
	"page-alpha-explorer.html",
	"page-agent-console-v2.html",
	"page-strategy-studio.html",
	"page-instrument-hub.html",
] as const;

const maxVisibleDecisionOptions = 4;
```

- [ ] **Step 2: Add a test for first-screen decision clusters**

Add this test inside `describe("prototype expert efficiency", () => { ... })`.

```ts
	it("keeps complex expert pages within a four-option first-screen decision budget", () => {
		const violations: string[] = [];

		for (const file of complexDecisionBudgetPages) {
			const document = loadDocument(file);
			const cluster = document.querySelector("[data-decision-cluster]");
			const options = cluster?.querySelectorAll("[data-decision-option]") ?? [];
			const overflow = cluster?.querySelector("[data-decision-overflow]");
			const primaryAnswer = document.querySelector("[data-primary-answer], [data-primary-answer-equivalent]");

			if (!cluster) {
				violations.push(`${file}:decision-cluster:missing`);
				continue;
			}
			if (!primaryAnswer) {
				violations.push(`${file}:primary-answer:missing`);
			}
			if (options.length === 0) {
				violations.push(`${file}:decision-options:missing`);
			}
			if (options.length > maxVisibleDecisionOptions) {
				violations.push(`${file}:decision-options:${options.length}`);
			}
			if (options.length === maxVisibleDecisionOptions && !overflow) {
				violations.push(`${file}:overflow:missing`);
			}
			for (const [index, option] of [...options].entries()) {
				const text = option.textContent?.replace(/\s+/g, " ").trim() ?? "";
				const label = option.getAttribute("aria-label") ?? "";
				if (!text && !label) {
					violations.push(`${file}:decision-option:${index + 1}:name`);
				}
			}
		}

		expect(violations).toEqual([]);
	});
```

- [ ] **Step 3: Add a test for default inspector disclosure**

Add this test after the decision-budget test.

```ts
	it("keeps complex page inspectors focused on current-decision evidence by default", () => {
		const violations: string[] = [];

		for (const file of complexDecisionBudgetPages) {
			const document = loadDocument(file);
			const defaultOpenSections = document.querySelectorAll(
				"[data-decision-evidence][data-default-open='true'], details[data-decision-evidence][open]",
			);
			const backgroundSections = document.querySelectorAll(
				"[data-background-evidence][data-default-open='true'], details[data-background-evidence][open]",
			);

			if (defaultOpenSections.length < 1) {
				violations.push(`${file}:decision-evidence:missing`);
			}
			if (defaultOpenSections.length > 2) {
				violations.push(`${file}:decision-evidence:${defaultOpenSections.length}`);
			}
			if (backgroundSections.length > 0) {
				violations.push(`${file}:background-open:${backgroundSections.length}`);
			}
		}

		expect(violations).toEqual([]);
	});
```

- [ ] **Step 4: Run expert-efficiency tests and verify failure**

Run:

```bash
bun vitest run scripts/prototype-expert-efficiency.test.ts
```

Expected: FAIL with missing `data-decision-cluster` or missing `data-decision-evidence` on the four complex pages.

- [ ] **Step 5: Commit failing tests**

```bash
git add scripts/prototype-expert-efficiency.test.ts
git commit -m "test: require complex page decision budgets"
```

---

### Task 4: Implement Complex Page Decision-Budget Markup

**Files:**

- Modify: `docs/designs/specs/prototypes/page-alpha-explorer.html`
- Modify: `docs/designs/specs/prototypes/page-agent-console-v2.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
- Modify: `docs/designs/specs/prototypes/page-instrument-hub.html`
- Test: `scripts/prototype-expert-efficiency.test.ts`

- [ ] **Step 1: Add decision cluster attributes on Alpha Explorer**

In `page-alpha-explorer.html`, wrap the primary header mode/action controls with `data-decision-cluster` and mark the four first-screen options.

```html
<div class="header-actions" data-decision-cluster aria-label="Alpha 探索首屏决策">
  <button class="mode-tab active" data-decision-option aria-label="Copilot 探索当前候选">Copilot 探索</button>
  <button class="mode-tab" data-decision-option aria-label="自动研究审阅">自动研究审阅</button>
  <button class="mode-tab" data-decision-option aria-label="因子实验室">因子实验室</button>
  <button class="btn-cta" data-decision-option aria-label="启动探索">启动探索</button>
  <button class="btn-ghost" data-decision-overflow aria-label="更多 Alpha 探索操作">更多</button>
</div>
```

If the current markup uses labels instead of buttons for mode tabs, keep the existing element type and add the same `data-decision-*` attributes and `aria-label` values.

- [ ] **Step 2: Mark Alpha Explorer evidence sections**

Add `data-decision-evidence data-default-open="true"` to the candidate inspector section that contains formula/rationale and evidence chain. Add `data-background-evidence` to lower-priority queue/history sections that should not be default-open evidence.

```html
<section class="inspector-section" data-decision-evidence data-default-open="true" aria-label="候选证据链">
```

```html
<section class="queue-panel" data-background-evidence aria-label="采纳队列">
```

- [ ] **Step 3: Add decision cluster attributes on Agent Console V2**

In `page-agent-console-v2.html`, mark only the core run-state choices and primary creation action.

```html
<div class="agent-tabs" data-decision-cluster aria-label="智能体控制台首屏决策">
  <button class="tab active" data-decision-option aria-label="查看计划队列">计划</button>
  <button class="tab" data-decision-option aria-label="查看运行中任务">运行</button>
  <button class="tab" data-decision-option aria-label="查看待审批项">审批</button>
  <button class="btn-cta" data-decision-option aria-label="新建计划">新建计划</button>
  <button class="tab tab-overflow" data-decision-overflow aria-haspopup="menu" aria-label="更多控制台视图">...</button>
</div>
```

- [ ] **Step 4: Mark Agent Console evidence sections**

The run inspector summary should be default-open decision evidence. Tool trace and long activity history should be background evidence.

```html
<section class="inspector-section" data-decision-evidence data-default-open="true" aria-label="运行检查摘要">
```

```html
<section class="inspector-section" data-background-evidence aria-label="工具追踪">
```

- [ ] **Step 5: Add decision cluster attributes on Strategy Studio**

In `page-strategy-studio.html`, mark the four primary first-screen controls.

```html
<div class="header-actions" data-decision-cluster aria-label="策略工作台首屏决策">
  <button class="btn-secondary" data-decision-option aria-label="保存策略">保存</button>
  <button class="btn-secondary" data-decision-option aria-label="校验策略">校验</button>
  <button class="btn-secondary" data-decision-option aria-label="执行 Dry Run">Dry Run</button>
  <button class="btn-primary" data-decision-option aria-label="提交回测">提交回测</button>
  <button class="btn-icon" data-decision-overflow aria-label="更多策略操作">...</button>
</div>
```

- [ ] **Step 6: Mark Strategy Studio evidence sections**

Make the AI assistant recommendation and validation warnings decision evidence. Mark longer logs as background evidence.

```html
<aside class="studio-assistant" data-decision-evidence data-default-open="true" aria-label="AI 助手建议">
```

```html
<section class="bottom-tray" data-background-evidence aria-label="校验日志和编译日志">
```

- [ ] **Step 7: Add decision cluster attributes on Instrument Hub**

In `page-instrument-hub.html`, mark the object-level first-screen controls.

```html
<div class="header-actions" data-decision-cluster aria-label="标的详情首屏决策">
  <label class="btn-secondary" data-decision-option aria-label="加入观察">加入观察</label>
  <label class="btn-secondary" data-decision-option aria-label="加入标的池">加入标的池</label>
  <label class="btn-secondary" data-decision-option aria-label="发送到研究">发送到研究</label>
  <label class="btn-secondary" data-decision-option aria-label="打开 Chart Lab">Chart Lab</label>
  <button class="btn-icon" data-decision-overflow aria-label="更多标的操作">...</button>
</div>
```

- [ ] **Step 8: Mark Instrument Hub evidence sections**

Make related signals and valuation warning decision evidence. Mark archive/news/background accordions as background evidence.

```html
<section class="context-section" data-decision-evidence data-default-open="true" aria-label="相关信号">
```

```html
<section class="context-section" data-background-evidence aria-label="关联研究">
```

- [ ] **Step 9: Run expert-efficiency tests**

Run:

```bash
bun vitest run scripts/prototype-expert-efficiency.test.ts
```

Expected: PASS.

- [ ] **Step 10: Run visual gates for the four complex pages**

Run:

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-alpha-explorer.html
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-agent-console-v2.html
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-strategy-studio.html
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-instrument-hub.html
```

Expected: each command PASS for all default viewports.

- [ ] **Step 11: Commit complex page implementation**

```bash
git add docs/designs/specs/prototypes/page-alpha-explorer.html docs/designs/specs/prototypes/page-agent-console-v2.html docs/designs/specs/prototypes/page-strategy-studio.html docs/designs/specs/prototypes/page-instrument-hub.html scripts/prototype-expert-efficiency.test.ts
git commit -m "fix: reduce complex prototype decision load"
```

---

### Task 5: Strengthen High-Risk Action Gates

**Files:**

- Modify: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/prototype-design-consistency.test.ts`

- [ ] **Step 1: Expand high-risk page coverage**

Replace the existing `highRiskActionPages` constant with this exact list.

```ts
const highRiskActionPages = [
	"platform-settings",
	"trading-overview",
	"signals-inbox",
	"orders-ledger",
	"universe-list",
	"strategies-detail",
	"strategy-list",
] as const;
```

- [ ] **Step 2: Replace the high-risk action test with stricter copy checks**

Replace the existing `"documents high-risk actions..."` test with this exact version.

```ts
	it("documents high-risk actions with object, impact, confirmation, cancel, recovery, and non-color danger cues", () => {
		const violations: string[] = [];

		for (const page of activePages().filter((prototype) => highRiskActionPages.includes(prototype.id as (typeof highRiskActionPages)[number]))) {
			const document = readPrototypeDocument(page);
			const defaultView = document.querySelector("#default-view");
			const action = defaultView?.querySelector("[data-danger-action], [data-high-risk-action]");

			if (!defaultView || !action) {
				violations.push(`${page.id}:danger-action`);
				continue;
			}

			const container = action.closest("[data-danger-confirmation], [data-high-risk-confirmation]");
			if (!container) {
				violations.push(`${page.id}:confirmation-container`);
				continue;
			}

			for (const selector of [
				"[data-risk-object]",
				"[data-impact-summary]",
				"[data-confirm-control]",
				"[data-cancel-control]",
				"[data-recovery-hint]",
				"[data-danger-marker]",
			]) {
				if (!container.querySelector(selector)) {
					violations.push(`${page.id}:${selector}`);
				}
			}

			const containerText = getReadablePrimaryText(container);
			if (!/(影响|后果|范围|订单|策略|标的池|信号|配置|交易|撤单|审批)/.test(containerText)) {
				violations.push(`${page.id}:impact-copy`);
			}
			if (!/(取消|保留|返回|不执行)/.test(containerText)) {
				violations.push(`${page.id}:cancel-copy`);
			}
			if (!/(恢复|回滚|可重新|保留记录|审计)/.test(containerText)) {
				violations.push(`${page.id}:recovery-copy`);
			}
		}

		expect(violations).toEqual([]);
	});
```

- [ ] **Step 3: Run consistency tests and verify failure**

Run:

```bash
bun vitest run scripts/prototype-design-consistency.test.ts -t "high-risk actions"
```

Expected: FAIL for at least one newly covered high-risk page that lacks `data-risk-object` or recovery copy.

- [ ] **Step 4: Commit failing test**

```bash
git add scripts/prototype-design-consistency.test.ts
git commit -m "test: require production-grade high-risk action copy"
```

---

### Task 6: Implement High-Risk Action Markup

**Files:**

- Modify: `docs/designs/specs/prototypes/page-strategies-detail.html`
- Modify: `docs/designs/specs/prototypes/page-universe-list.html`
- Modify: `docs/designs/specs/prototypes/page-signals-inbox.html`
- Modify: `docs/designs/specs/prototypes/page-orders-ledger.html`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
- Modify: `docs/designs/specs/prototypes/page-platform-settings.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-list.html`
- Test: `scripts/prototype-design-consistency.test.ts`

- [ ] **Step 1: Use the same high-risk confirmation structure on every covered page**

Each covered page must contain one default-view container matching this structure. Use existing local classes where present, but keep the `data-*` attributes and copy shape.

```html
<section class="danger-review" data-danger-confirmation aria-label="高风险操作确认">
  <div class="danger-review-header">
    <span class="danger-marker" data-danger-marker aria-hidden="true">!</span>
    <span data-risk-object>对象：当前对象名称</span>
  </div>
  <p data-impact-summary>影响范围：说明这次操作会改变哪些订单、策略、标的池、信号、配置或交易状态。</p>
  <div class="danger-review-actions">
    <button type="button" data-confirm-control data-danger-action aria-label="确认执行高风险操作">确认执行</button>
    <button type="button" data-cancel-control aria-label="取消并保留当前状态">取消，保留当前状态</button>
  </div>
  <p data-recovery-hint>恢复路径：操作会保留审计记录，可通过回滚、重新审批或重新提交恢复。</p>
</section>
```

- [ ] **Step 2: Apply exact page-specific copy**

Use these page-specific text values.

```text
page-strategies-detail.html
data-risk-object: 对象：动量因子增强策略 v3.2
data-impact-summary: 影响范围：删除后会停止新回测、保留历史回测和信号审计，不影响已成交订单。
data-confirm-control: 确认删除策略
data-cancel-control: 取消，保留策略
data-recovery-hint: 恢复路径：删除记录进入审计日志，可从最近版本克隆恢复。

page-universe-list.html
data-risk-object: 对象：沪深300成分股股票池
data-impact-summary: 影响范围：删除会影响 3 个关联策略的标的引用，已运行回测保持可追溯。
data-confirm-control: 确认删除股票池
data-cancel-control: 取消，保留股票池
data-recovery-hint: 恢复路径：可从指数成分源重新同步，并保留删除审计记录。

page-signals-inbox.html
data-risk-object: 对象：已选择 3 条待复核信号
data-impact-summary: 影响范围：批量确认会进入下单约束检查，批量忽略会保留信号但不触发订单。
data-confirm-control: 确认处理 3 条信号
data-cancel-control: 取消，保留待复核
data-recovery-hint: 恢复路径：已忽略信号可从已忽略队列恢复，确认记录进入审计日志。

page-orders-ledger.html
data-risk-object: 对象：ORD-001 贵州茅台买入订单
data-impact-summary: 影响范围：撤单会停止剩余未成交数量，已成交 200 股保持入账。
data-confirm-control: 确认撤单
data-cancel-control: 取消，保留订单
data-recovery-hint: 恢复路径：撤单后可按原策略重新提交订单，并保留券商回报记录。

page-trading-overview.html
data-risk-object: 对象：当前交易模式和待处理信号队列
data-impact-summary: 影响范围：暂停交易会阻止新订单提交，已提交订单继续按券商状态回报。
data-confirm-control: 确认暂停交易
data-cancel-control: 取消，保持交易模式
data-recovery-hint: 恢复路径：可在交易总览重新启用交易，所有切换写入审计日志。

page-platform-settings.html
data-risk-object: 对象：prod-cn-a 配置草稿 r18
data-impact-summary: 影响范围：保存配置会影响数据源连接、券商授权和风险默认参数。
data-confirm-control: 确认保存配置
data-cancel-control: 取消，保留草稿
data-recovery-hint: 恢复路径：可回滚到 r17 stable，配置差异保留在审计日志。

page-strategy-list.html
data-risk-object: 对象：Alpha-Momentum-v3 策略
data-impact-summary: 影响范围：暂停或删除会停止后续回测和信号生成，历史记录保留。
data-confirm-control: 确认变更策略状态
data-cancel-control: 取消，保留策略状态
data-recovery-hint: 恢复路径：可从策略详情恢复运行或克隆最近版本。
```

- [ ] **Step 3: Keep high-risk controls visually non-modal**

Use inline confirmation bars, detail rail review panels, or bottom review bars. Do not introduce first-thought modal overlays for these default high-risk confirmations.

Add this class block to pages that lack a danger review visual treatment.

```css
    .danger-review {
      border: 1px solid var(--border-warning);
      border-radius: var(--radius-6);
      background: var(--risk-medium-bg);
      padding: var(--space-10);
      display: grid;
      gap: var(--space-8);
    }

    .danger-review-header,
    .danger-review-actions {
      display: flex;
      align-items: center;
      gap: var(--space-8);
    }

    .danger-marker {
      display: inline-flex;
      width: 1rem;
      height: 1rem;
      align-items: center;
      justify-content: center;
      border-radius: var(--radius-3);
      color: var(--text-warning);
      border: 1px solid var(--border-warning);
      font-weight: var(--font-weight-semibold);
    }
```

- [ ] **Step 4: Run high-risk consistency test**

Run:

```bash
bun vitest run scripts/prototype-design-consistency.test.ts -t "high-risk actions"
```

Expected: PASS.

- [ ] **Step 5: Run page-specific tests for touched pages**

Run:

```bash
bun vitest run scripts/page-strategies-detail-prototype.test.ts scripts/page-universe-list-prototype.test.ts scripts/page-signals-inbox-prototype.test.ts scripts/page-orders-ledger-prototype.test.ts scripts/page-trading-overview-prototype.test.ts scripts/page-platform-settings-prototype.test.ts scripts/page-strategy-list-prototype.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit high-risk implementation**

```bash
git add docs/designs/specs/prototypes/page-strategies-detail.html docs/designs/specs/prototypes/page-universe-list.html docs/designs/specs/prototypes/page-signals-inbox.html docs/designs/specs/prototypes/page-orders-ledger.html docs/designs/specs/prototypes/page-trading-overview.html docs/designs/specs/prototypes/page-platform-settings.html docs/designs/specs/prototypes/page-strategy-list.html scripts/prototype-design-consistency.test.ts
git commit -m "fix: document high-risk prototype actions"
```

---

### Task 7: Add Light-Mode Readability Gates

**Files:**

- Modify: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/prototype-design-consistency.test.ts`

- [ ] **Step 1: Add light readability page list**

Add this constant near the other prototype page lists.

```ts
const lightReadabilityPages = [
	"home",
	"a-shares",
	"strategy-studio",
	"platform-settings",
] as const;
```

- [ ] **Step 2: Add a CSS-token gate for approved light weak-text overrides**

Add this test near the existing light-map scale test.

```ts
	it("keeps selected light-mode prototype weak text on readable semantic tokens", () => {
		const violations: string[] = [];

		for (const pageId of lightReadabilityPages) {
			const page = activePageById(pageId);
			const html = readPrototypeHtml(page);
			const hasLightOverride = /\[data-theme="light"\][^{]+\{[^}]*--text-(?:tertiary|quaternary):\s*color-mix\(in oklch,\s*var\(--neutral-(?:400|500|600)\)/s.test(html) ||
				/\[data-theme="light"\][^{]+\{[^}]*--prototype-light-readable-text:\s*var\(--neutral-600\)/s.test(html);

			if (!hasLightOverride) {
				violations.push(`${pageId}:light-readable-text`);
			}
			if (/color:\s*var\(--text-quaternary\)/.test(html) && !html.includes("--prototype-light-readable-text")) {
				violations.push(`${pageId}:quaternary-without-light-readable-token`);
			}
		}

		expect(violations).toEqual([]);
	});
```

- [ ] **Step 3: Run the new gate and verify failure**

Run:

```bash
bun vitest run scripts/prototype-design-consistency.test.ts -t "light-mode prototype weak text"
```

Expected: FAIL for selected pages that do not yet define a local `--prototype-light-readable-text` or equivalent light override.

- [ ] **Step 4: Commit failing test**

```bash
git add scripts/prototype-design-consistency.test.ts
git commit -m "test: require readable light-mode prototype text"
```

---

### Task 8: Implement Light-Mode Readability Cleanup

**Files:**

- Modify: `docs/designs/specs/prototypes/page-home.html`
- Modify: `docs/designs/specs/prototypes/page-a-shares.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
- Modify: `docs/designs/specs/prototypes/page-platform-settings.html`
- Test: `scripts/prototype-design-consistency.test.ts`

- [ ] **Step 1: Add local light-readable token to each selected page**

In each selected page, add this local override inside its page-level light theme block. If the page already has `[data-theme="light"] .page-root` or `[data-theme="light"] .shell-*`, add it there.

```css
    [data-theme="light"] .shell-command,
    [data-theme="light"] .shell-radar,
    [data-theme="light"] .studio-shell,
    [data-theme="light"] .config-shell {
      --prototype-light-readable-text: var(--neutral-600);
      --prototype-light-muted-text: var(--neutral-500);
    }
```

Use the selector that matches the page root:

- `page-home.html`: `.shell-command`
- `page-a-shares.html`: `.shell-radar`
- `page-strategy-studio.html`: `.studio-shell`
- `page-platform-settings.html`: `.config-shell`

- [ ] **Step 2: Route weak labels through the readable token**

For each selected page, update local weak-label rules that currently use `var(--text-quaternary)` in dense operational labels to use:

```css
      color: var(--prototype-light-readable-text);
```

Keep background/helper copy that is intentionally quiet on `var(--text-tertiary)` when it is not a decision label.

- [ ] **Step 3: Keep A-Shares map light scale separate from dark scale**

Confirm `page-a-shares.html` still contains the existing light map aliases.

```css
      --heat-up-1: var(--map-light-up-1);
      --heat-up-2: var(--map-light-up-2);
      --heat-up-3: var(--map-light-up-3);
      --heat-up-4: var(--map-light-up-4);
      --heat-down-1: var(--map-light-down-1);
      --heat-down-2: var(--map-light-down-2);
      --heat-down-3: var(--map-light-down-3);
      --heat-down-4: var(--map-light-down-4);
```

- [ ] **Step 4: Run light-mode readability gate**

Run:

```bash
bun vitest run scripts/prototype-design-consistency.test.ts -t "light-mode prototype weak text"
```

Expected: PASS.

- [ ] **Step 5: Regenerate visual matrix**

Run:

```bash
bun run prototype:visual-matrix
```

Expected: `Generated 28 visual matrix screenshots in /home/chevy/projects/ditto-app/test-results/edition-review/visual-matrix`.

- [ ] **Step 6: Manually inspect the four light screenshots**

Open these screenshots and confirm weak labels are readable without making the page visually noisy.

```text
test-results/edition-review/visual-matrix/home/light-compact.png
test-results/edition-review/visual-matrix/a-shares/light-compact.png
test-results/edition-review/visual-matrix/strategy-studio/light-comfortable.png
test-results/edition-review/visual-matrix/platform-settings/light-compact.png
```

- [ ] **Step 7: Commit light-mode cleanup**

```bash
git add docs/designs/specs/prototypes/page-home.html docs/designs/specs/prototypes/page-a-shares.html docs/designs/specs/prototypes/page-strategy-studio.html docs/designs/specs/prototypes/page-platform-settings.html scripts/prototype-design-consistency.test.ts test-results/edition-review/visual-matrix
git commit -m "fix: improve light-mode prototype readability"
```

---

### Task 9: Run Full Excellent Verification and Record Results

**Files:**

- Create: `docs/reviews/2026-05-11-prototype-excellent-optimization-results.md`
- Test: full project verification

- [ ] **Step 1: Run deterministic detector on active HTML**

Run:

```bash
npx impeccable --json --fast $(bun -e "import { readFileSync } from 'node:fs'; const m=JSON.parse(readFileSync('docs/designs/specs/prototypes/.edition-manifest.json','utf8')); const archived=new Set(['ai-overview','ai-copilot']); const active=m.pages.filter(p=>p.file?.startsWith('page-')&&p.file.endsWith('.html')&&p.id!=='token-showcase'&&p.status!=='archived-specimen'&&!archived.has(p.id)); process.stdout.write(active.map(p=>'docs/designs/specs/prototypes/'+p.file).join(' '));")
```

Expected:

```json
[]
```

- [ ] **Step 2: Run full prototype tests**

Run:

```bash
bun vitest run scripts/page-a-shares-prototype.test.ts scripts/prototype-expert-efficiency.test.ts scripts/prototype-design-consistency.test.ts scripts/prototype-interaction-ux-contract.test.ts
```

Expected: PASS for every selected test file.

- [ ] **Step 3: Run visual gates**

Run:

```bash
bun run prototype:gates
```

Expected: `prototype:gates passed for every active route prototype.`

- [ ] **Step 4: Run full project check**

Run:

```bash
bun run check
```

Expected: Biome passes, TypeScript passes, and Vitest exits 0.

- [ ] **Step 5: Create final review record**

Create `docs/reviews/2026-05-11-prototype-excellent-optimization-results.md` with this content, filling the test counts from the fresh command output.

```markdown
# Prototype Excellent Optimization Results

> 日期：2026-05-11
> 范围：`docs/designs/specs/prototypes/` 28 个 active route prototypes
> 目标：Good-high → Excellent

## 1. 结论

active prototype 集已达到 Excellent 冻结标准。Graphite Studio 方向保持不变，本轮只加强了 A-Shares 市场结构图语义、复杂页首屏决策预算、高风险动作说明和浅色模式可读性。

## 2. 完成项

- A-Shares Treemap 明确 `Size 成交额占比`、`Color 涨跌幅（A股：红涨绿跌）`、`Grouping 申万一级`。
- A-Shares Treemap cells 使用方向符号、文本、aria label 和 label budget，不依赖颜色单独传达涨跌。
- Alpha Explorer、Agent Console V2、Strategy Studio、Instrument Hub 均有首屏 `data-decision-cluster`，可见决策选项不超过 4 个。
- 高风险动作覆盖对象、影响范围、确认、取消、恢复路径和非颜色危险标记。
- Home、A-Shares、Strategy Studio、Platform Settings 浅色模式弱文本通过 readable token 收口。

## 3. 验证

```bash
npx impeccable --json --fast <28 active html>
```

结果：`[]`

```bash
bun vitest run scripts/page-a-shares-prototype.test.ts scripts/prototype-expert-efficiency.test.ts scripts/prototype-design-consistency.test.ts scripts/prototype-interaction-ux-contract.test.ts
```

结果：PASS

```bash
bun run prototype:gates
```

结果：28/28 active route prototypes PASS

```bash
bun run check
```

结果：PASS

## 4. 剩余 React 落地注意事项

- 将 prototype 的高风险确认合同映射为真实状态机，不能只复制静态文案。
- 将 A-Shares Treemap/Heatmap 的 size/color/grouping 作为 chart adapter 输入合同。
- 保持复杂页 `data-decision-cluster` 的 4 选项预算，新增动作默认进入 command 或 overflow。
- 浅色模式进入 React 后继续跑视觉矩阵，防止组件实现回退到弱对比。
```

- [ ] **Step 6: Commit final review record**

```bash
git add docs/reviews/2026-05-11-prototype-excellent-optimization-results.md
git commit -m "docs: record prototype excellent optimization"
```

---

## Self-Review

Spec coverage:

- A-Shares Treemap 紫青语义风险 is covered by Task 1 and Task 2 through explicit A-share red/green copy, market-up/down local variables, sign markers, label budget, and aria text.
- Excellent upgrade path is covered by Tasks 3 through 8: cognitive load, danger gates, light readability, visual verification.
- Existing project constraints are respected: no new dependencies, no npm/yarn/pnpm, no token changes without approval, no React implementation.
- Verification is covered by Task 9 with detector, targeted tests, visual gates, and `bun run check`.

Placeholder scan:

- The plan contains no placeholder markers or undefined future work items.
- Each code-changing task includes concrete code blocks or exact text replacements.
- Commands include expected outcomes.

Type and name consistency:

- `data-decision-cluster`, `data-decision-option`, `data-decision-overflow`, `data-decision-evidence`, and `data-background-evidence` are introduced in Task 3 and used consistently in Task 4.
- `data-risk-object`, `data-impact-summary`, `data-confirm-control`, `data-cancel-control`, `data-recovery-hint`, and `data-danger-marker` are required in Task 5 and implemented in Task 6.
- A-Shares map variables consistently use `--map-market-up-*` and `--map-market-down-*` after Task 2.

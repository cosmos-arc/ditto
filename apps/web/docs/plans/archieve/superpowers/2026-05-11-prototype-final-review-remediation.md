# Prototype Final Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final-review blockers found in `docs/designs/specs/prototypes/` so the active route prototypes can move from conditional pass to freeze-ready: audited label controls are keyboard/AT explicit, Platform Settings form labels are bound, shipped copy contains no visible draft wording, Cross Market right-rail drivers do not overflow, and the fixes are protected by regression tests.

**Architecture:** Preserve the existing static prototype system and Graphite Studio direction. Add one focused Vitest/JSDOM/Playwright regression file first, then make minimal HTML/CSS edits in the affected prototype pages. Do not add dependencies, do not change design tokens, and do not reshape page IA in this remediation pass.

**Tech Stack:** Bun, Vitest, JSDOM, Playwright, static HTML/CSS prototypes, existing shared prototype interactions, `npx impeccable --json --fast`.

---

## Scope

In scope:

- Final-review P1 accessibility blockers on label-driven controls.
- Final-review P1 form-label binding blockers on Platform Settings.
- Final-review P1 shipped-copy cleanup for visible and `aria-label` occurrences of `占位`.
- Targeted P2 Cross Market right-rail overflow fix at 1440px, 1366px, and 1200px widths.
- Regression gates for every item above.
- Final evidence record.

Out of scope:

- Broad decision-load / information-architecture redesign across Orders Ledger, Markets Screener, and Instrument Hub. That work should be planned separately because it changes prioritization and action grouping across multiple product surfaces.
- React implementation.
- New dependencies.
- Design-token changes.
- Contract schema changes.

## File Structure

- Create `scripts/prototype-final-review-remediation.test.ts`
  - Owns final-review regression gates for audited labels, Platform Settings labels, shipped-copy wording, and Cross Market driver overflow.
- Modify `docs/designs/specs/prototypes/page-research.html`
  - Owns audited inline review/detail label triggers.
- Modify `docs/designs/specs/prototypes/page-trading-overview.html`
  - Owns audited pipeline-stage label triggers.
- Modify `docs/designs/specs/prototypes/page-a-shares.html`
  - Owns audited Northbound context and right-rail expand label triggers.
- Modify `docs/designs/specs/prototypes/page-cross-market.html`
  - Owns Cross Market pair-chart copy and macro-driver overflow behavior.
- Modify `docs/designs/specs/prototypes/page-risk-center.html`
  - Owns Risk Center history chart copy and semantic chart replacement.
- Modify `docs/designs/specs/prototypes/page-platform-settings.html`
  - Owns Settings form control labels and non-native grouped field labels.
- Create `docs/reviews/2026-05-11-prototype-final-review-remediation-results.md`
  - Records commands, screenshots if produced, remaining caveats, and final score.

## Execution Rules

- Preserve existing dirty worktree changes; never revert unrelated files.
- Use `apply_patch` for manual edits.
- Use `bun`, never npm/yarn/pnpm.
- Start with failing tests, then make the smallest page edits that turn them green.
- Run `bun run check` before claiming completion.

---

### Task 1: Add Final-Review Regression Gates

**Files:**

- Create: `scripts/prototype-final-review-remediation.test.ts`
- Test: `scripts/prototype-final-review-remediation.test.ts`

- [ ] **Step 1: Create the test file**

Create `scripts/prototype-final-review-remediation.test.ts` with this content:

```ts
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const prototypesDir = join(__dirname, "../docs/designs/specs/prototypes");

function readPage(file: string): string {
	return readFileSync(join(prototypesDir, file), "utf8");
}

function loadDocument(file: string): Document {
	return new JSDOM(readPage(file)).window.document;
}

function accessibleName(element: Element): string {
	return [
		element.getAttribute("aria-label"),
		element.getAttribute("title"),
		element.textContent,
	]
		.filter(Boolean)
		.join(" ")
		.replace(/\s+/g, " ")
		.trim();
}

function visibleBodyText(document: Document): string {
	const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
		acceptNode(node) {
			const parent = node.parentElement;
			if (!parent) return NodeFilter.FILTER_REJECT;
			if (["SCRIPT", "STYLE", "TEMPLATE", "NOSCRIPT"].includes(parent.tagName)) {
				return NodeFilter.FILTER_REJECT;
			}
			return NodeFilter.FILTER_ACCEPT;
		},
	});

	const chunks: string[] = [];
	let node = walker.nextNode();
	while (node) {
		const text = node.textContent?.replace(/\s+/g, " ").trim();
		if (text) chunks.push(text);
		node = walker.nextNode();
	}

	return chunks.join(" ");
}

const activePrototypeFiles = readdirSync(prototypesDir)
	.filter((file) => /^page-[a-z0-9-]+\.html$/.test(file))
	.sort();

const auditedActionLabels = [
	{
		file: "page-research.html",
		selector: 'label.inline-action-link[for="overlay-run-detail"]',
		expectedName: /价值因子 Q1 回测详情/,
	},
	{
		file: "page-research.html",
		selector: 'label.inline-action-link[for="overlay-review-action"]',
		expectedName: /行业轮动参数优化.*审核/,
	},
	{
		file: "page-trading-overview.html",
		selector: 'label.pipeline-stage[for="pipeline-signal-pool"]',
		expectedName: /信号池.*4/,
	},
	{
		file: "page-trading-overview.html",
		selector: 'label.pipeline-stage[for="pipeline-pending"]',
		expectedName: /待复核.*2/,
	},
	{
		file: "page-trading-overview.html",
		selector: 'label.pipeline-stage[for="pipeline-ordered"]',
		expectedName: /已下单.*3/,
	},
	{
		file: "page-trading-overview.html",
		selector: 'label.pipeline-stage[for="pipeline-filled"]',
		expectedName: /已成交.*47/,
	},
	{
		file: "page-a-shares.html",
		selector: 'label.context-bar-item[for="overlay-northbound-detail"]',
		expectedName: /北向.*12/,
	},
	{
		file: "page-a-shares.html",
		selector: 'label.rail-section-expand[for="overlay-northbound-detail"]',
		expectedName: /北向资金.*展开/,
	},
	{
		file: "page-cross-market.html",
		selector: 'label.pair-chart-close[for="pair-chart"]',
		expectedName: /关闭.*走势对比/,
	},
] as const;

describe("prototype final review remediation gates", () => {
	it("keeps audited label-driven actions keyboard reachable and explicitly named", () => {
		const failures: string[] = [];

		for (const target of auditedActionLabels) {
			const document = loadDocument(target.file);
			const label = document.querySelector<HTMLLabelElement>(target.selector);

			if (!label) {
				failures.push(`${target.file}: missing ${target.selector}`);
				continue;
			}

			const control = document.getElementById(label.htmlFor);
			if (!control) failures.push(`${target.file}: ${target.selector} points to missing #${label.htmlFor}`);
			if (label.getAttribute("role") !== "button") failures.push(`${target.file}: ${target.selector} needs role="button"`);
			if (label.getAttribute("tabindex") !== "0") failures.push(`${target.file}: ${target.selector} needs tabindex="0"`);
			if (!target.expectedName.test(accessibleName(label))) {
				failures.push(`${target.file}: ${target.selector} needs accessible name matching ${target.expectedName}`);
			}
		}

		expect(failures).toEqual([]);
	});

	it("binds Platform Settings visible form labels to controls or named groups", () => {
		const document = loadDocument("page-platform-settings.html");
		const failures: string[] = [];

		for (const label of document.querySelectorAll<HTMLLabelElement>("label.form-label")) {
			if (!label.htmlFor) {
				failures.push(`label "${accessibleName(label)}" is missing for=""`);
				continue;
			}

			const control = document.getElementById(label.htmlFor);
			if (!control) failures.push(`label "${accessibleName(label)}" points to missing #${label.htmlFor}`);
		}

		for (const group of document.querySelectorAll<HTMLElement>("[role='group'][aria-labelledby]")) {
			const labelId = group.getAttribute("aria-labelledby");
			if (!labelId || !document.getElementById(labelId)) {
				failures.push(`group "${accessibleName(group)}" points to missing #${labelId ?? ""}`);
			}
		}

		expect(failures).toEqual([]);
	});

	it("does not ship visible text or aria labels containing 占位 in active route prototypes", () => {
		const failures: string[] = [];

		for (const file of activePrototypeFiles) {
			const document = loadDocument(file);
			const visibleText = visibleBodyText(document);

			if (visibleText.includes("占位")) failures.push(`${file}: visible body text contains 占位`);

			for (const element of document.querySelectorAll<HTMLElement>("[aria-label]")) {
				const ariaLabel = element.getAttribute("aria-label") ?? "";
				if (ariaLabel.includes("占位")) {
					failures.push(`${file}: aria-label contains 占位 -> ${ariaLabel}`);
				}
			}
		}

		expect(failures).toEqual([]);
	});

	it("keeps Cross Market macro driver items inside the strip at desktop review widths", async () => {
		const browser = await chromium.launch({ headless: true });
		const page = await browser.newPage();

		try {
			for (const width of [1440, 1366, 1200]) {
				await page.setViewportSize({ width, height: 1000 });
				await page.goto(pathToFileURL(join(prototypesDir, "page-cross-market.html")).href);
				await page.waitForLoadState("domcontentloaded");

				const overflowingItems = await page.locator(".drivers-strip").evaluate((strip) => {
					const stripRect = strip.getBoundingClientRect();
					return Array.from(strip.querySelectorAll(".driver-item"))
						.map((item) => {
							const rect = item.getBoundingClientRect();
							return {
								name: item.textContent?.replace(/\s+/g, " ").trim(),
								left: rect.left,
								right: rect.right,
								stripLeft: stripRect.left,
								stripRight: stripRect.right,
								viewportRight: window.innerWidth,
							};
						})
						.filter((item) => item.left < item.stripLeft - 0.5 || item.right > item.stripRight + 0.5 || item.right > item.viewportRight + 0.5);
				});

				expect(overflowingItems, `${width}px`).toEqual([]);
			}
		} finally {
			await browser.close();
		}
	});
});
```

- [ ] **Step 2: Run the new test and confirm it fails for the known issues**

```bash
bun test scripts/prototype-final-review-remediation.test.ts
```

Expected result before remediation:

- The audited action label test reports missing `role`, `tabindex`, or accessible names.
- The Platform Settings label test reports unbound `.form-label` labels.
- The shipped-copy test reports `page-risk-center.html` and `page-cross-market.html`.
- The Cross Market overflow test reports at least one overflowing `.driver-item` at a desktop width.

- [ ] **Step 3: Commit only the failing test gate when working on a branch**

```bash
git add scripts/prototype-final-review-remediation.test.ts
git commit -m "test prototype final review blockers"
```

---

### Task 2: Make Audited Label Actions Explicit Controls

**Files:**

- Modify: `docs/designs/specs/prototypes/page-research.html`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
- Modify: `docs/designs/specs/prototypes/page-a-shares.html`
- Modify: `docs/designs/specs/prototypes/page-cross-market.html`
- Test: `scripts/prototype-final-review-remediation.test.ts`
- Existing protection: `docs/designs/specs/prototypes/shared/prototype-interactions.js` already activates `[role="button"]` with Enter and Space.

- [ ] **Step 1: Update Research inline action labels**

In `page-research.html`, replace:

```html
<label for="overlay-run-detail" class="inline-action-link">查看详情</label>
```

with:

```html
<label for="overlay-run-detail" class="inline-action-link" role="button" tabindex="0" aria-label="查看价值因子 Q1 回测详情">查看详情</label>
```

Replace:

```html
<label for="overlay-review-action" class="inline-action-link tight">审核</label>
```

with:

```html
<label for="overlay-review-action" class="inline-action-link tight" role="button" tabindex="0" aria-label="审核行业轮动参数优化">审核</label>
```

- [ ] **Step 2: Update Trading Overview pipeline labels**

In `page-trading-overview.html`, update the four `.pipeline-stage` labels:

```html
<label class="pipeline-stage" for="pipeline-signal-pool" role="button" tabindex="0" aria-label="展开信号池，4 个待处理信号" data-tooltip="信号池中的待处理信号 · 点击展开">
```

```html
<label class="pipeline-stage" for="pipeline-pending" role="button" tabindex="0" aria-label="展开待复核信号，2 个等待人工复核" data-tooltip="等待人工复核的信号 · 点击展开">
```

```html
<label class="pipeline-stage" for="pipeline-ordered" role="button" tabindex="0" aria-label="展开已下单队列，3 个订单未完全成交" data-tooltip="已提交但未完全成交的订单 · 点击展开">
```

```html
<label class="pipeline-stage" for="pipeline-filled" role="button" tabindex="0" aria-label="展开已成交记录，今日 47 笔完全成交" data-tooltip="今日已完全成交的订单 · 点击展开">
```

- [ ] **Step 3: Update A-Shares Northbound labels**

In `page-a-shares.html`, replace the Northbound context-bar label opening tag with:

```html
<label for="overlay-northbound-detail" class="context-bar-item cursor-pointer" title="查看北向资金详情" role="button" tabindex="0" aria-label="查看北向资金详情，当前净流入 12 亿">
```

Replace the right-rail expand label with:

```html
<label for="overlay-northbound-detail" class="rail-section-expand cursor-pointer" role="button" tabindex="0" aria-label="展开北向资金分时曲线与持仓明细" data-tooltip="查看北向资金分时曲线与持仓明细">展开 →</label>
```

- [ ] **Step 4: Update Cross Market pair-chart close label**

In `page-cross-market.html`, replace:

```html
<label for="pair-chart" class="pair-chart-close" aria-label="关闭走势对比">关闭</label>
```

with:

```html
<label for="pair-chart" class="pair-chart-close" role="button" tabindex="0" aria-label="关闭黄金 vs 美元走势对比">关闭</label>
```

- [ ] **Step 5: Run the focused accessibility gate**

```bash
bun test scripts/prototype-final-review-remediation.test.ts -- -t "label-driven actions"
```

Expected result:

- The audited label-driven action test passes.

---

### Task 3: Bind Platform Settings Form Labels

**Files:**

- Modify: `docs/designs/specs/prototypes/page-platform-settings.html`
- Test: `scripts/prototype-final-review-remediation.test.ts`

- [ ] **Step 1: Bind Wind editor native controls**

In the Wind editor `.config-form-grid`, replace the four native-control rows with:

```html
<div class="form-group"><label class="form-label" for="datasource-api-host">API Host</label><input id="datasource-api-host" class="form-input" type="text" value="https://api.wind.local"></div>
<div class="form-group"><label class="form-label" for="datasource-sync-frequency">同步频率</label><select id="datasource-sync-frequency" class="form-input form-select"><option selected>60s polling</option><option>30s polling</option></select></div>
<div class="form-group"><label class="form-label" for="datasource-timeout-threshold">超时阈值</label><input id="datasource-timeout-threshold" class="form-input" type="text" value="850ms"></div>
<div class="form-group"><label class="form-label" for="datasource-retry-count">失败重试</label><input id="datasource-retry-count" class="form-input" type="text" value="3 attempts"></div>
```

Replace the latency row opening label/group with:

```html
<div class="form-group full"><div class="form-label" id="datasource-latency-trend-label">延迟趋势</div><div class="latency-strip" role="img" aria-labelledby="datasource-latency-trend-label" aria-label="Wind 最近 12 次延迟趋势">
```

- [ ] **Step 2: Bind broker editor native controls and grouped trade protection**

Replace the four broker native-control rows with:

```html
<div class="form-group"><label class="form-label" for="broker-account-alias">账户别名</label><input id="broker-account-alias" class="form-input" type="text" value="CITIC Paper A"></div>
<div class="form-group"><label class="form-label" for="broker-trading-mode">交易模式</label><select id="broker-trading-mode" class="form-input form-select"><option selected>模拟盘</option><option>实盘只读</option></select></div>
<div class="form-group"><label class="form-label" for="broker-counter-url">柜台地址</label><input id="broker-counter-url" class="form-input" type="text" value="xtp.paper.local:18888"></div>
<div class="form-group"><label class="form-label" for="broker-order-limit">下单限额</label><input id="broker-order-limit" class="form-input" type="text" value="500,000 CNY"></div>
```

Replace the trade-protection label/group opening with:

```html
<div class="form-group full"><div class="form-label" id="broker-trade-protection-label">交易保护</div><div role="group" aria-labelledby="broker-trade-protection-label">
```

Keep the two existing `.toggle-row` entries inside that group and close the new group before the existing form hint or row close.

- [ ] **Step 3: Bind General Settings native controls**

Replace the six general setting rows with:

```html
<div class="form-group"><label class="form-label" for="general-default-market">默认市场</label><select id="general-default-market" class="form-input form-select"><option selected>A股（沪深）</option><option>港股</option><option>美股</option></select></div>
<div class="form-group"><label class="form-label" for="general-timezone">时区</label><select id="general-timezone" class="form-input form-select"><option selected>Asia/Shanghai (UTC+8)</option><option>America/New_York (UTC-5)</option></select></div>
<div class="form-group"><label class="form-label" for="general-language">界面语言</label><select id="general-language" class="form-input form-select"><option selected>简体中文</option><option>English</option></select></div>
<div class="form-group"><label class="form-label" for="general-notifications">通知偏好</label><select id="general-notifications" class="form-input form-select"><option>全部通知</option><option selected>仅重要通知</option><option>静默</option></select></div>
<div class="form-group"><label class="form-label" for="general-fee-rate">默认手续费率</label><input id="general-fee-rate" class="form-input" type="text" value="0.025%"></div>
<div class="form-group"><label class="form-label" for="general-slippage">默认滑点</label><input id="general-slippage" class="form-input" type="text" value="0.01%"></div>
```

- [ ] **Step 4: Run the focused Platform Settings gate**

```bash
bun test scripts/prototype-final-review-remediation.test.ts -- -t "Platform Settings"
```

Expected result:

- The Platform Settings label-binding test passes.

---

### Task 4: Remove Shipped Draft Wording From User-Facing Surfaces

**Files:**

- Modify: `docs/designs/specs/prototypes/page-risk-center.html`
- Modify: `docs/designs/specs/prototypes/page-cross-market.html`
- Test: `scripts/prototype-final-review-remediation.test.ts`

- [ ] **Step 1: Replace Risk Center visible draft wording with semantic trend content**

In `page-risk-center.html`, replace:

```html
<div class="history-chart-placeholder">
  <span class="placeholder-label">历史对比图表占位</span>
</div>
```

with:

```html
<div class="history-chart-placeholder" role="img" aria-label="历史压力测试对比，展示最近 6 次组合损益、尾部风险与突破次数">
  <svg class="history-chart-svg" viewBox="0 0 260 72" aria-hidden="true" focusable="false">
    <path class="history-chart-grid" d="M8 12H252M8 36H252M8 60H252" />
    <path class="history-chart-loss-line" d="M10 50L52 44L94 48L136 34L178 39L220 28L250 31" />
    <path class="history-chart-tail-line" d="M10 42L52 38L94 40L136 31L178 34L220 24L250 27" />
    <circle class="history-chart-dot loss" cx="220" cy="28" r="3" />
    <circle class="history-chart-dot tail" cx="220" cy="24" r="3" />
  </svg>
  <span class="placeholder-label">近 6 次压力测试 · 损益 / 尾部风险</span>
</div>
```

Add these CSS rules near the existing `.history-chart-placeholder` block:

```css
.history-chart-svg {
  width: 100%;
  max-width: 16.25rem;
  height: 4.5rem;
}

.history-chart-grid {
  stroke: var(--border-subtle);
  stroke-width: 1;
  opacity: 0.45;
}

.history-chart-loss-line,
.history-chart-tail-line {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
}

.history-chart-loss-line {
  stroke: var(--system-warning-fg);
}

.history-chart-tail-line {
  stroke: var(--system-critical-fg);
  opacity: 0.75;
}

.history-chart-dot {
  fill: currentColor;
}

.history-chart-dot.loss {
  color: var(--system-warning-fg);
}

.history-chart-dot.tail {
  color: var(--system-critical-fg);
}
```

- [ ] **Step 2: Replace Cross Market pair-chart aria label**

In `page-cross-market.html`, replace:

```html
<div class="pair-chart-placeholder" role="img" aria-label="黄金 vs 美元走势对比图（占位）">
```

with:

```html
<div class="pair-chart-placeholder" role="img" aria-label="黄金 vs 美元 30 日走势对比图，黄金以金色折线呈现，美元以蓝色折线呈现">
```

- [ ] **Step 3: Run the shipped-copy gate**

```bash
bun test scripts/prototype-final-review-remediation.test.ts -- -t "占位"
```

Expected result:

- No active route prototype has visible body text or `aria-label` containing `占位`.

---

### Task 5: Fix Cross Market Macro Driver Overflow

**Files:**

- Modify: `docs/designs/specs/prototypes/page-cross-market.html`
- Test: `scripts/prototype-final-review-remediation.test.ts`
- Visual QA: `/tmp/ditto-prototype-final-review-remediation/cross-market-1440.png`

- [ ] **Step 1: Replace desktop driver strip layout with a non-overflowing grid**

In `page-cross-market.html`, replace the current `.drivers-strip` block with:

```css
.drivers-strip {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
  flex-shrink: 1;
  min-width: 0;
  padding: var(--space-8) 0;
  margin-top: calc(var(--space-8) * -1);
  overflow: hidden;
}
```

Replace the current `.driver-item` block with:

```css
.driver-item {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  min-width: 0;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-3);
  background: none;
  white-space: nowrap;
  font-size: var(--font-size-12);
  flex-shrink: 1;
  transition: background var(--motion-duration-fast) var(--motion-easing-standard);
}
```

Add this rule after `.driver-item`:

```css
.driver-item-name,
.driver-item-val,
.driver-item-change {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

Replace `.driver-mini-bar` with:

```css
.driver-mini-bar {
  width: 1rem;
  height: 3px;
  border-radius: var(--radius-2);
  flex: 0 0 1rem;
}
```

In the existing `@media (max-width: 1366px)` block, keep the `.drivers-strip` grid declaration and remove duplicate `.driver-mini-bar` width overrides if they now match the base rule.

- [ ] **Step 2: Run the Cross Market overflow gate**

```bash
bun test scripts/prototype-final-review-remediation.test.ts -- -t "Cross Market macro driver"
```

Expected result:

- The overflow test passes for 1440px, 1366px, and 1200px.

- [ ] **Step 3: Capture a desktop visual proof**

```bash
mkdir -p /tmp/ditto-prototype-final-review-remediation
bunx playwright screenshot "file://$PWD/docs/designs/specs/prototypes/page-cross-market.html" /tmp/ditto-prototype-final-review-remediation/cross-market-1440.png --viewport-size=1440,1000
```

Expected result:

- The screenshot exists and the macro driver strip is inside the right rail without horizontal clipping.

---

### Task 6: Run Full Prototype and Project Verification

**Files:**

- Test: `scripts/prototype-final-review-remediation.test.ts`
- Test: `scripts/prototype-interaction-ux-contract.test.ts`
- Test: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/prototype-full-directory-visual-audit.test.ts`
- Create: `docs/reviews/2026-05-11-prototype-final-review-remediation-results.md`

- [ ] **Step 1: Run focused and adjacent prototype tests**

```bash
bun test scripts/prototype-final-review-remediation.test.ts
bun test scripts/prototype-interaction-ux-contract.test.ts scripts/prototype-design-consistency.test.ts scripts/prototype-full-directory-visual-audit.test.ts
```

Expected result:

- All focused final-review gates pass.
- Existing interaction, design-consistency, and full-directory visual gates pass.

- [ ] **Step 2: Run the design-audit CLI**

```bash
npx impeccable --json --fast docs/designs/specs/prototypes
```

Expected result:

- No new high-severity findings.
- Existing Inter/font false positives may remain if the CLI still reports `shared/fonts.css`; record them as accepted because the design register specifies Inter.
- Existing CSS triangle false positive may remain for `shared/layout-components.css`; record it as accepted if it still points at the side-tab arrow border.

- [ ] **Step 3: Run the project gate**

```bash
bun run check
```

Expected result:

- Biome passes.
- TypeScript passes.
- Vitest passes.

- [ ] **Step 4: Record final evidence**

Create `docs/reviews/2026-05-11-prototype-final-review-remediation-results.md`:

```md
# Prototype Final Review Remediation Results

Date: 2026-05-11
Scope: `docs/designs/specs/prototypes/`

## Changes

- Closed audited label-driven action accessibility blockers.
- Bound Platform Settings form labels to controls or named groups.
- Removed user-facing `占位` wording from active route prototypes.
- Fixed Cross Market macro driver overflow at desktop review widths.

## Verification

- `bun test scripts/prototype-final-review-remediation.test.ts`: pass
- `bun test scripts/prototype-interaction-ux-contract.test.ts scripts/prototype-design-consistency.test.ts scripts/prototype-full-directory-visual-audit.test.ts`: pass
- `npx impeccable --json --fast docs/designs/specs/prototypes`: pass with accepted low/false positives listed below
- `bun run check`: pass

## Accepted CLI Findings

- `shared/fonts.css` Inter overuse finding: accepted false positive because PRODUCT/DESIGN define Inter as the product UI font.
- `shared/layout-components.css` side-tab border finding: accepted false positive if the line still points to the CSS triangle arrow.

## Remaining Caveat

Broad decision-load restructuring across Orders Ledger, Markets Screener, and Instrument Hub remains a separate IA pass. This remediation closes the freeze-blocking accessibility, shipped-copy, and overflow issues from the final review.
```

- [ ] **Step 5: Commit the remediation when working on a branch**

```bash
git add scripts/prototype-final-review-remediation.test.ts \
  docs/designs/specs/prototypes/page-research.html \
  docs/designs/specs/prototypes/page-trading-overview.html \
  docs/designs/specs/prototypes/page-a-shares.html \
  docs/designs/specs/prototypes/page-cross-market.html \
  docs/designs/specs/prototypes/page-risk-center.html \
  docs/designs/specs/prototypes/page-platform-settings.html \
  docs/reviews/2026-05-11-prototype-final-review-remediation-results.md
git commit -m "fix prototype final review blockers"
```

---

## Completion Checklist

- [ ] Final-review test file exists and fails before remediation.
- [ ] Audited label-driven actions expose `role="button"`, `tabindex="0"`, and specific accessible names.
- [ ] Platform Settings `.form-label` labels are bound to real controls; non-native groups are named with `aria-labelledby`.
- [ ] No active route prototype exposes visible text or `aria-label` containing `占位`.
- [ ] Cross Market macro drivers do not overflow at 1440px, 1366px, or 1200px.
- [ ] Focused and adjacent prototype tests pass.
- [ ] `npx impeccable --json --fast docs/designs/specs/prototypes` is recorded.
- [ ] `bun run check` passes.
- [ ] Results document is created with commands and accepted caveats.

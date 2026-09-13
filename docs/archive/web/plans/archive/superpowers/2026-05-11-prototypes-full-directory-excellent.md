# Full Prototype Directory Excellent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring every HTML surface under `prototype/` to Excellent quality, including active route prototypes, legacy non-active specimens, archive specimens, and the Graphite Studio token showcase.

**Architecture:** Treat this as one prototype-quality subsystem because all changes live in the static prototype layer and its Vitest/Playwright gates. Add full-directory regression gates first, then apply small, local HTML/CSS fixes for detector-clean motion, responsive geometry, explicit accessible names, and final review evidence. Keep Graphite Studio direction, current design tokens, and existing prototype architecture intact.

**Tech Stack:** Bun, Vitest, JSDOM, Playwright, static HTML/CSS prototypes, `npx impeccable --json --fast`, existing prototype gate scripts.

---

## Scope

Target quality bar: **Excellent for the whole prototype directory**, not only the 28 active route prototypes.

Included:

- 28 active route prototypes from `.edition-manifest.json`.
- Non-active canonical-adjacent prototype: `page-agent-console.html`.
- Token showcase: `style-b-graphite-studio/token-showcase.html`.
- Archive HTML specimens under `archive/2026-04-30/`.
- Dark and light theme first-screen readability.
- 1536, 1366, and 1200 desktop viewport behavior.
- Interaction basics: no page errors, no document-level horizontal scroll, no default visible overlays, explicit names for icon triggers.
- Visual consistency: no layout-property motion, no bounce-style motion, no detector-triggering generic font sample, no monotone spacing warning in token showcase.

Excluded:

- React implementation.
- New dependencies.
- Global design-token changes.
- Product information architecture changes.
- Mobile structural redesign below the existing prototype viewport contract.

## File Structure

- Modify `scripts/prototype-design-consistency.test.ts`
  - Owns full-directory static quality gates: every prototype HTML file, all inline CSS, archive specimens, token showcase detector invariants, and explicit icon trigger names.
- Create `scripts/prototype-full-directory-visual-audit.test.ts`
  - Owns Playwright geometry and runtime checks for all prototype HTML files and focused high-risk layout selectors.
- Modify `prototype/page-agent-console.html`
  - Removes layout-property progress/resource bar transitions in legacy Agent Console.
- Modify `prototype/archive/2026-04-30/page-ai-overview.html`
  - Removes bounce-named motion and layout-property progress/confidence transitions.
- Modify `prototype/archive/2026-04-30/page-ai-copilot.html`
  - Removes height/width transitions in archive Copilot message/confidence UI.
- Modify `prototype/style-b-graphite-studio/token-showcase.html`
  - Removes detector-triggering width/height/max-height transitions, replaces the direct `Inter` sample override with token usage, and gives spacing demos more rhythm.
- Modify `prototype/page-cross-market.html`
  - Fixes Macro Driver strip geometry in compact/narrow viewports and adds explicit `aria-label` to filter trigger.
- Modify `prototype/page-regime-monitor.html`
  - Fixes heatgrid legend wrapping and text sizing without relying on horizontal overflow.
- Modify `prototype/page-signals-inbox.html`
  - Clamps detail panel/header/body geometry in compact/narrow viewports.
- Modify `prototype/page-trading-overview.html`
  - Fixes status bar width calculation so it remains inside the viewport.
- Modify `prototype/page-backtest-list.html`
  - Clamps active filter count in narrow viewport.
- Modify `prototype/page-experiment-list.html`
  - Clamps active filter count in narrow viewport, including state gallery previews.
- Modify `prototype/page-a-shares.html`
  - Adds explicit names to header icon overlay triggers.
- Modify `prototype/page-markets-intelligence.html`
  - Adds explicit name to custom filter trigger.
- Modify `prototype/page-strategy-studio.html`
  - Adds explicit name/role to delete strategy trigger.
- Create `docs/reviews/2026-05-11-prototype-full-directory-excellent-results.md`
  - Records full-directory evidence and remaining React implementation caveats.

## Execution Rules

- Work in an isolated branch or worktree.
- Use `apply_patch` for manual edits.
- Use Bun commands only.
- Preserve unrelated user changes.
- Run each task-specific test immediately after the related change.
- Run the full verification suite before declaring completion.

---

### Task 1: Add Full-Directory Static Excellent Gates

**Files:**

- Modify: `scripts/prototype-design-consistency.test.ts`
- Test: `scripts/prototype-design-consistency.test.ts`

- [ ] **Step 1: Add recursive full-directory prototype helpers**

Insert this helper block after `function readPrototypeCssSources(): CssSource[] { ... }`:

```ts
function readPrototypeHtmlFilesRecursive(dir = prototypesDir): HtmlSource[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const fullPath = join(dir, entry.name);
		if (entry.isDirectory()) return readPrototypeHtmlFilesRecursive(fullPath);
		if (!entry.isFile() || !entry.name.endsWith(".html")) return [];

		return [
			{
				label: relative(root, fullPath),
				html: readFileSync(fullPath, "utf8"),
			},
		];
	});
}

function readFullPrototypeCssSources(): CssSource[] {
	const inlineSources = readPrototypeHtmlFilesRecursive().map((source) => ({
		label: `${source.label}:inline-css`,
		css: getStyleBlocks(source.html),
	}));

	return [...readPrototypeCssSources(), ...inlineSources];
}
```

- [ ] **Step 2: Add static gates for detector-clean motion and font samples**

Add this test inside `describe("prototype design consistency", () => { ... })`, near the existing CSS regression tests:

```ts
	it("keeps every prototype HTML file free of detector-blocking motion and generic font samples", () => {
		const layoutDrivenTransitionProperties = new Set([
			"width",
			"height",
			"max-width",
			"max-height",
			"min-width",
			"min-height",
			"padding",
			"margin",
			"flex",
			"flex-grow",
			"flex-shrink",
			"flex-basis",
		]);
		const violations: string[] = [];

		for (const source of readFullPrototypeCssSources()) {
			const css = stripCssComments(source.css);

			for (const match of css.matchAll(/transition\s*:\s*([^;}]+)/gi)) {
				const transitionValue = match[1];
				const animatedProperties = transitionValue.split(",").map((item) => item.trim().split(/\s+/)[0]?.toLowerCase() ?? "");

				if (animatedProperties.some((property) => property === "all")) {
					violations.push(`${source.label}:${getLineNumber(css, match.index)}:transition-all`);
				}
				if (animatedProperties.some((property) => layoutDrivenTransitionProperties.has(property))) {
					violations.push(`${source.label}:${getLineNumber(css, match.index)}:layout-transition`);
				}
			}

			for (const match of css.matchAll(/animation\s*:\s*([^;}]+)/gi)) {
				if (/(?:bounce|elastic)/i.test(match[1])) {
					violations.push(`${source.label}:${getLineNumber(css, match.index)}:bounce-animation`);
				}
			}

			for (const match of css.matchAll(/font-family\s*:\s*['"](?:Inter|Roboto|Open Sans|Lato|Montserrat|Arial)\b/gi)) {
				violations.push(`${source.label}:${getLineNumber(css, match.index)}:literal-generic-font-sample`);
			}
		}

		expect(violations).toEqual([]);
	});
```

- [ ] **Step 3: Add explicit-name gate for icon-only overlay triggers**

Add this test after the new static motion test:

```ts
	it("keeps icon-only overlay triggers explicitly named beyond title attributes", () => {
		const violations: string[] = [];

		for (const source of readPrototypeHtmlFilesRecursive()) {
			const document = new JSDOM(source.html).window.document;

			for (const trigger of document.querySelectorAll("label[for], button, [role='button']")) {
				const visibleText = trigger.textContent?.replace(/\s+/g, " ").trim() ?? "";
				const hasIcon = Boolean(trigger.querySelector("svg"));
				const hasExplicitName =
					Boolean(trigger.getAttribute("aria-label")) ||
					Boolean(trigger.getAttribute("aria-labelledby")) ||
					visibleText.length > 0;

				if (hasIcon && !hasExplicitName) {
					const target = trigger.getAttribute("for") ?? trigger.getAttribute("aria-controls") ?? "unknown";
					violations.push(`${source.label}:${target}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});
```

- [ ] **Step 4: Add static geometry contracts for known risk selectors**

Add this test after the explicit-name gate:

```ts
	it("documents compact geometry fixes for final full-directory review risks", () => {
		const checks = [
			{
				page: activePageById("cross-market"),
				expected: [
					/@media\s*\(max-width:\s*1366px\)[\s\S]*\.drivers-strip\s*\{[\s\S]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/,
					/@media\s*\(max-width:\s*1200px\)[\s\S]*\.drivers-strip\s*\{[\s\S]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/,
				],
			},
			{
				page: activePageById("regime-monitor"),
				expected: [
					/\.heatgrid-legend\s*\{[\s\S]*flex-wrap:\s*wrap;/,
					/\.heatgrid-legend\s*\{[\s\S]*max-width:\s*100%;/,
				],
			},
			{
				page: activePageById("signals-inbox"),
				expected: [
					/\.shell-signals\s+\.detail-panel\s*\{[\s\S]*min-width:\s*0;/,
					/\.detail-header,\s*\.detail-body\s*\{[\s\S]*max-width:\s*100%;/,
				],
			},
			{
				page: activePageById("trading-overview"),
				expected: [
					/#default-view\s*>\s*\.status-bar\s*\{[\s\S]*width:\s*auto\s*!important;/,
					/#default-view\s*>\s*\.status-bar\s*\{[\s\S]*max-width:\s*calc\(100vw - var\(--shell-rail-width\)\);/,
				],
			},
			{
				page: activePageById("backtest-list"),
				expected: [/\.filter-count\s*\{[\s\S]*max-width:\s*100%;[\s\S]*overflow:\s*hidden;[\s\S]*text-overflow:\s*ellipsis;/],
			},
			{
				page: activePageById("experiment-list"),
				expected: [/\.filter-count\s*\{[\s\S]*max-width:\s*100%;[\s\S]*overflow:\s*hidden;[\s\S]*text-overflow:\s*ellipsis;/],
			},
		];
		const violations: string[] = [];

		for (const check of checks) {
			const html = readPrototypeHtml(check.page);
			for (const pattern of check.expected) {
				if (!pattern.test(html)) {
					violations.push(`${check.page.id}:${pattern.source.slice(0, 80)}`);
				}
			}
		}

		expect(violations).toEqual([]);
	});
```

- [ ] **Step 5: Run the new static gates and verify they fail before implementation**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: FAIL with violations that include `page-agent-console.html`, `page-ai-overview.html`, `page-ai-copilot.html`, `token-showcase.html`, and known geometry contracts.

- [ ] **Step 6: Commit the failing gates**

```bash
git add scripts/prototype-design-consistency.test.ts
git commit -m "test: cover full prototype directory excellence gates"
```

---

### Task 2: Fix Non-Active and Archive Detector Findings

**Files:**

- Modify: `prototype/page-agent-console.html`
- Modify: `prototype/archive/2026-04-30/page-ai-overview.html`
- Modify: `prototype/archive/2026-04-30/page-ai-copilot.html`
- Modify: `prototype/style-b-graphite-studio/token-showcase.html`
- Test: `scripts/prototype-design-consistency.test.ts`

- [ ] **Step 1: Replace legacy Agent Console layout-property transitions**

In `prototype/page-agent-console.html`, replace the `.progress-bar-fill` and `.resource-bar-fill` transition declarations with transform-friendly declarations:

```css
    .progress-bar-fill {
      height: 100%;
      border-radius: 2px;
      transform-origin: left center;
      transition: transform var(--motion-duration-normal) var(--motion-easing-standard),
                  opacity var(--motion-duration-normal) var(--motion-easing-standard);
    }
```

```css
    .resource-bar-fill {
      height: 100%;
      border-radius: 2px;
      transform-origin: left center;
      transition: transform var(--motion-duration-normal) var(--motion-easing-standard),
                  opacity var(--motion-duration-normal) var(--motion-easing-standard);
    }
```

- [ ] **Step 2: Replace archive AI Overview bounce motion and layout-property transitions**

In `prototype/archive/2026-04-30/page-ai-overview.html`, change these declarations:

```css
    .ai-plan-progress-fill {
      height: 100%;
      border-radius: 2px;
      transform-origin: left center;
      transition: transform var(--motion-duration-normal) var(--motion-easing-standard),
                  opacity var(--motion-duration-normal) var(--motion-easing-standard);
    }

    .ai-thinking-dots span {
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: var(--ai-accent);
      animation: ai-thinking-pulse var(--ai-thinking-speed) var(--motion-easing-standard) infinite;
    }
    .ai-thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
    .ai-thinking-dots span:nth-child(3) { animation-delay: 0.4s; }

    @keyframes ai-thinking-pulse {
      0%, 80%, 100% { opacity: 0.35; transform: scale(0.86); }
      40% { opacity: 1; transform: scale(1); }
    }

    .ai-status-badge.processing .ai-status-dot {
      background: var(--ai-accent);
      animation: ai-thinking-pulse var(--ai-thinking-speed) var(--motion-easing-standard) infinite;
    }

    .ai-confidence-bar-fill {
      height: 100%;
      border-radius: 1px;
      transform-origin: left center;
      transition: transform var(--motion-duration-normal) var(--motion-easing-standard),
                  opacity var(--motion-duration-normal) var(--motion-easing-standard);
    }
```

- [ ] **Step 3: Replace archive AI Copilot layout-property transitions**

In `prototype/archive/2026-04-30/page-ai-copilot.html`, replace the user message accent and confidence fill rules:

```css
    .message--user .message-content::after {
      content: '';
      position: absolute;
      top: 50%;
      right: -8px;
      transform: translateY(-50%) scaleY(0);
      transform-origin: center;
      width: 3px;
      height: 16px;
      border-radius: 2px;
      background: var(--brand-accent);
      opacity: 0;
      transition: transform var(--motion-duration-normal) var(--motion-easing-emphasis),
                  opacity var(--motion-duration-normal) var(--motion-easing-emphasis);
    }
    .message--user:hover .message-content::after {
      transform: translateY(-50%) scaleY(1);
      opacity: 1;
    }

    .confidence-bar-fill {
      height: 100%;
      border-radius: 2px;
      transform-origin: left center;
      transition: transform 0.8s var(--motion-easing-emphasis),
                  opacity 0.8s var(--motion-easing-emphasis);
      position: relative;
    }
```

- [ ] **Step 4: Clean token showcase transitions, font sample, and spacing rhythm**

In `prototype/style-b-graphite-studio/token-showcase.html`, apply these CSS replacements:

```css
    .swatch {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--space-6);
      padding: var(--space-8);
      border-radius: var(--radius-6);
      background: var(--surface-panel-base);
      border: 1px solid var(--border-subtle);
    }

    .spacing-list {
      display: flex;
      flex-direction: column;
      gap: var(--space-6);
    }

    .elevation-stack {
      display: flex;
      flex-direction: column;
      gap: var(--space-8);
    }

    .spacing-bar {
      height: 8px;
      border-radius: var(--radius-2);
      background: var(--brand-accent);
      opacity: 0.6;
      min-width: 4px;
      transform-origin: left center;
      transition: transform var(--motion-duration-normal) var(--motion-easing-standard),
                  opacity var(--motion-duration-normal) var(--motion-easing-standard);
    }

    .progress-fill {
      width: 65%;
      height: 100%;
      border-radius: var(--radius-3);
      background: var(--feedback-progress-fill);
      transform-origin: left center;
      transition: transform 0.6s var(--motion-easing-standard),
                  opacity 0.6s var(--motion-easing-standard);
    }

    .demo-table tbody tr {
      white-space: nowrap;
      height: var(--density-row-height);
      display: flex;
      align-items: center;
      transition: background-color var(--motion-duration-normal) var(--motion-easing-standard),
                  color var(--motion-duration-normal) var(--motion-easing-standard);
    }

    .font-card-sample--ui {
      font-family: var(--font-family-ui);
    }

    .section-fold-body {
      display: grid;
      grid-template-rows: 1fr;
      transition: grid-template-rows 0.3s var(--motion-easing-standard), opacity 0.2s ease;
      overflow: hidden;
    }

    .section-fold-body > * {
      min-height: 0;
      overflow: hidden;
    }

    .section-fold-body.collapsed {
      grid-template-rows: 0fr;
      opacity: 0;
    }
```

- [ ] **Step 5: Run full-directory detector**

Run:

```bash
find prototype -type f -name '*.html' -print0 | xargs -0 npx impeccable --json --fast
```

Expected: exit 0 and output `[]`.

- [ ] **Step 6: Run the static gate**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit detector cleanup**

```bash
git add prototype/page-agent-console.html prototype/archive/2026-04-30/page-ai-overview.html prototype/archive/2026-04-30/page-ai-copilot.html prototype/style-b-graphite-studio/token-showcase.html scripts/prototype-design-consistency.test.ts
git commit -m "fix: make full prototype directory detector clean"
```

---

### Task 3: Fix Active-Route Geometry and Icon Trigger Names

**Files:**

- Modify: `prototype/page-cross-market.html`
- Modify: `prototype/page-regime-monitor.html`
- Modify: `prototype/page-signals-inbox.html`
- Modify: `prototype/page-trading-overview.html`
- Modify: `prototype/page-backtest-list.html`
- Modify: `prototype/page-experiment-list.html`
- Modify: `prototype/page-a-shares.html`
- Modify: `prototype/page-markets-intelligence.html`
- Modify: `prototype/page-strategy-studio.html`
- Test: `scripts/prototype-design-consistency.test.ts`

- [ ] **Step 1: Fix Cross-Market macro driver geometry and filter trigger name**

In `prototype/page-cross-market.html`, add these media rules after `.driver-mini-bar.down { ... }`:

```css
    @media (max-width: 1366px) {
      .drivers-strip {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: var(--space-4);
        overflow: visible;
        width: 100%;
      }

      .driver-item {
        min-width: 0;
        justify-content: space-between;
      }

      .driver-item-name,
      .driver-item-val,
      .driver-item-change {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .driver-mini-bar {
        width: 1rem;
        flex: 0 0 1rem;
      }

      .driver-sep {
        display: none;
      }
    }

    @media (max-width: 1200px) {
      .drivers-strip {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }
    }
```

Change the filter trigger to include an explicit accessible name:

```html
          <label for="overlay-filter-panel" class="header-action-btn cursor-pointer" title="筛选器" aria-label="打开筛选器">
```

- [ ] **Step 2: Fix Regime Monitor heatgrid legend**

In `prototype/page-regime-monitor.html`, replace `.heatgrid-legend` and `.heatgrid-legend-item` with:

```css
    .heatgrid-legend {
      display: flex;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      gap: var(--space-6) var(--space-10);
      max-width: 100%;
      font-size: var(--font-size-12);
      color: var(--text-tertiary);
    }
    .heatgrid-legend-item {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      min-width: 0;
      white-space: nowrap;
    }
```

- [ ] **Step 3: Fix Signals Inbox detail rail geometry**

In `prototype/page-signals-inbox.html`, extend the detail panel rules:

```css
    .shell-signals .detail-panel {
      grid-area: detail;
      background: var(--surface-panel-base);
      border-left: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-width: 0;
      min-height: 0;
    }

    .detail-header,
    .detail-body {
      max-width: 100%;
      min-width: 0;
      box-sizing: border-box;
    }

    .detail-header > div {
      min-width: 0;
    }

    .detail-header-title,
    .detail-header-subtitle {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
```

- [ ] **Step 4: Fix Trading Overview status bar width**

In `prototype/page-trading-overview.html`, replace the `#default-view > .status-bar` block with:

```css
    #default-view > .status-bar {
      position: relative !important;
      bottom: auto !important;
      flex: 0 0 1.5rem !important;
      height: 1.5rem !important;
      margin-left: var(--shell-rail-width);
      width: auto !important;
      max-width: calc(100vw - var(--shell-rail-width));
      box-sizing: border-box;
      overflow: hidden;
    }
```

- [ ] **Step 5: Clamp Backtest List and Experiment List filter counts**

In both `prototype/page-backtest-list.html` and `prototype/page-experiment-list.html`, add this rule after the existing `.filter-count` rule:

```css
    .filter-count {
      max-width: 100%;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
```

For the gallery filter preview in `page-experiment-list.html`, ensure the preview also uses the same class and no inline width override.

- [ ] **Step 6: Add explicit accessible names to remaining icon-only triggers**

Apply these exact HTML changes:

`prototype/page-a-shares.html`:

```html
          <label for="overlay-filter-panel" class="header-action-btn cursor-pointer" title="筛选器" aria-label="打开筛选器">
```

```html
          <label for="overlay-ai-analysis" class="header-action-btn cursor-pointer" title="AI 解读" aria-label="打开 AI 解读">
```

`prototype/page-markets-intelligence.html`:

```html
          <label for="overlay-custom-filter" class="header-action-btn cursor-pointer" title="筛选" aria-label="打开自定义筛选">
```

`prototype/page-strategy-studio.html`:

```html
        <label for="overlay-delete-strategy" class="header-delete-btn" title="删除策略" role="button" aria-label="删除策略" tabindex="0">
```

- [ ] **Step 7: Run static geometry and accessible-name gates**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts
```

Expected: PASS.

- [ ] **Step 8: Run active route prototype gates**

Run:

```bash
bun run prototype:gates
```

Expected: all 28 active route prototypes PASS with no blocking or non-blocking issues.

- [ ] **Step 9: Commit active route polish**

```bash
git add prototype/page-cross-market.html prototype/page-regime-monitor.html prototype/page-signals-inbox.html prototype/page-trading-overview.html prototype/page-backtest-list.html prototype/page-experiment-list.html prototype/page-a-shares.html prototype/page-markets-intelligence.html prototype/page-strategy-studio.html
git commit -m "fix: polish prototype geometry and icon trigger names"
```

---

### Task 4: Add Full-Directory Runtime Visual Audit

**Files:**

- Create: `scripts/prototype-full-directory-visual-audit.test.ts`
- Test: `scripts/prototype-full-directory-visual-audit.test.ts`

- [ ] **Step 1: Create Playwright audit test**

Create `scripts/prototype-full-directory-visual-audit.test.ts` with this content:

```ts
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { chromium, type Browser } from "playwright";

const root = process.cwd();
const prototypesDir = join(root, "prototype");
const navigationTimeoutMs = 20_000;
const auditTimeoutMs = 90_000;
const viewports = [
	{ name: "standard", width: 1536, height: 1080 },
	{ name: "compact", width: 1366, height: 768 },
	{ name: "narrow", width: 1200, height: 800 },
] as const;

type PrototypeFile = {
	id: string;
	path: string;
};

type GeometryTarget = {
	file: string;
	selector: string;
	maxRightOverflowPx?: number;
};

function readPrototypeFiles(dir = prototypesDir): PrototypeFile[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const fullPath = join(dir, entry.name);
		if (entry.isDirectory()) return readPrototypeFiles(fullPath);
		if (!entry.isFile() || !entry.name.endsWith(".html")) return [];

		return [{ id: entry.name.replace(/\.html$/, ""), path: fullPath }];
	});
}

const geometryTargets: GeometryTarget[] = [
	{ file: "page-cross-market.html", selector: ".drivers-strip" },
	{ file: "page-regime-monitor.html", selector: ".heatgrid-legend" },
	{ file: "page-signals-inbox.html", selector: ".detail-panel" },
	{ file: "page-trading-overview.html", selector: "#default-view > .status-bar" },
	{ file: "page-backtest-list.html", selector: ".filter-count" },
	{ file: "page-experiment-list.html", selector: ".filter-count" },
];

describe("full prototype directory visual audit", () => {
	let browser: Browser;

	beforeAll(async () => {
		browser = await chromium.launch({ channel: "chromium" });
	}, auditTimeoutMs);

	afterAll(async () => {
		await browser.close();
	});

	it(
		"keeps every prototype page free of runtime errors, default horizontal scroll, and default visible overlays",
		async () => {
			const violations: string[] = [];

			for (const prototype of readPrototypeFiles()) {
				for (const viewport of viewports) {
					const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
					const consoleErrors: string[] = [];
					const pageErrors: string[] = [];

					page.on("console", (message) => {
						if (message.type() === "error") consoleErrors.push(message.text());
					});
					page.on("pageerror", (error) => pageErrors.push(error.message));

					await page.goto(pathToFileURL(prototype.path).href, {
						waitUntil: "load",
						timeout: navigationTimeoutMs,
					});
					await page.waitForTimeout(80);

					const audit = await page.evaluate(() => {
						const visible = (element: Element) => {
							const style = getComputedStyle(element);
							const rect = element.getBoundingClientRect();
							return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
						};

						return {
							hasHorizontalScroll:
								document.documentElement.scrollWidth > window.innerWidth + 2 ||
								document.body.scrollWidth > window.innerWidth + 2,
							defaultVisibleOverlays: Array.from(
								document.querySelectorAll("[role='dialog'], .overlay-backdrop, .overlay-surface"),
							).filter(visible).length,
						};
					});

					if (consoleErrors.length > 0) violations.push(`${prototype.id}:${viewport.name}:console:${consoleErrors[0]}`);
					if (pageErrors.length > 0) violations.push(`${prototype.id}:${viewport.name}:pageerror:${pageErrors[0]}`);
					if (audit.hasHorizontalScroll) violations.push(`${prototype.id}:${viewport.name}:horizontal-scroll`);
					if (audit.defaultVisibleOverlays > 0) violations.push(`${prototype.id}:${viewport.name}:default-visible-overlays:${audit.defaultVisibleOverlays}`);

					await page.close();
				}
			}

			expect(violations).toEqual([]);
		},
		auditTimeoutMs,
	);

	it(
		"keeps final-review risk selectors inside the viewport in compact and narrow layouts",
		async () => {
			const violations: string[] = [];

			for (const target of geometryTargets) {
				for (const viewport of viewports.filter((item) => item.name !== "standard")) {
					const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
					await page.goto(pathToFileURL(join(prototypesDir, target.file)).href, {
						waitUntil: "load",
						timeout: navigationTimeoutMs,
					});

					const geometry = await page.locator(target.selector).first().evaluate((element) => {
						const rect = element.getBoundingClientRect();
						return {
							left: rect.left,
							right: rect.right,
							width: rect.width,
							viewportWidth: window.innerWidth,
						};
					});
					const allowedRight = geometry.viewportWidth + (target.maxRightOverflowPx ?? 2);

					if (geometry.left < -2 || geometry.right > allowedRight) {
						violations.push(
							`${target.file}:${target.selector}:${viewport.name}:${Math.round(geometry.left)}..${Math.round(geometry.right)} of ${geometry.viewportWidth}`,
						);
					}

					await page.close();
				}
			}

			expect(violations).toEqual([]);
		},
		auditTimeoutMs,
	);
});
```

- [ ] **Step 2: Run the visual audit and verify it fails before all geometry fixes are complete**

Run:

```bash
bun run test:run scripts/prototype-full-directory-visual-audit.test.ts
```

Expected: FAIL until the active-route geometry fixes from Task 3 are complete; then PASS.

- [ ] **Step 3: Run the visual audit after Task 3 fixes**

Run:

```bash
bun run test:run scripts/prototype-full-directory-visual-audit.test.ts
```

Expected: PASS.

- [ ] **Step 4: Commit runtime audit**

```bash
git add scripts/prototype-full-directory-visual-audit.test.ts
git commit -m "test: add full prototype directory visual audit"
```

---

### Task 5: Final Full-Directory Verification and Review Record

**Files:**

- Create: `docs/reviews/2026-05-11-prototype-full-directory-excellent-results.md`
- Test: full command suite

- [ ] **Step 1: Run full-directory detector**

Run:

```bash
find prototype -type f -name '*.html' -print0 | xargs -0 npx impeccable --json --fast
```

Expected: exit 0 and output `[]`.

- [ ] **Step 2: Run targeted prototype tests**

Run:

```bash
bun run test:run scripts/prototype-design-consistency.test.ts scripts/prototype-full-directory-visual-audit.test.ts scripts/page-a-shares-prototype.test.ts scripts/prototype-expert-efficiency.test.ts scripts/prototype-interaction-ux-contract.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run active route visual gates**

Run:

```bash
bun run prototype:gates
```

Expected: 28/28 active route prototypes PASS, no blocking issues, no non-blocking issues.

- [ ] **Step 4: Run full project check**

Run:

```bash
bun run check
```

Expected: `biome check .` PASS, `tsc -b` PASS, and Vitest PASS.

- [ ] **Step 5: Create final review record**

Create `docs/reviews/2026-05-11-prototype-full-directory-excellent-results.md`:

````md
# Prototype Full Directory Excellent Results

> Date: 2026-05-11
> Scope: every HTML file under `prototype/`
> Target: Excellent, full-directory freeze quality

## Conclusion

The full prototype directory meets Excellent review quality. Active route prototypes, legacy non-active specimens, archive specimens, and the Graphite Studio token showcase are detector-clean, runtime-clean, and visually stable across the reviewed desktop viewports.

## Evidence

```bash
find prototype -type f -name '*.html' -print0 | xargs -0 npx impeccable --json --fast
```

Result: `[]`

```bash
bun run test:run scripts/prototype-design-consistency.test.ts scripts/prototype-full-directory-visual-audit.test.ts scripts/page-a-shares-prototype.test.ts scripts/prototype-expert-efficiency.test.ts scripts/prototype-interaction-ux-contract.test.ts
```

Result: PASS

```bash
bun run prototype:gates
```

Result: 28/28 active route prototypes PASS

```bash
bun run check
```

Result: PASS

## Fixed Issues

- Removed detector-triggering layout-property transitions from legacy Agent Console, archive AI Overview, archive AI Copilot, and token showcase.
- Replaced bounce-named AI thinking motion with restrained pulse motion.
- Replaced direct generic font sample override in token showcase with design-token font usage.
- Added spacing rhythm to token showcase demo rows so the page no longer reads as one-note 4px spacing.
- Fixed compact/narrow geometry risks in Cross-Market, Regime Monitor, Signals Inbox, Trading Overview, Backtest List, and Experiment List.
- Added explicit accessible names to icon-only overlay triggers in Cross-Market, A-Shares, Markets Intelligence, and Strategy Studio.

## React Implementation Notes

- Keep chart/map semantics as data adapter contracts rather than static labels.
- Preserve A-Shares red-up/green-down semantics with non-color signs and aria text.
- Preserve high-risk action confirmations as state-machine steps, not decorative modal copy.
- Preserve full-directory motion rules: transform, opacity, or grid-template-rows only.
````

- [ ] **Step 6: Commit final review record**

```bash
git add docs/reviews/2026-05-11-prototype-full-directory-excellent-results.md
git commit -m "docs: record full prototype directory excellent review"
```

---

## Self-Review

Spec coverage:

- Full-directory scope is covered by Task 1 and Task 4 through recursive HTML discovery under `prototype/`.
- Active route Excellent regressions are covered by Task 3 and `bun run prototype:gates`.
- Non-active and archive detector findings are covered by Task 2.
- Interaction and obvious bug checks are covered by Task 4: runtime errors, page errors, default horizontal scroll, default visible overlays, and known geometry selectors.
- Visual consistency is covered by detector, static CSS gates, and final review record.

Placeholder scan:

- The plan uses exact paths, commands, expected outcomes, and concrete code blocks.
- No undefined future work items remain.

Type and name consistency:

- New helper names are consistent: `readPrototypeHtmlFilesRecursive`, `readFullPrototypeCssSources`, and `readPrototypeFiles`.
- New test file path is consistently `scripts/prototype-full-directory-visual-audit.test.ts`.
- Geometry selectors match the reviewed source files.

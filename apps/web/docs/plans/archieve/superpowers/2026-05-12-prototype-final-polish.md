# Prototype Final Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `docs/designs/specs/prototypes` 的发布前 UX 风险收敛到可放行状态：消除首屏交互遮挡、底部/侧栏视窗遮挡、表格数值截断，并把 `page-a-shares` 热力图改成专业 A 股红涨绿跌语义。

**Architecture:** 先新增可重复运行的 Vitest + Playwright 回归合同，锁住遮挡、文本 fit、红绿热力图和 impeccable 绝对禁令；再按页面边界做小范围 CSS/HTML 修复。全局只改共享原型 CSS 和原型 HTML，不改 `src/styles/design-tokens/`，避免未批准的 Design Token 变更。

**Tech Stack:** Bun, Vitest, Playwright, static HTML/CSS prototypes, OKLCH CSS custom properties, existing impeccable detector.

---

## Scope Check

本计划覆盖同一个 release-polish 目标下的四类缺陷：自动化合同、交互遮挡、表格/状态栏 fit、A 股热力图。它们共享同一套原型目录和验证命令，适合放在一个计划中；执行时每个任务仍能独立提交和回滚。

## Current Evidence

- `bun run prototype:gates`: active route prototypes 全部通过，但该门禁没有覆盖所有交互目标被覆盖的问题。
- `bunx vitest run scripts/prototype-design-consistency.test.ts scripts/prototype-final-review-remediation.test.ts scripts/prototype-full-directory-visual-audit.test.ts --testTimeout=180000 --hookTimeout=180000`: 3 files, 116 tests passed。
- 自定义 Playwright 遮挡扫描发现：29 页 × 5 视窗，56 个记录存在交互遮挡，59 个记录存在文本溢出，3 个 fixed/sticky 越界，0 个全局横向溢出。
- `bunx impeccable --json --fast docs/designs/specs/prototypes`: `shared/fonts.css` 的 Inter 是 product UI 可接受误报；`shared/layout-components.css:2282` 的 `border-left: 4px solid var(--text-tertiary)` 是真实问题。
- `bun run check`: 150 files, 1803 tests passed。

## File Structure

- Create: `scripts/prototype-final-polish-contract.test.ts`
  - 静态合同：禁止 active prototype / shared prototype CSS 中出现有色粗侧边框；要求 `page-a-shares` 使用 OKLCH 红绿 stepped heatmap palette；要求 active root 不保留 superseded root specimen。
- Create: `scripts/prototype-viewport-obstruction-contract.test.ts`
  - Playwright 合同：在 gate viewports 检查可见交互目标没有被其他层覆盖；检查 fixed/sticky 交互目标不越出视窗；检查关键数据列文本不被压缩到不可读。
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css`
  - 替换 collapsible rail 的 border triangle；补强 table footer 和 numeric cell 的通用 fit 规则。
- Modify: `docs/designs/specs/prototypes/page-a-shares.html`
  - 改为 A 股红涨绿跌 stepped OKLCH palette；保留 `▲/▼`、正负号、阈值图例、aria label 的双维表达。
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html`
  - 重排 header 策略摘要、删除入口和 action toolbar，消除 `删除策略` 被 action 区覆盖。
- Modify: `docs/designs/specs/prototypes/page-agent-console-v2.html`
  - 让 top/bottom main 使用明确 grid row contract 和内部滚动，消除 findings / auto research / quality panels 垂直互压。
- Modify: `docs/designs/specs/prototypes/page-markets-screener.html`
  - 保证 detail rail 不覆盖 table action；让 footer 占据正常 flow；表格右侧 action 留出安全空间。
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html`
  - 底部 status bar 彻底进入文档流，main/detail scroll area 扣除 status bar 高度。
- Modify: `docs/designs/specs/prototypes/page-instrument-hub.html`
  - 右 rail section 使用内部滚动和底部安全距离，消除研究项被后续 summary 覆盖。
- Modify: `docs/designs/specs/prototypes/page-research.html`
  - 修正右 rail queue/run item 宽度和 z-index，避免 `查看回测详情` 被审批队列文本覆盖。
- Modify: `docs/designs/specs/prototypes/page-markets-intelligence.html`
  - state variant / stale action 不再与右 rail action 互压。
- Modify: `docs/designs/specs/prototypes/.edition-manifest.json`
  - 如归档 root superseded `page-agent-console.html`，同步 manifest 中 root specimen 的文件路径或状态说明。
- Move: `docs/designs/specs/prototypes/page-agent-console.html` → `docs/designs/specs/prototypes/archive/2026-05-12/page-agent-console.html`
  - 仅在 Task 9 执行；它是 superseded specimen，不应继续参与 root 目录发布面扫描。
- Modify: `docs/designs/specs/audits/2026-05-11-prototype-quality-recovery-results.md`
  - 追加本轮修复结果和验证证据。

## References

- Product/design context: `PRODUCT.md`, `DESIGN.md`
- Existing color decision: `docs/designs/decisions/2026-03-30-up-down-color-semantics.md`
- Current A-share domain tokens: `src/styles/design-tokens/tokens-domain.css`
- WCAG color rule: https://www.w3.org/WAI/WCAG22/Understanding/use-of-color
- WCAG target size overlap rule: https://www.w3.org/TR/WCAG22/#target-size-minimum
- A 股红涨绿跌 market convention reference: https://support.futunn.com/en/topic40/?lang=en-us

## Task 1: Add Static Final Polish Contract

**Files:**
- Create: `scripts/prototype-final-polish-contract.test.ts`
- Test: `scripts/prototype-final-polish-contract.test.ts`

- [ ] **Step 1: Write the failing static contract**

Create `scripts/prototype-final-polish-contract.test.ts` with this complete content:

```ts
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");

const activeSharedCssFiles = [
	"shared/layout-components.css",
	"shared/layout-shell.css",
	"shared/layout-state.css",
	"shared/prototype-interactions.css",
	"shared/prototype-toggles.css",
	"shared/theme-switcher.css",
] as const;

type StaticFinding = {
	file: string;
	line: number;
	snippet: string;
};

function readPrototypeFile(relativePath: string): string {
	return readFileSync(join(prototypesDir, relativePath), "utf8");
}

function lineNumberAt(source: string, index: number): number {
	return source.slice(0, index).split("\n").length;
}

function collectActiveRootHtmlFiles(): string[] {
	return readdirSync(prototypesDir)
		.filter((file) => file.startsWith("page-") && file.endsWith(".html"))
		.sort();
}

function collectColoredSideBorderFindings(relativePath: string): StaticFinding[] {
	const source = readPrototypeFile(relativePath);
	const findings: StaticFinding[] = [];
	const sideBorderPattern =
		/border-(left|right):\s*(?:[2-9]|\d{2,})px\s+solid\s+(?!transparent\b|currentColor\b)([^;]+)/g;

	for (const match of source.matchAll(sideBorderPattern)) {
		findings.push({
			file: relativePath,
			line: lineNumberAt(source, match.index ?? 0),
			snippet: match[0].trim(),
		});
	}

	return findings;
}

describe("prototype final polish static contract", () => {
	it("does not use thick colored side accent borders in active prototype CSS", () => {
		const scannedFiles = [
			...activeSharedCssFiles,
			...collectActiveRootHtmlFiles(),
		].filter((relativePath) => existsSync(join(prototypesDir, relativePath)));

		const findings = scannedFiles.flatMap(collectColoredSideBorderFindings);

		expect(findings).toEqual([]);
	});

	it("keeps superseded agent console out of the root prototype release surface", () => {
		const rootHtmlFiles = collectActiveRootHtmlFiles();

		expect(rootHtmlFiles).not.toContain("page-agent-console.html");
		expect(rootHtmlFiles).toContain("page-agent-console-v2.html");
	});

	it("uses explicit A-share red and green stepped heatmap colors instead of low-chroma graphite mixes", () => {
		const source = readPrototypeFile("page-a-shares.html");
		const requiredTokens = [
			"--map-market-up-1: oklch(0.305 0.062 22);",
			"--map-market-up-2: oklch(0.358 0.088 22);",
			"--map-market-up-3: oklch(0.414 0.116 22);",
			"--map-market-up-4: oklch(0.475 0.144 22);",
			"--map-market-down-1: oklch(0.300 0.050 155);",
			"--map-market-down-2: oklch(0.352 0.070 155);",
			"--map-market-down-3: oklch(0.406 0.092 155);",
			"--map-market-down-4: oklch(0.462 0.112 155);",
		];

		for (const token of requiredTokens) {
			expect(source).toContain(token);
		}

		expect(source).not.toMatch(/--map-market-(?:up|down)-[1-4]:\s*color-mix\(/);
		expect(source).toContain("A股：红涨绿跌");
		expect(source).toContain('data-direction="up"');
		expect(source).toContain('data-direction="down"');
		expect(source).toContain("▲");
		expect(source).toContain("▼");
	});
});
```

- [ ] **Step 2: Run the new static contract and confirm it fails for the current known issues**

Run:

```bash
bunx vitest run scripts/prototype-final-polish-contract.test.ts
```

Expected: FAIL with all three failures:

- `shared/layout-components.css` reports `border-left: 4px solid var(--text-tertiary)`.
- root prototype files still contain `page-agent-console.html`.
- `page-a-shares.html` still defines `--map-market-up-*` and `--map-market-down-*` via `color-mix(...)`.

- [ ] **Step 3: Commit the failing contract**

```bash
git add scripts/prototype-final-polish-contract.test.ts
git commit -m "test: add prototype final polish static contract"
```

## Task 2: Remove Thick Side-Border Accent From Shared Components

**Files:**
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css:2274-2288`
- Test: `scripts/prototype-final-polish-contract.test.ts`

- [ ] **Step 1: Replace the triangle side-border pseudo-element**

In `docs/designs/specs/prototypes/shared/layout-components.css`, replace the existing `.rail-section[data-collapsible-strip] .rail-section-header::after` block with this code:

```css
.rail-section[data-collapsible-strip] .rail-section-header::after {
  content: "›";
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%) rotate(0deg);
  width: 1rem;
  height: 1rem;
  display: grid;
  place-items: center;
  color: var(--text-tertiary);
  font-family: var(--font-family-ui);
  font-size: var(--font-size-12);
  line-height: 1;
  transition: transform 200ms var(--motion-easing-standard),
              opacity 150ms var(--motion-easing-standard),
              color 150ms var(--motion-easing-standard);
  opacity: 0.58;
}

.rail-section[data-collapsible-strip] .rail-section-header:hover::after {
  color: var(--text-secondary);
  opacity: 0.9;
}

.rail-section[data-collapsed-state="true"] .rail-section-header::after {
  transform: translateY(-50%) rotate(-90deg);
}
```

- [ ] **Step 2: Run the focused static test**

Run:

```bash
bunx vitest run scripts/prototype-final-polish-contract.test.ts -t "thick colored side accent"
```

Expected: PASS.

- [ ] **Step 3: Run the impeccable detector for the shared component file**

Run:

```bash
bunx impeccable --json --fast docs/designs/specs/prototypes/shared/layout-components.css
```

Expected: exit code 0 or no `side-tab` finding. If the command still exits with non-zero for a different active finding, capture the JSON output and inspect the reported file/line before changing code.

- [ ] **Step 4: Commit**

```bash
git add docs/designs/specs/prototypes/shared/layout-components.css
git commit -m "fix: remove prototype side accent border"
```

## Task 3: Convert A-Share Heatmap To Red/Green Stepped Palette

**Files:**
- Modify: `docs/designs/specs/prototypes/page-a-shares.html:386-470`
- Test: `scripts/prototype-final-polish-contract.test.ts`
- Test: `scripts/page-a-shares-prototype.test.ts`

- [ ] **Step 1: Replace the map color token block**

In `.map-container`, replace lines currently defining `--map-market-up-base`, `--map-market-down-base`, `--map-market-up-*`, `--map-market-down-*`, `--map-market-*-edge-*`, `--map-light-*`, and `--map-light-*-edge-*` with this block:

```css
      --map-market-up-1: oklch(0.305 0.062 22);
      --map-market-up-2: oklch(0.358 0.088 22);
      --map-market-up-3: oklch(0.414 0.116 22);
      --map-market-up-4: oklch(0.475 0.144 22);
      --map-market-down-1: oklch(0.300 0.050 155);
      --map-market-down-2: oklch(0.352 0.070 155);
      --map-market-down-3: oklch(0.406 0.092 155);
      --map-market-down-4: oklch(0.462 0.112 155);
      --map-market-up-edge-1: oklch(0.560 0.150 22 / 0.44);
      --map-market-up-edge-2: oklch(0.600 0.164 22 / 0.56);
      --map-market-up-edge-3: oklch(0.635 0.174 22 / 0.68);
      --map-market-up-edge-4: oklch(0.670 0.184 22 / 0.78);
      --map-market-down-edge-1: oklch(0.560 0.112 155 / 0.44);
      --map-market-down-edge-2: oklch(0.600 0.124 155 / 0.56);
      --map-market-down-edge-3: oklch(0.640 0.136 155 / 0.68);
      --map-market-down-edge-4: oklch(0.680 0.148 155 / 0.78);
      --map-light-up-1: oklch(0.925 0.024 22);
      --map-light-up-2: oklch(0.890 0.040 22);
      --map-light-up-3: oklch(0.850 0.058 22);
      --map-light-up-4: oklch(0.805 0.078 22);
      --map-light-down-1: oklch(0.920 0.022 155);
      --map-light-down-2: oklch(0.882 0.036 155);
      --map-light-down-3: oklch(0.840 0.052 155);
      --map-light-down-4: oklch(0.795 0.070 155);
      --map-light-up-edge-1: oklch(0.620 0.138 22 / 0.36);
      --map-light-up-edge-2: oklch(0.600 0.152 22 / 0.46);
      --map-light-up-edge-3: oklch(0.580 0.164 22 / 0.56);
      --map-light-up-edge-4: oklch(0.560 0.176 22 / 0.66);
      --map-light-down-edge-1: oklch(0.590 0.100 155 / 0.36);
      --map-light-down-edge-2: oklch(0.570 0.112 155 / 0.46);
      --map-light-down-edge-3: oklch(0.550 0.124 155 / 0.56);
      --map-light-down-edge-4: oklch(0.530 0.136 155 / 0.66);
```

Keep the existing `--heat-flat`, `--heat-up-*`, `--heat-down-*`, and `[data-theme="light"] .map-container` mappings. Do not change `src/styles/design-tokens/tokens-domain.css`.

- [ ] **Step 2: Run the static palette contract**

Run:

```bash
bunx vitest run scripts/prototype-final-polish-contract.test.ts -t "A-share red and green stepped"
```

Expected: PASS.

- [ ] **Step 3: Run the existing A-share page tests**

Run:

```bash
bunx vitest run scripts/page-a-shares-prototype.test.ts
```

Expected: PASS. This preserves current semantics: `A股：红涨绿跌`, explicit `data-direction`, accessible cells, label budgets, and no glossy glows.

- [ ] **Step 4: Capture a gate screenshot for visual review**

Run:

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-a-shares.html --viewport VP-COMPACT=1366x768 --out-dir test-results/ditto-design-cycle-gates/a-shares-red-green-check
```

Expected: PASS. Inspect `test-results/ditto-design-cycle-gates/a-shares-red-green-check/page-a-shares.html-VP-COMPACT.png`; the sector map should read as muted but unmistakable red/green, not purple/cyan.

- [ ] **Step 5: Commit**

```bash
git add docs/designs/specs/prototypes/page-a-shares.html
git commit -m "fix: calibrate a-share heatmap red green palette"
```

## Task 4: Add Viewport Obstruction Regression Contract

**Files:**
- Create: `scripts/prototype-viewport-obstruction-contract.test.ts`
- Test: `scripts/prototype-viewport-obstruction-contract.test.ts`

- [ ] **Step 1: Write the failing Playwright obstruction contract**

Create `scripts/prototype-viewport-obstruction-contract.test.ts` with this complete content:

```ts
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { chromium, type Browser } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../docs/designs/specs/prototypes");
const manifestPath = join(prototypesDir, ".edition-manifest.json");
const navigationTimeoutMs = 15_000;
const scanTimeoutMs = 180_000;

const gateViewports = [
	{ name: "1536x1080", width: 1536, height: 1080 },
	{ name: "1366x768", width: 1366, height: 768 },
	{ name: "1200x800", width: 1200, height: 800 },
] as const;

const stressViewports = [
	{ name: "1280x720", width: 1280, height: 720 },
	{ name: "1024x768", width: 1024, height: 768 },
] as const;

const criticalPageIds = new Set([
	"strategy-studio",
	"agent-console-v2",
	"markets-screener",
	"alpha-explorer",
	"instrument-hub",
	"markets-intelligence",
	"trading-overview",
	"research",
	"signals-inbox",
	"cross-market",
]);

const textFitPageIds = new Set([
	"markets-screener",
	"backtest-list",
	"strategy-list",
	"experiment-list",
	"factor-list",
	"portfolio",
	"watchlist",
	"strategies-detail",
	"platform",
	"regime-monitor",
	"markets-calendar",
]);

type ManifestPage = {
	id: string;
	file: string;
	status?: string;
};

type EditionManifest = {
	pages: ManifestPage[];
};

type Viewport = {
	name: string;
	width: number;
	height: number;
};

type ObstructionIssue = {
	pageId: string;
	file: string;
	viewport: string;
	targetPath: string;
	targetText: string;
	blockerPath: string;
	blockerText: string;
	rect: string;
};

type ClippedIssue = {
	pageId: string;
	file: string;
	viewport: string;
	targetPath: string;
	targetText: string;
	ancestorPath: string;
	rect: string;
};

type TextFitIssue = {
	pageId: string;
	file: string;
	viewport: string;
	targetPath: string;
	targetText: string;
	scrollWidth: number;
	clientWidth: number;
};

type BrowserScanResult = {
	obstructions: Array<Omit<ObstructionIssue, "pageId" | "file" | "viewport">>;
	clippedFixedTargets: Array<Omit<ClippedIssue, "pageId" | "file" | "viewport">>;
	textFitIssues: Array<Omit<TextFitIssue, "pageId" | "file" | "viewport">>;
	overflowX: number;
};

function readManifest(): EditionManifest {
	return JSON.parse(readFileSync(manifestPath, "utf8")) as EditionManifest;
}

function activePage(page: ManifestPage): boolean {
	return (
		page.file.startsWith("page-") &&
		page.file.endsWith(".html") &&
		page.status !== "archived-specimen"
	);
}

function auditedPages(): ManifestPage[] {
	return readManifest().pages.filter(activePage);
}

async function scanPage(browser: Browser, pageSpec: ManifestPage, viewport: Viewport): Promise<BrowserScanResult> {
	const browserPage = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
	try {
		await browserPage.goto(`file://${join(prototypesDir, pageSpec.file)}`, {
			waitUntil: "load",
			timeout: navigationTimeoutMs,
		});
		await browserPage.waitForTimeout(120);

		return await browserPage.evaluate((): BrowserScanResult => {
			const viewportWidth = window.innerWidth;
			const viewportHeight = window.innerHeight;
			const interactiveSelector = [
				"button",
				"a[href]",
				"input:not([type='hidden'])",
				"select",
				"textarea",
				"[role='button']",
				"[role='tab']",
				"[tabindex]:not([tabindex='-1'])",
				"summary",
				"label[for]",
				"[data-answer-action]",
				"[data-command-action]",
				"[data-overlay-trigger]",
			].join(",");
			const textFitSelector = [
				"button",
				"a[href]",
				"[role='button']",
				"[role='tab']",
				"th",
				"td",
				".metric-value",
				".metric-label",
				".header-metric",
				".calendar-reading-value",
				".regime-strip-metric",
			].join(",");

			function labelFor(element: Element): string {
				return (
					element.getAttribute("aria-label") ??
					element.getAttribute("title") ??
					element.textContent ??
					""
				)
					.replace(/\s+/g, " ")
					.trim()
					.slice(0, 96);
			}

			function pathFor(element: Element): string {
				const parts: string[] = [];
				let current: Element | null = element;
				while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 5) {
					let part = current.localName;
					if (current.id) {
						part += `#${current.id}`;
						parts.unshift(part);
						break;
					}
					const classes = [...current.classList].slice(0, 3);
					if (classes.length > 0) part += `.${classes.join(".")}`;
					const parent = current.parentElement;
					if (parent) {
						const sameTagSiblings = [...parent.children].filter(
							(child) => child.localName === current?.localName,
						);
						if (sameTagSiblings.length > 1) {
							part += `:nth-of-type(${sameTagSiblings.indexOf(current) + 1})`;
						}
					}
					parts.unshift(part);
					current = parent;
				}
				return parts.join(" > ");
			}

			function visible(element: Element): boolean {
				const style = getComputedStyle(element);
				const rect = element.getBoundingClientRect();
				return !(
					style.display === "none" ||
					style.visibility === "hidden" ||
					Number(style.opacity) <= 0.05 ||
					rect.width < 3 ||
					rect.height < 3 ||
					rect.bottom <= 0 ||
					rect.right <= 0 ||
					rect.top >= viewportHeight ||
					rect.left >= viewportWidth ||
					element.closest("[hidden], [aria-hidden='true']")
				);
			}

			function rectLabel(rect: DOMRect): string {
				return `${Math.round(rect.left)},${Math.round(rect.top)},${Math.round(rect.width)}x${Math.round(rect.height)}`;
			}

			const obstructions: BrowserScanResult["obstructions"] = [];
			for (const target of [...document.querySelectorAll(interactiveSelector)]) {
				if (!visible(target)) continue;
				const rect = target.getBoundingClientRect();
				const pointX = Math.min(Math.max(rect.left + rect.width / 2, 1), viewportWidth - 1);
				const pointY = Math.min(Math.max(rect.top + rect.height / 2, 1), viewportHeight - 1);
				const topElement = document.elementFromPoint(pointX, pointY);
				if (
					!topElement ||
					topElement === target ||
					target.contains(topElement) ||
					topElement.contains(target)
				) {
					continue;
				}

				const topStyle = getComputedStyle(topElement);
				const topRect = topElement.getBoundingClientRect();
				if (topStyle.pointerEvents === "none" || topRect.width <= 4 || topRect.height <= 4) continue;

				obstructions.push({
					targetPath: pathFor(target),
					targetText: labelFor(target),
					blockerPath: pathFor(topElement),
					blockerText: labelFor(topElement),
					rect: rectLabel(rect),
				});
			}

			const clippedFixedTargets: BrowserScanResult["clippedFixedTargets"] = [];
			for (const target of [...document.querySelectorAll(interactiveSelector)]) {
				if (!visible(target)) continue;
				const rect = target.getBoundingClientRect();
				let current: Element | null = target;
				let fixedAncestor: Element | null = null;
				while (current && current !== document.documentElement) {
					const position = getComputedStyle(current).position;
					if (position === "fixed" || position === "sticky") {
						fixedAncestor = current;
						break;
					}
					current = current.parentElement;
				}

				if (
					fixedAncestor &&
					(rect.left < -1 ||
						rect.top < -1 ||
						rect.right > viewportWidth + 1 ||
						rect.bottom > viewportHeight + 1)
				) {
					clippedFixedTargets.push({
						targetPath: pathFor(target),
						targetText: labelFor(target),
						ancestorPath: pathFor(fixedAncestor),
						rect: rectLabel(rect),
					});
				}
			}

			const textFitIssues: BrowserScanResult["textFitIssues"] = [];
			for (const target of [...document.querySelectorAll(textFitSelector)]) {
				if (!visible(target)) continue;
				const style = getComputedStyle(target);
				const isDataCell =
					target.matches("td, th") ||
					target.classList.contains("metric-value") ||
					target.classList.contains("header-metric") ||
					target.classList.contains("calendar-reading-value") ||
					target.classList.contains("regime-strip-metric");
				if (!isDataCell || style.whiteSpace === "normal") continue;
				if (target.scrollWidth > target.clientWidth + 2) {
					textFitIssues.push({
						targetPath: pathFor(target),
						targetText: labelFor(target),
						scrollWidth: target.scrollWidth,
						clientWidth: target.clientWidth,
					});
				}
			}

			const overflowX =
				Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) -
				document.documentElement.clientWidth;

			return {
				obstructions,
				clippedFixedTargets,
				textFitIssues,
				overflowX,
			};
		});
	} finally {
		await browserPage.close();
	}
}

function withPageContext<T extends object>(
	pageSpec: ManifestPage,
	viewport: Viewport,
	issues: T[],
): Array<T & { pageId: string; file: string; viewport: string }> {
	return issues.map((issue) => ({
		...issue,
		pageId: pageSpec.id,
		file: pageSpec.file,
		viewport: viewport.name,
	}));
}

describe("prototype viewport obstruction contract", () => {
	let browser: Browser;

	beforeAll(async () => {
		browser = await chromium.launch({ channel: "chromium", args: ["--disable-gpu"] });
	});

	afterAll(async () => {
		await browser.close();
	});

	it(
		"does not cover visible interactive targets at gate viewports",
		async () => {
			const issues: ObstructionIssue[] = [];
			const pages = auditedPages().filter((page) => criticalPageIds.has(page.id));

			for (const pageSpec of pages) {
				for (const viewport of gateViewports) {
					const result = await scanPage(browser, pageSpec, viewport);
					issues.push(...withPageContext(pageSpec, viewport, result.obstructions));
					expect(result.overflowX, `${pageSpec.id} ${viewport.name} horizontal overflow`).toBeLessThanOrEqual(2);
				}
			}

			expect(issues).toEqual([]);
		},
		scanTimeoutMs,
	);

	it(
		"does not clip fixed or sticky interactive targets at gate and stress viewports",
		async () => {
			const issues: ClippedIssue[] = [];
			const pages = auditedPages().filter((page) => criticalPageIds.has(page.id));

			for (const pageSpec of pages) {
				for (const viewport of [...gateViewports, ...stressViewports]) {
					const result = await scanPage(browser, pageSpec, viewport);
					issues.push(...withPageContext(pageSpec, viewport, result.clippedFixedTargets));
				}
			}

			expect(issues).toEqual([]);
		},
		scanTimeoutMs,
	);

	it(
		"keeps key dense data labels and numeric cells readable at release gate viewports",
		async () => {
			const issues: TextFitIssue[] = [];
			const pages = auditedPages().filter((page) => textFitPageIds.has(page.id));

			for (const pageSpec of pages) {
				for (const viewport of gateViewports) {
					const result = await scanPage(browser, pageSpec, viewport);
					issues.push(...withPageContext(pageSpec, viewport, result.textFitIssues));
				}
			}

			expect(issues).toEqual([]);
		},
		scanTimeoutMs,
	);
});
```

- [ ] **Step 2: Run the obstruction contract and confirm it fails on the known pages**

Run:

```bash
bunx vitest run scripts/prototype-viewport-obstruction-contract.test.ts --testTimeout=180000 --hookTimeout=180000
```

Expected: FAIL. The failure list should include at least:

- `strategy-studio` header `删除策略`
- `markets-screener` table compare actions
- `agent-console-v2` findings rows
- `instrument-hub` right rail research item
- `trading-overview` status-bar-covered controls
- dense table numeric/text fit issues on list pages

- [ ] **Step 3: Commit the failing obstruction contract**

```bash
git add scripts/prototype-viewport-obstruction-contract.test.ts
git commit -m "test: add prototype viewport obstruction contract"
```

## Task 5: Fix Strategy Studio Header Action Overlap

**Files:**
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html:252-364`
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html:1365-1381`
- Modify: `docs/designs/specs/prototypes/page-strategy-studio.html:2029-2076`
- Test: `scripts/prototype-viewport-obstruction-contract.test.ts`

- [ ] **Step 1: Update the header layout CSS**

Replace the `.studio-header`, `.strategy-name`, `.header-spacer`, `.studio-actions`, and `.studio-action` blocks with this code:

```css
    .studio-header {
      grid-area: header;
      background: var(--surface-frosted);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-subtle);
      display: grid;
      grid-template-columns: auto minmax(280px, 1fr) minmax(360px, auto);
      align-items: center;
      padding: 0 var(--space-16);
      gap: var(--space-12);
      z-index: 5;
      position: relative;
    }

    .strategy-name {
      font-size: var(--font-size-13);
      font-weight: var(--font-weight-medium);
      color: var(--text-primary);
      display: grid;
      grid-template-columns: auto minmax(120px, 1fr) auto auto;
      align-items: center;
      gap: var(--space-8);
      min-width: 0;
      overflow: hidden;
      white-space: nowrap;
    }

    .strategy-run-chip[data-answer-evidence] {
      max-width: 8.5rem;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .header-spacer { display: none; }

    .studio-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: var(--space-6);
      min-width: 0;
    }

    .studio-action {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: var(--space-4);
      min-width: 0;
      height: var(--density-action-height);
      padding: 0 var(--space-8);
      font-family: var(--font-family-ui);
      font-size: var(--font-size-12);
      font-weight: var(--font-weight-medium);
      color: var(--text-secondary);
      background: var(--surface-panel-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-4);
      cursor: pointer;
      transition: color var(--motion-duration-fast) var(--motion-easing-standard),
                  background var(--motion-duration-fast) var(--motion-easing-standard),
                  border-color var(--motion-duration-fast) var(--motion-easing-standard);
      white-space: nowrap;
    }

    @media (max-width: 1360px) {
      .studio-header {
        grid-template-columns: auto minmax(220px, 1fr) minmax(300px, auto);
        gap: var(--space-8);
      }

      .strategy-run-chip[data-answer-evidence],
      .strategy-run-chip--optional {
        display: none;
      }

      .studio-action {
        padding: 0 var(--space-6);
      }
    }
```

- [ ] **Step 2: Make the delete button a stable icon target inside the strategy summary**

Replace `.header-delete-btn` with:

```css
    .header-delete-btn {
      width: 28px;
      height: 28px;
      cursor: pointer;
      color: var(--text-tertiary);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid transparent;
      border-radius: var(--radius-4);
      flex: 0 0 28px;
      transition: color var(--motion-duration-fast) var(--motion-easing-standard),
                  background var(--motion-duration-fast) var(--motion-easing-standard),
                  border-color var(--motion-duration-fast) var(--motion-easing-standard);
    }

    .header-delete-btn:hover,
    .header-delete-btn:focus-visible {
      color: var(--risk-critical-fg);
      background: var(--risk-critical-bg);
      border-color: color-mix(in oklch, var(--risk-critical-fg) 28%, var(--border-subtle));
      outline: none;
    }
```

- [ ] **Step 3: Keep the HTML order unchanged and remove only the empty spacer**

Delete this line from the header markup:

```html
      <div class="header-spacer"></div>
```

Do not move `提交回测`; it remains the primary action inside `.studio-actions`.

- [ ] **Step 4: Run the focused obstruction contract**

Run:

```bash
bunx vitest run scripts/prototype-viewport-obstruction-contract.test.ts -t "visible interactive targets" --testTimeout=180000 --hookTimeout=180000
```

Expected: FAIL only for remaining pages; `strategy-studio` must not appear in the obstruction list.

- [ ] **Step 5: Commit**

```bash
git add docs/designs/specs/prototypes/page-strategy-studio.html
git commit -m "fix: stabilize strategy studio header actions"
```

## Task 6: Fix Agent Console V2 Vertical Panel Collisions

**Files:**
- Modify: `docs/designs/specs/prototypes/page-agent-console-v2.html:74-92`
- Modify: `docs/designs/specs/prototypes/page-agent-console-v2.html:522-596`
- Modify: `docs/designs/specs/prototypes/page-agent-console-v2.html:786-825`
- Test: `scripts/prototype-viewport-obstruction-contract.test.ts`

- [ ] **Step 1: Give the main panel explicit vertical track ownership**

Add this block after `.agent-shell`:

```css
    .main-panel {
      display: grid;
      grid-template-rows: minmax(220px, 0.95fr) minmax(220px, 1.05fr);
      min-width: 0;
      min-height: 0;
      overflow: hidden;
    }
```

- [ ] **Step 2: Make top and bottom sections self-contained**

Replace `.top-main` and `.bottom-main` with:

```css
    .top-main {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
      min-height: 0;
      overflow: hidden;
      border-bottom: 1px solid var(--border-subtle);
    }

    .bottom-main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      min-height: 0;
      overflow: hidden;
    }
```

- [ ] **Step 3: Convert fixed body heights to header-aware grid bodies**

Replace `.timeline, .findings, .autoresearch, .quality` and body rules with:

```css
    .timeline,
    .findings,
    .autoresearch,
    .quality {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      border-right: 1px solid var(--border-subtle);
    }

    .timeline-body,
    .findings-body,
    .dashboard-body {
      min-height: 0;
      height: auto;
      padding: var(--space-12);
      overflow-y: auto;
      overscroll-behavior: contain;
    }
```

- [ ] **Step 4: Replace the compact media override**

Inside the existing `@media (max-width: 1280px)` block, replace the `.main-panel`, `.top-main`, `.bottom-main`, `.timeline`, `.findings`, `.timeline-body`, and `.findings-body` overrides with:

```css
      .main-panel {
        grid-template-rows: none;
        overflow-y: auto;
        overscroll-behavior: contain;
      }

      .top-main,
      .bottom-main {
        grid-template-columns: minmax(0, 1fr);
        grid-auto-rows: minmax(180px, auto);
      }

      .timeline,
      .findings,
      .autoresearch,
      .quality {
        min-height: 180px;
        border-right: 0;
        border-bottom: 1px solid var(--border-subtle);
      }

      .timeline-body,
      .findings-body,
      .dashboard-body {
        height: auto;
        min-height: 0;
      }
```

- [ ] **Step 5: Run the focused obstruction contract**

Run:

```bash
bunx vitest run scripts/prototype-viewport-obstruction-contract.test.ts -t "visible interactive targets" --testTimeout=180000 --hookTimeout=180000
```

Expected: FAIL only for remaining pages; `agent-console-v2` must not appear in the obstruction list.

- [ ] **Step 6: Commit**

```bash
git add docs/designs/specs/prototypes/page-agent-console-v2.html
git commit -m "fix: contain agent console panel scrolling"
```

## Task 7: Fix Markets Screener Detail Rail And Table Action Overlap

**Files:**
- Modify: `docs/designs/specs/prototypes/page-markets-screener.html:105-130`
- Modify: `docs/designs/specs/prototypes/page-markets-screener.html:1878-1882`
- Modify: `docs/designs/specs/prototypes/page-markets-screener.html:2585-2588`
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css:1647-1684`
- Test: `scripts/prototype-viewport-obstruction-contract.test.ts`

- [ ] **Step 1: Give the catalog table a right-side safety gutter**

In `page-markets-screener.html`, replace `.catalog-table-inner .table-container` with:

```css
    .catalog-table-inner .table-container {
      flex: 1 1 auto;
      min-height: 0;
      overflow: auto;
      background: var(--surface-app);
      padding-right: var(--space-8);
      scrollbar-gutter: stable both-edges;
    }
```

- [ ] **Step 2: Prevent the detail rail from painting over table actions**

Add this block near the `.shell-catalog.catalog-shell` rules:

```css
    .shell-catalog.catalog-shell {
      --prototype-detail-width: clamp(280px, 24vw, 340px);
    }

    #main-content {
      min-width: 0;
      overflow: hidden;
    }

    #catalog-detail-panel {
      min-width: 0;
      overflow: hidden auto;
      contain: layout paint;
    }
```

- [ ] **Step 3: Make the shared table footer non-overlaying and compact**

In `shared/layout-components.css`, replace `.table-footer`, `.table-footer-info`, `.table-footer-actions`, and `.pagination-btn` with:

```css
.table-footer {
  grid-area: footer;
  flex: 0 0 auto;
  min-height: var(--density-strip-height);
  background: var(--surface-strip);
  border-top: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  padding: var(--space-4) var(--density-gutter);
  font-size: var(--font-size-12);
  color: var(--text-tertiary);
  position: relative;
  z-index: 1;
}

.table-footer-info {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.table-footer-actions {
  display: flex;
  align-items: center;
  gap: var(--space-6);
  flex: 0 0 auto;
}

.pagination-btn {
  font-family: var(--font-family-ui);
  font-size: var(--font-size-12);
  min-width: 24px;
  min-height: 24px;
  padding: var(--space-2) var(--space-6);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-4);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: border-color var(--motion-duration-fast) var(--motion-easing-standard),
              background var(--motion-duration-fast) var(--motion-easing-standard),
              color var(--motion-duration-fast) var(--motion-easing-standard),
              box-shadow var(--motion-duration-fast) var(--motion-easing-standard),
              opacity var(--motion-duration-fast) var(--motion-easing-standard);
}
```

- [ ] **Step 4: Run the focused obstruction and table fit tests**

Run:

```bash
bunx vitest run scripts/prototype-viewport-obstruction-contract.test.ts -t "visible interactive targets|key dense data" --testTimeout=180000 --hookTimeout=180000
```

Expected: FAIL only for remaining pages; `markets-screener` must not report table action obstruction. It may still report text fit until Task 10.

- [ ] **Step 5: Commit**

```bash
git add docs/designs/specs/prototypes/page-markets-screener.html docs/designs/specs/prototypes/shared/layout-components.css
git commit -m "fix: contain screener detail rail and footer"
```

## Task 8: Normalize Bottom Status Bar Safe Areas

**Files:**
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html:1035-1058`
- Modify: `docs/designs/specs/prototypes/page-trading-overview.html:1838-1850`
- Modify: `docs/designs/specs/prototypes/page-instrument-hub.html:602-871`
- Modify: `docs/designs/specs/prototypes/page-research.html`
- Modify: `docs/designs/specs/prototypes/page-markets-intelligence.html`
- Test: `scripts/prototype-viewport-obstruction-contract.test.ts`

- [ ] **Step 1: Make `trading-overview` status bar relative from the primary definition**

In `page-trading-overview.html`, replace the first `.status-bar` definition with:

```css
    .status-bar {
      position: relative;
      bottom: auto;
      left: auto;
      right: auto;
      display: flex;
      align-items: center;
      flex: 0 0 var(--status-bar-height);
      height: var(--status-bar-height);
      min-height: var(--status-bar-height);
      padding: 0 var(--space-8);
      background: var(--surface-app);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      border-top: 1px solid var(--border-subtle);
      font-family: var(--font-family-numeric);
      font-size: var(--font-size-10);
      color: var(--text-tertiary);
      letter-spacing: 0.02em;
      user-select: none;
      z-index: 1;
    }
```

Keep the later `#default-view > .status-bar` block, but simplify it to:

```css
    #default-view > .status-bar {
      flex: 0 0 var(--status-bar-height) !important;
      height: var(--status-bar-height) !important;
      width: auto !important;
    }
```

- [ ] **Step 2: Add a reusable right-rail safe scroll pattern to `instrument-hub`**

In `page-instrument-hub.html`, replace `.hub-sidebar` and `.context-body` with:

```css
    .hub-sidebar {
      grid-area: sidebar;
      min-width: 0;
      min-height: 0;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding-bottom: calc(var(--status-bar-height) + var(--space-12));
    }

    .context-body {
      min-height: 0;
      overflow: hidden;
    }

    .context-section[data-background-evidence] .context-body {
      max-height: 12rem;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding-right: var(--space-4);
    }
```

- [ ] **Step 3: Apply the same safe-scroll contract to research and markets intelligence right rails**

In `page-research.html`, add this block near existing `.context-section` / right rail rules:

```css
    .context-rail,
    .right-rail {
      min-height: 0;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding-bottom: calc(var(--status-bar-height) + var(--space-12));
    }

    .context-section-body {
      min-height: 0;
      overflow: hidden;
    }

    .context-section[data-background-evidence] .context-section-body {
      max-height: 12rem;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding-right: var(--space-4);
    }
```

In `page-markets-intelligence.html`, add this block near `.intel-right-rail` rules:

```css
    .intel-right-rail {
      min-height: 0;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding-bottom: calc(var(--status-bar-height) + var(--space-12));
      contain: layout paint;
    }

    .intel-right-rail .rail-section-body {
      min-height: 0;
      overflow: hidden;
    }

    .intel-right-rail .rail-section[data-background-evidence] .rail-section-body {
      max-height: 12rem;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding-right: var(--space-4);
    }
```

- [ ] **Step 4: Run the obstruction contract**

Run:

```bash
bunx vitest run scripts/prototype-viewport-obstruction-contract.test.ts -t "visible interactive targets|fixed or sticky" --testTimeout=180000 --hookTimeout=180000
```

Expected: `trading-overview`, `instrument-hub`, `research`, `markets-intelligence`, and `cross-market` no longer appear in obstruction or clipped-fixed issue lists.

- [ ] **Step 5: Commit**

```bash
git add docs/designs/specs/prototypes/page-trading-overview.html docs/designs/specs/prototypes/page-instrument-hub.html docs/designs/specs/prototypes/page-research.html docs/designs/specs/prototypes/page-markets-intelligence.html
git commit -m "fix: add prototype status and rail safe areas"
```

## Task 9: Archive Superseded Agent Console Root Specimen

**Files:**
- Move: `docs/designs/specs/prototypes/page-agent-console.html` → `docs/designs/specs/prototypes/archive/2026-05-12/page-agent-console.html`
- Modify: `docs/designs/specs/prototypes/.edition-manifest.json`
- Test: `scripts/prototype-final-polish-contract.test.ts`

- [ ] **Step 1: Move the superseded file**

Run:

```bash
mkdir -p docs/designs/specs/prototypes/archive/2026-05-12
git mv docs/designs/specs/prototypes/page-agent-console.html docs/designs/specs/prototypes/archive/2026-05-12/page-agent-console.html
```

Expected: `git status --short` shows one rename.

- [ ] **Step 2: Update the manifest entry**

In `docs/designs/specs/prototypes/.edition-manifest.json`, change the `agent-console` entry to:

```json
{
  "id": "agent-console",
  "file": "archive/2026-05-12/page-agent-console.html",
  "status": "archived-specimen",
  "score": 9.2,
  "styleAnchor": "platform",
  "rounds": 1,
  "roundsV2": 1,
  "roundsV3": 1,
  "roundsV5": 1,
  "inlineStyles": {
    "before": 123,
    "after": 0
  },
  "jsModules": {
    "ticker": 6,
    "reveal": 10,
    "glow": 2,
    "donut": 4,
    "tabs": 1,
    "total": 23
  },
  "createdAt": "2026-04-01",
  "stateCoverage": {
    "tabs": 4,
    "overlays": 4,
    "stateVariants": 6,
    "coveragePercent": 100
  },
  "blueprintId": 15,
  "shellFamily": "studio",
  "landing": {
    "reactRouteStatus": "superseded",
    "featureModule": "src/features/platform",
    "contractStatus": "superseded",
    "overlayStatus": "archived",
    "visualAuditStatus": "superseded"
  },
  "archiveNote": "2026-05-12: physically archived from root because page-agent-console-v2.html is the canonical /platform/agents prototype."
}
```

- [ ] **Step 3: Run the static root-surface test**

Run:

```bash
bunx vitest run scripts/prototype-final-polish-contract.test.ts -t "superseded agent console"
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/designs/specs/prototypes/.edition-manifest.json docs/designs/specs/prototypes/archive/2026-05-12/page-agent-console.html
git commit -m "chore: archive superseded agent console prototype"
```

## Task 10: Fix Dense Table Numeric And Label Fit

**Files:**
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css:1460-1491`
- Modify: `docs/designs/specs/prototypes/page-backtest-list.html`
- Modify: `docs/designs/specs/prototypes/page-strategy-list.html`
- Modify: `docs/designs/specs/prototypes/page-experiment-list.html`
- Modify: `docs/designs/specs/prototypes/page-factor-list.html`
- Modify: `docs/designs/specs/prototypes/page-portfolio.html`
- Modify: `docs/designs/specs/prototypes/page-watchlist.html`
- Modify: `docs/designs/specs/prototypes/page-strategies-detail.html`
- Modify: `docs/designs/specs/prototypes/page-platform.html`
- Modify: `docs/designs/specs/prototypes/page-regime-monitor.html`
- Modify: `docs/designs/specs/prototypes/page-markets-calendar.html`
- Test: `scripts/prototype-viewport-obstruction-contract.test.ts`

- [ ] **Step 1: Add shared numeric fit utilities**

In `shared/layout-components.css`, replace `.data-table td.numeric` and `.data-table .numeric` with:

```css
.data-table td.numeric,
.data-table .numeric {
  font-family: var(--font-family-numeric);
  font-size: var(--font-size-12);
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
  min-width: max-content;
}

.data-table td.code-cell,
.data-table td.cell-ticker,
.data-table td.cell-volume,
.data-table td.cell-change-up,
.data-table td.cell-change-down,
.data-table td.cell-change-flat {
  white-space: nowrap;
  min-width: max-content;
}

.data-table td.name-cell,
.data-table td.cell-name,
.data-table td.cell-note {
  min-width: 7rem;
}

.table-container,
.sd-overflow-auto,
.catalog-table-inner .table-container {
  overflow-x: auto;
  scrollbar-gutter: stable both-edges;
}
```

- [ ] **Step 2: Add page-level column minima for list pages**

For each listed file, add a compact column rule inside the existing `<style>` block. Use only the rule that matches the page:

`docs/designs/specs/prototypes/page-backtest-list.html`

```css
    .data-table th:nth-child(2),
    .data-table td:nth-child(2) { min-width: 9rem; }
    .data-table th:nth-child(6),
    .data-table td:nth-child(6) { min-width: 5.5rem; }
```

`docs/designs/specs/prototypes/page-strategy-list.html`

```css
    .data-table th:nth-child(2),
    .data-table td:nth-child(2) { min-width: 9rem; }
    .data-table th:nth-child(6),
    .data-table td:nth-child(6) { min-width: 5.5rem; }
```

`docs/designs/specs/prototypes/page-experiment-list.html`

```css
    .data-table th:nth-child(6),
    .data-table td:nth-child(6) { min-width: 5.25rem; }
```

`docs/designs/specs/prototypes/page-factor-list.html`

```css
    .data-table th:nth-child(3),
    .data-table td:nth-child(3),
    .data-table th:nth-child(5),
    .data-table td:nth-child(5) { min-width: 5.25rem; }
```

`docs/designs/specs/prototypes/page-portfolio.html`

```css
    .data-table th:nth-child(1),
    .data-table td:nth-child(1) { min-width: 5.75rem; }
    .data-table th:nth-child(2),
    .data-table td:nth-child(2) { min-width: 5.75rem; }
    .data-table th:nth-child(8),
    .data-table td:nth-child(8),
    .data-table th:nth-child(9),
    .data-table td:nth-child(9),
    .data-table th:nth-child(11),
    .data-table td:nth-child(11) { min-width: 6.5rem; }
```

`docs/designs/specs/prototypes/page-watchlist.html`

```css
    .data-table th:nth-child(4),
    .data-table td:nth-child(4),
    .data-table th:nth-child(5),
    .data-table td:nth-child(5) { min-width: 5.75rem; }
    .data-table th:nth-child(8),
    .data-table td:nth-child(8) { min-width: 6.5rem; }
```

`docs/designs/specs/prototypes/page-strategies-detail.html`

```css
    .data-table th:nth-child(2),
    .data-table td:nth-child(2) { min-width: 9rem; }
```

`docs/designs/specs/prototypes/page-platform.html`

```css
    .data-table th:nth-child(1),
    .data-table td:nth-child(1) { min-width: 7rem; }
    .data-table th:nth-child(4),
    .data-table td:nth-child(4) { min-width: 4rem; }
```

`docs/designs/specs/prototypes/page-regime-monitor.html`

```css
    .regime-strip-metric {
      min-width: 9.25rem;
      white-space: nowrap;
    }
```

`docs/designs/specs/prototypes/page-markets-calendar.html`

```css
    .calendar-reading-value {
      min-width: 8.5rem;
      white-space: nowrap;
    }
```

- [ ] **Step 3: Run the dense data fit test**

Run:

```bash
bunx vitest run scripts/prototype-viewport-obstruction-contract.test.ts -t "key dense data" --testTimeout=180000 --hookTimeout=180000
```

Expected: PASS.

- [ ] **Step 4: Run representative visual gates**

Run:

```bash
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-portfolio.html --viewport VP-COMPACT=1366x768 --out-dir test-results/ditto-design-cycle-gates/portfolio-fit-check
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-factor-list.html --viewport VP-NARROW=1200x800 --out-dir test-results/ditto-design-cycle-gates/factor-list-fit-check
bun run prototype:gates -- --prototype docs/designs/specs/prototypes/page-watchlist.html --viewport VP-NARROW=1200x800 --out-dir test-results/ditto-design-cycle-gates/watchlist-fit-check
```

Expected: all PASS. Inspect screenshots for horizontal table scroll inside the table region, not page-level horizontal overflow.

- [ ] **Step 5: Commit**

```bash
git add docs/designs/specs/prototypes/shared/layout-components.css docs/designs/specs/prototypes/page-backtest-list.html docs/designs/specs/prototypes/page-strategy-list.html docs/designs/specs/prototypes/page-experiment-list.html docs/designs/specs/prototypes/page-factor-list.html docs/designs/specs/prototypes/page-portfolio.html docs/designs/specs/prototypes/page-watchlist.html docs/designs/specs/prototypes/page-strategies-detail.html docs/designs/specs/prototypes/page-platform.html docs/designs/specs/prototypes/page-regime-monitor.html docs/designs/specs/prototypes/page-markets-calendar.html
git commit -m "fix: preserve dense prototype table readability"
```

## Task 11: Full Verification And Audit Record

**Files:**
- Modify: `docs/designs/specs/audits/2026-05-11-prototype-quality-recovery-results.md`
- Test: full prototype and project checks

- [ ] **Step 1: Run all final polish contracts**

Run:

```bash
bunx vitest run scripts/prototype-final-polish-contract.test.ts scripts/prototype-viewport-obstruction-contract.test.ts --testTimeout=180000 --hookTimeout=180000
```

Expected: PASS.

- [ ] **Step 2: Run existing prototype quality tests**

Run:

```bash
bunx vitest run scripts/prototype-design-consistency.test.ts scripts/prototype-final-review-remediation.test.ts scripts/prototype-full-directory-visual-audit.test.ts scripts/page-a-shares-prototype.test.ts --testTimeout=180000 --hookTimeout=180000
```

Expected: PASS.

- [ ] **Step 3: Run prototype gates for all active route prototypes**

Run:

```bash
bun run prototype:gates
```

Expected: PASS for every active route prototype.

- [ ] **Step 4: Run impeccable detector**

Run:

```bash
bunx impeccable --json --fast docs/designs/specs/prototypes
```

Expected: no `side-tab`, `gradient-text`, or active route layout findings. `overused-font` for `shared/fonts.css` is acceptable in this product UI because `DESIGN.md` explicitly defines Inter / Geist / JetBrains Mono as the typography system.

- [ ] **Step 5: Run full project check**

Run:

```bash
bun run check
```

Expected: biome, TypeScript, and Vitest all pass.

- [ ] **Step 6: Append audit evidence**

Append this section to `docs/designs/specs/audits/2026-05-11-prototype-quality-recovery-results.md`:

```md
## 2026-05-12 Final Polish Verification

Scope:

- Viewport obstruction contract added for gate viewports: 1536x1080, 1366x768, 1200x800.
- Superseded root agent console specimen archived.
- A-share market structure map recalibrated to explicit red-up / green-down stepped OKLCH palette.
- Dense table numeric and label fit rules added for release gate viewports.

Verification:

- `bunx vitest run scripts/prototype-final-polish-contract.test.ts scripts/prototype-viewport-obstruction-contract.test.ts --testTimeout=180000 --hookTimeout=180000`: PASS.
- `bunx vitest run scripts/prototype-design-consistency.test.ts scripts/prototype-final-review-remediation.test.ts scripts/prototype-full-directory-visual-audit.test.ts scripts/page-a-shares-prototype.test.ts --testTimeout=180000 --hookTimeout=180000`: PASS.
- `bun run prototype:gates`: PASS for every active route prototype.
- `bunx impeccable --json --fast docs/designs/specs/prototypes`: no active blocking design anti-patterns; product typography detector warning for Inter accepted by `DESIGN.md`.
- `bun run check`: PASS.

Release UX delta:

- P0 interactive obstruction: resolved for audited gate viewports.
- P1 bottom/status rail obstruction: resolved for audited gate viewports.
- P1 A-share heatmap red/green semantics: resolved while preserving non-color-only signs, labels, thresholds, and aria labels.
- P1 dense numeric fit: resolved by table-local horizontal overflow and column minima.
```

- [ ] **Step 7: Commit**

```bash
git add docs/designs/specs/audits/2026-05-11-prototype-quality-recovery-results.md scripts/prototype-final-polish-contract.test.ts scripts/prototype-viewport-obstruction-contract.test.ts
git commit -m "docs: record prototype final polish verification"
```

## Self-Review

- Spec coverage: 遮挡、交互遮挡、组件一致性、布局一致性、配色一致性、间距/字体一致性、`page-a-shares` 红绿热力图均有任务和验证命令覆盖。
- 占位表达扫描：计划没有使用禁用占位表达；每个代码步骤给出实际代码或明确替换块。
- Type consistency: 新测试只使用 `ManifestPage`, `EditionManifest`, `Viewport`, `ObstructionIssue`, `ClippedIssue`, `TextFitIssue`, `BrowserScanResult`；后续步骤引用的测试名和文件路径与定义一致。

## Execution Order

1. Task 1 → Task 2 → Task 3: 先锁静态规范，再修 side border 和 A 股热力图。
2. Task 4 → Task 5 → Task 8: 先锁遮挡合同，再修最严重交互遮挡页面。
3. Task 9: 把 superseded specimen 移出 root，降低发布面噪声。
4. Task 10: 收敛表格和数值 fit。
5. Task 11: 全量验证，记录审计结果。

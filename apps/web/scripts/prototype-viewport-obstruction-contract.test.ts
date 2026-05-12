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

type OverflowIssue = {
	pageId: string;
	file: string;
	viewport: string;
	overflowX: number;
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
		page.status !== "archived-specimen" &&
		page.status !== "removed-specimen"
	);
}

function auditedPages(): ManifestPage[] {
	return readManifest().pages.filter(activePage);
}

function pagesForContract(pageIds: Set<string>, label: string): ManifestPage[] {
	const activePages = auditedPages();
	const activePageById = new Map(activePages.map((page) => [page.id, page]));
	const missingPageIds = [...pageIds].filter((pageId) => !activePageById.has(pageId)).sort();

	expect(missingPageIds, `${label} missing active prototype ids`).toEqual([]);

	return [...pageIds]
		.map((pageId) => activePageById.get(pageId))
		.filter((page): page is ManifestPage => page !== undefined);
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
					style.pointerEvents === "none" ||
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

			function intersectionWithViewport(rect: DOMRect): DOMRect | null {
				const left = Math.max(rect.left, 0);
				const top = Math.max(rect.top, 0);
				const right = Math.min(rect.right, viewportWidth);
				const bottom = Math.min(rect.bottom, viewportHeight);
				const width = right - left;
				const height = bottom - top;

				if (width < 4 || height < 4 || width * height < 24) return null;

				return new DOMRect(left, top, width, height);
			}

			function samplePointsFor(rect: DOMRect): Array<{ x: number; y: number }> {
				const insetX = Math.min(Math.max(rect.width * 0.2, 2), 10);
				const insetY = Math.min(Math.max(rect.height * 0.2, 2), 10);
				const left = rect.left + insetX;
				const right = rect.right - insetX;
				const top = rect.top + insetY;
				const bottom = rect.bottom - insetY;
				const centerX = rect.left + rect.width / 2;
				const centerY = rect.top + rect.height / 2;

				return [
					{ x: centerX, y: centerY },
					{ x: left, y: top },
					{ x: right, y: top },
					{ x: left, y: bottom },
					{ x: right, y: bottom },
				].filter((point) => point.x >= 0 && point.x <= viewportWidth && point.y >= 0 && point.y <= viewportHeight);
			}

			function blockingElementAt(target: Element, point: { x: number; y: number }): Element | null {
				const topElement = document.elementFromPoint(point.x, point.y);
				if (
					!topElement ||
					topElement === target ||
					target.contains(topElement) ||
					topElement.contains(target)
				) {
					return null;
				}

				const topStyle = getComputedStyle(topElement);
				const topRect = topElement.getBoundingClientRect();
				if (
					topStyle.pointerEvents === "none" ||
					topStyle.display === "none" ||
					topStyle.visibility === "hidden" ||
					Number(topStyle.opacity) <= 0.05 ||
					topRect.width <= 4 ||
					topRect.height <= 4
				) {
					return null;
				}

				return topElement;
			}

			function rectLabel(rect: DOMRect): string {
				return `${Math.round(rect.left)},${Math.round(rect.top)},${Math.round(rect.width)}x${Math.round(rect.height)}`;
			}

			const obstructions: BrowserScanResult["obstructions"] = [];
			for (const target of [...document.querySelectorAll(interactiveSelector)]) {
				if (!visible(target)) continue;
				const rect = target.getBoundingClientRect();
				const intersection = intersectionWithViewport(rect);
				if (!intersection) continue;

				const topElement = samplePointsFor(intersection)
					.map((point) => blockingElementAt(target, point))
					.find((element): element is Element => element !== null);
				if (!topElement) continue;

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
					target.classList.contains("metric-label") ||
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

function summarizeIssues<TIssue extends { pageId: string; file: string; viewport: string }>(
	issues: TIssue[],
	formatIssue: (issue: TIssue) => string,
): string[] {
	const groups = new Map<string, TIssue[]>();
	for (const issue of issues) {
		const key = `${issue.pageId} ${issue.viewport}`;
		groups.set(key, [...(groups.get(key) ?? []), issue]);
	}

	return [...groups.entries()]
		.sort(([left], [right]) => left.localeCompare(right))
		.map(([key, groupedIssues]) => {
			const file = groupedIssues[0]?.file ?? "unknown";
			const samples = groupedIssues.slice(0, 3).map(formatIssue).join(" | ");
			const remaining = groupedIssues.length > 3 ? ` (+${groupedIssues.length - 3} more)` : "";
			return `${key} ${file}: ${groupedIssues.length} issue(s)${remaining}; ${samples}`;
		});
}

function summarizeObstructions(issues: ObstructionIssue[]): string[] {
	return summarizeIssues(
		issues,
		(issue) =>
			`target="${issue.targetText}" path="${issue.targetPath}" blockedBy="${issue.blockerText}" blockerPath="${issue.blockerPath}" rect=${issue.rect}`,
	);
}

function summarizeClippedTargets(issues: ClippedIssue[]): string[] {
	return summarizeIssues(
		issues,
		(issue) =>
			`target="${issue.targetText}" path="${issue.targetPath}" fixedOrStickyAncestor="${issue.ancestorPath}" rect=${issue.rect}`,
	);
}

function summarizeTextFitIssues(issues: TextFitIssue[]): string[] {
	return summarizeIssues(
		issues,
		(issue) =>
			`target="${issue.targetText}" path="${issue.targetPath}" scrollWidth=${issue.scrollWidth} clientWidth=${issue.clientWidth}`,
	);
}

function summarizeOverflowIssues(issues: OverflowIssue[]): string[] {
	return summarizeIssues(issues, (issue) => `overflowX=${issue.overflowX}`);
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
			const overflowIssues: OverflowIssue[] = [];
			const pages = pagesForContract(criticalPageIds, "critical viewport obstruction contract");

			for (const pageSpec of pages) {
				for (const viewport of gateViewports) {
					const result = await scanPage(browser, pageSpec, viewport);
					issues.push(...withPageContext(pageSpec, viewport, result.obstructions));
					if (result.overflowX > 2) {
						overflowIssues.push({
							pageId: pageSpec.id,
							file: pageSpec.file,
							viewport: viewport.name,
							overflowX: result.overflowX,
						});
					}
				}
			}

			expect(summarizeOverflowIssues(overflowIssues), "horizontal overflow").toEqual([]);
			expect(summarizeObstructions(issues), "interactive target obstructions").toEqual([]);
		},
		scanTimeoutMs,
	);

	it(
		"does not clip fixed or sticky interactive targets at gate and stress viewports",
		async () => {
			const issues: ClippedIssue[] = [];
			const pages = pagesForContract(criticalPageIds, "critical fixed/sticky clipping contract");

			for (const pageSpec of pages) {
				for (const viewport of [...gateViewports, ...stressViewports]) {
					const result = await scanPage(browser, pageSpec, viewport);
					issues.push(...withPageContext(pageSpec, viewport, result.clippedFixedTargets));
				}
			}

			expect(summarizeClippedTargets(issues)).toEqual([]);
		},
		scanTimeoutMs,
	);

	it(
		"keeps key dense data labels and numeric cells readable at release gate viewports",
		async () => {
			const issues: TextFitIssue[] = [];
			const pages = pagesForContract(textFitPageIds, "dense text fit contract");

			for (const pageSpec of pages) {
				for (const viewport of gateViewports) {
					const result = await scanPage(browser, pageSpec, viewport);
					issues.push(...withPageContext(pageSpec, viewport, result.textFitIssues));
				}
			}

			expect(summarizeTextFitIssues(issues)).toEqual([]);
		},
		scanTimeoutMs,
	);
});

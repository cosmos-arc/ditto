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

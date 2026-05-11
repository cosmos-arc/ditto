import { readdirSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { chromium, type Browser } from "playwright";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");
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
					await page.emulateMedia({ reducedMotion: "reduce" });
					await page.goto(pathToFileURL(join(prototypesDir, target.file)).href, {
						waitUntil: "load",
						timeout: navigationTimeoutMs,
					});
					await page.waitForTimeout(250);

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

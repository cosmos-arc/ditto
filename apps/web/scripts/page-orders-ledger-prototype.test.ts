import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium, type Browser, type Page } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-orders-ledger.html",
);
const navigationTimeoutMs = 10_000;
let browser: Browser | undefined;

beforeAll(async () => {
	browser = await chromium.launch({ channel: "chromium" });
}, 30_000);

afterAll(async () => {
	await browser?.close();
	browser = undefined;
});

function loadPage() {
	const html = readFileSync(prototypePath, "utf-8");
	return new JSDOM(html).window.document;
}

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadDefaultViewHtml() {
	const html = loadHtml();
	const start = html.indexOf('<section id="default-view"');
	const end = html.indexOf('<section id="states-gallery"');

	return start >= 0 && end > start ? html.slice(start, end) : html;
}

describe("page-orders-ledger prototype", () => {
	it("uses a gate-recognizable ledger shell with bounded main and trace regions", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-ledger.catalog-shell")).not.toBeNull();
		expect(
			document.querySelector('#default-view > .shell-ledger[data-resizable-panel-group="ops-main-detail"]'),
		).not.toBeNull();
		expect(document.querySelector("#default-view .resize-separator[aria-controls='main-content order-trace-panel']")).not.toBeNull();
		expect(document.querySelector(".ledger-table-area.catalog-main[data-contract-slot='order-list']")).not.toBeNull();
		expect(document.querySelector(".order-trace.catalog-detail[data-contract-slot='execution-trace']")).not.toBeNull();
	});

	it(
		"keeps every order status tab attached to the ledger grid without list drift",
		async () => {
			await withPrototypePage({ width: 1366, height: 768 }, async (page) => {
				for (const tabId of ["orders-done", "orders-pending", "orders-submitted", "orders-partial", "orders-failed"]) {
					await checkRadio(page, tabId);

					const layout = await page.evaluate((activeTabId) => {
						const panel = document.querySelector<HTMLElement>(`[data-panel="${activeTabId}"]`);
						const tableArea = panel?.querySelector<HTMLElement>(".ledger-table-area");
						const shell = document.querySelector<HTMLElement>("#default-view > .shell-ledger");
						if (!panel || !tableArea || !shell) return null;

						const panelDisplay = getComputedStyle(panel).display;
						const tableGridArea = getComputedStyle(tableArea).gridArea;
						const tableRect = tableArea.getBoundingClientRect();
						const shellRect = shell.getBoundingClientRect();

						return {
							panelDisplay,
							tableGridArea,
							tableLeft: Math.round(tableRect.left),
							shellLeft: Math.round(shellRect.left),
						};
					}, tabId);

					expect(layout).not.toBeNull();
					expect(layout?.panelDisplay).toBe("contents");
					expect(layout?.tableGridArea).toBe("table");
					expect(layout?.tableLeft).toBeGreaterThan(layout?.shellLeft ?? 0);
				}
			});
		},
		15_000,
	);

	it(
		"keeps the quick order filters wired so only one table panel is visible",
		async () => {
			await withPrototypePage({ width: 1366, height: 768 }, async (page) => {
				await expectVisiblePanels(page, ["all"]);

				await page.locator('[data-tab-target="pending"]').click();
				await expectVisiblePanels(page, ["pending"]);

				await page.locator('[data-tab-target="filled"]').click();
				await expectVisiblePanels(page, ["filled"]);
			});
		},
		15_000,
	);

	it(
		"keeps the terminal status bar out of the compact viewport table content",
		async () => {
			await withPrototypePage({ width: 1366, height: 768 }, async (page) => {
				const overlap = await page.evaluate(() => {
					const statusBar = document.querySelector("#default-view > .status-bar");
					const table = document.querySelector("#default-view .ledger-table");

					if (!statusBar || !table) {
						return { intersects: true, overlapHeight: -1 };
					}

					const statusRect = statusBar.getBoundingClientRect();
					const tableRect = table.getBoundingClientRect();
					const overlapHeight = Math.min(statusRect.bottom, tableRect.bottom) -
						Math.max(statusRect.top, tableRect.top);

					return {
						intersects: overlapHeight > 5,
						overlapHeight: Math.round(overlapHeight),
					};
				});

				expect(overlap).toEqual({ intersects: false, overlapHeight: expect.any(Number) });
			});
		},
		15_000,
	);

	it("keeps the default ledger dense enough for an execution console", () => {
		const document = loadPage();
		const defaultRows = document.querySelectorAll(
			'#default-view [data-tab-panel="all"] .ledger-table tbody tr',
		);

		expect(defaultRows.length).toBeGreaterThanOrEqual(18);
	});

	it("keeps default-view numeric values deterministic for visual review screenshots", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#default-view [data-counter], #default-view [data-ticker]")).toHaveLength(0);
	});

	it("keeps default-view entrance motion subtle and non-jittery", () => {
		const defaultView = loadDefaultViewHtml();
		const delays = [...defaultView.matchAll(/data-reveal-delay="(\d+)"/g)].map((match) => Number(match[1]));

		expect(defaultView).not.toContain('data-reveal="fade-right"');
		expect(Math.max(...delays)).toBeLessThanOrEqual(220);
	});

	it(
		"uses the full default ledger width for scan-ready columns",
		async () => {
			await withPrototypePage({ width: 1536, height: 1080 }, async (page) => {
				const trailingGap = await page.evaluate(() => {
					const table = document.querySelector('#default-view [data-tab-panel="all"] .ledger-table');
					const lastCell = document.querySelector(
						'#default-view [data-tab-panel="all"] .ledger-table tbody tr:first-child td:last-child',
					);

					if (!table || !lastCell) {
						return Number.POSITIVE_INFINITY;
					}

					return Math.round(table.getBoundingClientRect().right - lastCell.getBoundingClientRect().right);
				});

				expect(trailingGap).toBeLessThanOrEqual(4);
			});
		},
		15_000,
	);

	it(
		"supports order status tabs, prototype zones, and overlay triggers at runtime",
		async () => {
			await withPrototypePage({ width: 1366, height: 768 }, async (page) => {
				await page.locator('label[for="orders-pending"]').click();
				await expectCssVisible(page, '[data-panel="orders-pending"]', true);
				await expectCssVisible(page, '[data-panel="orders-done"]', false);

				await checkRadio(page, "view-states");
				await expectCssVisible(page, "#states-gallery", true);
				await expectCssVisible(page, "#default-view", false);

				await checkRadio(page, "view-default");
				await page.locator('label[for="overlay-batch-cancel"]').first().click();
					await expect(
						await page.locator("#overlay-batch-cancel").evaluate((element) => {
							if (!(element instanceof HTMLInputElement)) throw new TypeError("Expected batch-cancel input");
							return element.checked;
						}),
					).toBe(true);
				await expectCssVisible(page, '[data-overlay="overlay-batch-cancel"]', true);
			});
		},
		15_000,
	);
});

async function withPrototypePage(viewport: { width: number; height: number }, run: (page: Page) => Promise<void>) {
	if (!browser) {
		throw new Error("Chromium browser was not initialized");
	}

	const page = await browser.newPage({ viewport });
	page.setDefaultTimeout(2_000);

	try {
		await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });
		await run(page);
	} finally {
		await page.close();
	}
}

async function expectVisiblePanels(page: import("playwright").Page, visiblePanels: string[]) {
	const panelStates = await page.locator("[data-tab-panel]").evaluateAll((panels) =>
		panels.map((panel) => ({
			id: panel.getAttribute("data-tab-panel") ?? "",
			visible: getComputedStyle(panel).display !== "none",
		})),
	);

	const visibleIds = panelStates.filter((panel) => panel.visible).map((panel) => panel.id);

	expect(visibleIds).toEqual(visiblePanels);
}

async function expectCssVisible(page: import("playwright").Page, selector: string, visible: boolean) {
	const isVisible = await page.locator(selector).first().evaluate((element) => {
		const style = getComputedStyle(element);
		const rect = element.getBoundingClientRect();
		const hasVisibleBox = rect.width > 0 && rect.height > 0;
		const hasVisibleChildBox = Array.from(element.children).some((child) => {
			const childStyle = getComputedStyle(child);
			const childRect = child.getBoundingClientRect();

			return childStyle.display !== "none" && childStyle.visibility !== "hidden" && childRect.width > 0 && childRect.height > 0;
		});

		return style.display !== "none" && style.visibility !== "hidden" && (hasVisibleBox || hasVisibleChildBox);
	});

	expect(isVisible).toBe(visible);
}

async function checkRadio(page: import("playwright").Page, id: string) {
	await page.evaluate((radioId) => {
		const input = document.getElementById(radioId);

		if (!(input instanceof HTMLInputElement)) {
			throw new Error(`Radio not found: ${radioId}`);
		}

		input.checked = true;
		input.dispatchEvent(new Event("change", { bubbles: true }));
	}, id);
}

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-orders-ledger.html",
);

function loadPage() {
	const html = readFileSync(prototypePath, "utf-8");
	return new JSDOM(html).window.document;
}

describe("page-orders-ledger prototype", () => {
	it("uses a gate-recognizable ledger shell with bounded main and trace regions", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-ledger.catalog-shell")).not.toBeNull();
		expect(document.querySelector(".ledger-table-area.catalog-main[data-contract-slot='order-list']")).not.toBeNull();
		expect(document.querySelector(".order-trace.catalog-detail[data-contract-slot='execution-trace']")).not.toBeNull();
	});

	it(
		"keeps the quick order filters wired so only one table panel is visible",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

				await expectVisiblePanels(page, ["all"]);

				await page.locator('[data-tab-target="pending"]').click();
				await expectVisiblePanels(page, ["pending"]);

				await page.locator('[data-tab-target="filled"]').click();
				await expectVisiblePanels(page, ["filled"]);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"keeps the terminal status bar out of the compact viewport table content",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

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
			} finally {
				await browser.close();
			}
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

	it(
		"uses the full default ledger width for scan-ready columns",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

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
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"supports order status tabs, prototype zones, and overlay triggers at runtime",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

				await page.locator('label[for="orders-pending"]').click();
				await expectCssVisible(page, '[data-panel="orders-pending"]', true);
				await expectCssVisible(page, '[data-panel="orders-done"]', false);

				await checkRadio(page, "view-states");
				await expectCssVisible(page, "#states-gallery", true);
				await expectCssVisible(page, "#default-view", false);

				await checkRadio(page, "view-default");
				await page.locator('label[for="overlay-batch-cancel"]').first().click();
				await expect(await page.locator("#overlay-batch-cancel").evaluate((element) => element.checked)).toBe(true);
				await expectCssVisible(page, '[data-overlay="overlay-batch-cancel"]', true);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);
});

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

		return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
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

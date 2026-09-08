import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium, type Browser, type Page } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../prototype/page-signals-inbox.html",
);

function loadPage() {
	const html = readFileSync(prototypePath, "utf-8");
	return new JSDOM(html).window.document;
}

const prototypeUrl = `file://${prototypePath}`;
const navigationTimeoutMs = 10_000;
let browser: Browser | undefined;

beforeAll(async () => {
	browser = await chromium.launch({ channel: "chromium" });
}, 30_000);

afterAll(async () => {
	await browser?.close();
	browser = undefined;
});

const expectedRailItems = [
	{ domain: "home", label: "首页", icon: "home", current: false },
	{ domain: "markets", label: "市场", icon: "trending-up", current: false },
	{ domain: "research", label: "研究", icon: "book-open", current: false },
	{ domain: "trading", label: "交易", icon: "candlestick-chart", current: true },
	{ domain: "platform", label: "平台", icon: "server-cog", current: false },
] as const;

describe("page-signals-inbox prototype", () => {
	it("keeps all ops-console regions inside the gate-recognizable shell grid", () => {
		const document = loadPage();
		const shell = document.querySelector("#default-view > .shell-signals.shell-ops");
		const railItems = Array.from(shell?.querySelectorAll<HTMLElement>(".shell-rail .rail-icon[data-rail-domain]") ?? []);

		expect(shell).not.toBeNull();
		expect(shell?.getAttribute("data-resizable-panel-group")).toBe("ops-main-detail");
		expect(shell?.querySelector(".resize-separator[aria-controls='main-content signal-detail-panel']")).not.toBeNull();
		expect(shell?.querySelector(".shell-rail")).not.toBeNull();
		expect(
			railItems.map((item) => ({
				domain: item.dataset["railDomain"],
				label: item.getAttribute("aria-label"),
				title: item.getAttribute("title"),
				icon: item.dataset["icon"],
				current: item.getAttribute("aria-current"),
				active: item.classList.contains("active"),
			})),
		).toEqual(
			expectedRailItems.map((item) => ({
				domain: item.domain,
				label: item.label,
				title: item.label,
				icon: item.icon,
				current: item.current ? "page" : null,
				active: item.current,
			})),
		);
		expect(shell?.querySelector(".shell-header")).not.toBeNull();
		expect(shell?.querySelector('[data-contract-slot="main"]')).not.toBeNull();
		expect(shell?.querySelector('[data-contract-slot="detail"]')).not.toBeNull();
	});

	it("renders the full pending queue promised by the default tab count", () => {
		const document = loadPage();
		const pendingRows = document.querySelectorAll(
			'#default-view [data-panel="tab-pending"] [data-tab-panel="all"] tbody tr',
		);

		expect(pendingRows).toHaveLength(12);
	});

	it("does not hide scrollable signal rows behind viewport reveal observers", () => {
		const document = loadPage();
		const revealRows = document.querySelectorAll(
			'#default-view [data-panel="tab-pending"] [data-tab-panel="all"] tbody tr[data-reveal]',
		);

		expect(revealRows).toHaveLength(0);
	});

	it("keeps default-view numeric values deterministic for visual review screenshots", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#default-view [data-ticker], #default-view [data-counter]")).toHaveLength(0);
	});

	it(
		"keeps every signal status tab list stretched to the available panel width and height",
		async () => {
			await withPrototypePage({ width: 1366, height: 768 }, async (page) => {
				for (const tabId of ["tab-pending", "tab-confirmed", "tab-ignored", "tab-ordered"]) {
					await page.locator(`label[for="${tabId}"]`).click();

					const geometry = await page.evaluate((activeTabId) => {
						const panelName = activeTabId;
						const panel = document.querySelector<HTMLElement>(`[data-panel="${panelName}"]`);
						const wrapper = panel?.querySelector<HTMLElement>(".signals-table-wrap");
						const table = wrapper?.querySelector<HTMLTableElement>(".data-table");
						if (!panel || !wrapper || !table) return null;

						const panelRect = panel.getBoundingClientRect();
						const wrapperRect = wrapper.getBoundingClientRect();
						const tableRect = table.getBoundingClientRect();

						return {
							wrapperRight: Math.round(wrapperRect.right),
							panelRight: Math.round(panelRect.right),
							wrapperBottom: Math.round(wrapperRect.bottom),
							panelBottom: Math.round(panelRect.bottom),
							tableRight: Math.round(tableRect.right),
							wrapperLeft: Math.round(wrapperRect.left),
						};
					}, tabId);

					expect(geometry).not.toBeNull();
					if (!geometry) continue;
					expect(geometry.wrapperRight).toBeGreaterThanOrEqual(geometry.panelRight - 1);
					expect(geometry.wrapperBottom).toBeGreaterThanOrEqual(geometry.panelBottom - 1);
					expect(geometry.tableRight).toBeGreaterThanOrEqual(geometry.wrapperRight - 1);
					expect(geometry.wrapperLeft).toBeLessThan(geometry.wrapperRight);
				}
			});
		},
		15_000,
	);

	it(
		"keeps the shell header title and subtitle visually separated",
		async () => {
			await withPrototypePage({ width: 1366, height: 768 }, async (page) => {
				const headerTitle = await page.evaluate(() => {
					const group = document.querySelector<HTMLElement>(".shell-header .header-title-group");
					const title = document.querySelector<HTMLElement>(".shell-header .header-title");
					const subtitle = document.querySelector<HTMLElement>(".shell-header .header-subtitle");
					if (!group || !title || !subtitle) return null;

					const titleRect = title.getBoundingClientRect();
					const subtitleRect = subtitle.getBoundingClientRect();
					const titleStyle = getComputedStyle(title);
					const subtitleStyle = getComputedStyle(subtitle);

					return {
						titleText: title.textContent?.trim() ?? "",
						subtitleText: subtitle.textContent?.trim() ?? "",
						subtitleIsNestedInTitle: title.contains(subtitle),
						gap: Math.round(subtitleRect.left - titleRect.right),
						titleFontSize: titleStyle.fontSize,
						subtitleFontSize: subtitleStyle.fontSize,
						titleColor: titleStyle.color,
						subtitleColor: subtitleStyle.color,
					};
				});

				expect(headerTitle).toMatchObject({
					titleText: "信号收件箱",
					subtitleText: "交易控制中心",
					subtitleIsNestedInTitle: false,
					titleFontSize: "16px",
					subtitleFontSize: "12px",
				});
				expect(headerTitle?.gap).toBeGreaterThanOrEqual(6);
				expect(headerTitle?.subtitleColor).not.toBe(headerTitle?.titleColor);
			});
		},
		15_000,
	);

	it(
		"stretches the pending signal table columns across the full frame",
		async () => {
			await withPrototypePage({ width: 1366, height: 768 }, async (page) => {
				const tableGeometry = await page.evaluate(() => {
					const wrapper = document.querySelector<HTMLElement>(
						'[data-panel="tab-pending"] [data-tab-panel="all"].signals-table-wrap',
					);
					const table = wrapper?.querySelector<HTMLTableElement>("table");
					const selectedRow = table?.querySelector<HTMLTableRowElement>("tbody tr.row.selected");
					const lastHeaderCell = table?.querySelector<HTMLTableCellElement>("thead th:last-child");
					const lastBodyCell = selectedRow?.querySelector<HTMLTableCellElement>("td:last-child");

					if (!wrapper || !table || !selectedRow || !lastHeaderCell || !lastBodyCell) return null;

					const wrapperRect = wrapper.getBoundingClientRect();
					const tableRect = table.getBoundingClientRect();
					const headerRect = lastHeaderCell.getBoundingClientRect();
					const bodyRect = lastBodyCell.getBoundingClientRect();

					return {
						wrapperRight: Math.round(wrapperRect.right),
						tableRight: Math.round(tableRect.right),
						headerRight: Math.round(headerRect.right),
						bodyRight: Math.round(bodyRect.right),
						tableWidth: Math.round(tableRect.width),
						occupiedWidth: Math.round(bodyRect.right - tableRect.left),
					};
				});

				expect(tableGeometry).not.toBeNull();
				if (!tableGeometry) return;

				expect(tableGeometry.tableRight).toBe(tableGeometry.wrapperRight);
				expect(tableGeometry.headerRight).toBeGreaterThanOrEqual(tableGeometry.wrapperRight - 1);
				expect(tableGeometry.bodyRight).toBeGreaterThanOrEqual(tableGeometry.wrapperRight - 1);
				expect(tableGeometry.occupiedWidth).toBeGreaterThanOrEqual(tableGeometry.tableWidth - 1);
			});
		},
		15_000,
	);

	it(
		"keeps the terminal status bar out of the signal detail viewport",
		async () => {
			await withPrototypePage({ width: 1536, height: 1080 }, async (page) => {
				const geometry = await page.evaluate(() => {
					const shell = document.querySelector("#default-view > .shell-signals");
					const detail = document.querySelector('[data-contract-slot="detail"]');
					const statusBar = document.querySelector("#default-view > .status-bar");

					if (!shell || !detail || !statusBar) {
						return { hasRequiredRegions: false };
					}

					const shellRect = shell.getBoundingClientRect();
					const detailRect = detail.getBoundingClientRect();
					const statusRect = statusBar.getBoundingClientRect();

					return {
						hasRequiredRegions: true,
						shellBottom: Math.round(shellRect.bottom),
						detailBottom: Math.round(detailRect.bottom),
						statusTop: Math.round(statusRect.top),
					};
				});

				expect(geometry).toMatchObject({ hasRequiredRegions: true });
				if (!("statusTop" in geometry)) {
					throw new Error("signals inbox geometry did not include status bar data");
				}
				expect(geometry.shellBottom).toBeLessThanOrEqual(geometry.statusTop + 1);
				expect(geometry.detailBottom).toBeLessThanOrEqual(geometry.statusTop + 1);
			});
		},
		15_000,
	);

	it(
		"supports signal status tabs, prototype zones, and overlay triggers at runtime",
		async () => {
			await withPrototypePage({ width: 1366, height: 768 }, async (page) => {
				await page.locator('label[for="tab-confirmed"]').click();
				await expectCssVisible(page, '[data-panel="tab-confirmed"]', true);
				await expectCssVisible(page, '[data-panel="tab-pending"]', false);

				await checkInput(page, "view-states", true);
				await expectCssVisible(page, "#states-gallery", true);
				await expectCssVisible(page, "#default-view", false);

				await checkInput(page, "view-default", true);
				await page.locator('label[for="tab-pending"]').click();
				await page.locator('label[for="overlay-batch-confirm"]').first().click();
				expect(
					await page.locator("#overlay-batch-confirm").evaluate((element) =>
						element instanceof HTMLInputElement ? element.checked : false,
					),
				).toBe(true);
				await expectCssVisible(page, '[data-overlay="overlay-batch-confirm"]', true);
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
		await page.goto(prototypeUrl, { waitUntil: "load", timeout: navigationTimeoutMs });
		await run(page);
	} finally {
		await page.close();
	}
}

async function expectCssVisible(page: import("playwright").Page, selector: string, visible: boolean) {
	const isVisible = await page.locator(selector).first().evaluate((element) => {
		const style = getComputedStyle(element);
		const rect = element.getBoundingClientRect();

		return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
	});

	expect(isVisible).toBe(visible);
}

async function checkInput(page: import("playwright").Page, id: string, checked: boolean) {
	await page.evaluate(
		({ inputId, nextChecked }) => {
			const input = document.getElementById(inputId);

			if (!(input instanceof HTMLInputElement)) {
				throw new Error(`Input not found: ${inputId}`);
			}

			input.checked = nextChecked;
			input.dispatchEvent(new Event("change", { bubbles: true }));
		},
		{ inputId: id, nextChecked: checked },
	);
}

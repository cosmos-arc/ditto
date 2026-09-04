import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-watchlist.html",
);
const navigationTimeoutMs = 10_000;

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-watchlist prototype", () => {
	it("uses a gate-recognizable catalog shell with toolbar, summary, table, and detail regions", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-catalog.catalog-shell")).not.toBeNull();
		expect(document.querySelector(".filter-toolbar[data-contract-slot='header']")).not.toBeNull();
		expect(document.querySelector(".watchlist-summary[aria-label*='观察列表摘要']")).not.toBeNull();
		expect(document.querySelector(".catalog-table[data-contract-slot='main']")).not.toBeNull();
		expect(document.querySelector(".catalog-detail[data-contract-slot='detail']")).not.toBeNull();
	});

	it("keeps the watchlist dense, scan-ready, and aligned with blueprint fields", () => {
		const document = loadPage();
		const rows = document.querySelectorAll("#default-view .data-table tbody tr.row");
		const headers = Array.from(document.querySelectorAll("#default-view .data-table th")).map(
			(header) => header.textContent ?? "",
		);

		expect(rows).toHaveLength(8);
		expect(headers.join(" ")).toContain("代码");
		expect(headers.join(" ")).toContain("最新价");
		expect(headers.join(" ")).toContain("信号状态");
		expect(headers.join(" ")).toContain("操作");
		expect(document.querySelector("[data-watchlist-count]")?.textContent).toContain("8");
		expect(document.querySelectorAll("#default-view .watchlist-row-main")).toHaveLength(8);
	});

	it("does not rely on color alone for directional price changes", () => {
		const document = loadPage();
		const rows = Array.from(document.querySelectorAll("#default-view .data-table tbody tr.row"));

		expect(rows.length).toBeGreaterThan(0);
		for (const row of rows) {
			expect(row.getAttribute("data-direction")).toMatch(/^(up|down|flat)$/);
			expect(row.querySelector(".direction-symbol")?.textContent).toMatch(/[▲▼•]/);
		}
	});

	it("keeps the selection column compact and full-width action buttons centered", () => {
		const html = loadHtml();

		expect(html).toMatch(/\.col-select\s*\{[^}]*width:\s*28px;/s);
		expect(html).toMatch(/\.col-name\s*\{[^}]*width:\s*18%;/s);
		expect(html).toMatch(/\.catalog-detail\s+\.btn\.w-full\s*\{[^}]*justify-content:\s*center;/s);
	});

	it("covers the declared table states and watchlist overlays", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#states-gallery [data-component='watchlist-table'] .gallery-card")).toHaveLength(7);
		expect(document.querySelectorAll("#states-gallery [data-component='search-bar'] .gallery-card")).toHaveLength(2);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(2);
		expect(document.querySelector("#overlay-add-instrument")).not.toBeNull();
		expect(document.querySelector("#overlay-bulk-delete")).not.toBeNull();
		expect(document.querySelector("#default-view [data-overlay='overlay-add-instrument']")).not.toBeNull();
		expect(document.querySelector("#default-view [data-overlay='overlay-bulk-delete']")).not.toBeNull();
	});

	it("keeps all prototype markup free of inline style attributes", () => {
		expect(loadHtml()).not.toMatch(/\sstyle=/);
	});

	it(
		"supports prototype zones and both watchlist overlays at runtime",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				await page.locator("label[for='overlay-add-instrument']").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-add-instrument']", true);
				await page.locator("[data-overlay='overlay-add-instrument'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-add-instrument']", false);

				await page.locator("label[for='overlay-bulk-delete']").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-bulk-delete']", true);
				await page.locator("[data-overlay='overlay-bulk-delete'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-bulk-delete']", false);

				await checkRadio(page, "view-states");
				await expectCssVisible(page, "#states-gallery", true);
				await expectCssVisible(page, "#default-view", false);

				await checkRadio(page, "view-overlays");
				await expectCssVisible(page, "#overlays-gallery", true);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"keeps collapsed observation records at summary height in roomy viewports",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				const geometry = await page.locator('.catalog-detail details[data-collapse-priority="l3"]:not([open])').evaluate(
					(section) => {
						const summary = section.querySelector(".context-section-header");
						const sectionRect = section.getBoundingClientRect();
						const summaryRect = summary?.getBoundingClientRect();

						return {
							sectionHeight: Math.round(sectionRect.height),
							summaryHeight: Math.round(summaryRect?.height ?? 0),
						};
					},
				);

				expect(geometry.sectionHeight).toBeLessThan(96);
				expect(geometry.sectionHeight).toBeLessThanOrEqual(geometry.summaryHeight + 32);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"keeps compact right rail content clear of the viewport bottom",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				const geometry = await page.evaluate(() => {
					const detail = document.querySelector(".catalog-detail");
					const actionSection = document.querySelector(".catalog-detail .context-section:last-child");
					const sections = Array.from(document.querySelectorAll(".catalog-detail .context-section"));

					if (!detail || !actionSection) {
						return { hasRequiredRegions: false };
					}

					const actionRect = actionSection.getBoundingClientRect();
					const clippedSections = sections
						.map((section, index) => ({
							index,
							clientHeight: section.clientHeight,
							scrollHeight: section.scrollHeight,
						}))
						.filter((section) => section.scrollHeight > section.clientHeight + 1);

					return {
						hasRequiredRegions: true,
						actionBottom: Math.round(actionRect.bottom),
						detailClientHeight: detail.clientHeight,
						detailScrollHeight: detail.scrollHeight,
						viewportBottom: window.innerHeight,
						clippedSections,
					};
				});

				expect(geometry).toMatchObject({ hasRequiredRegions: true });
				if (!("actionBottom" in geometry)) {
					throw new Error("right rail geometry did not include action data");
				}
				expect(geometry.actionBottom).toBeLessThanOrEqual(geometry.viewportBottom - 8);
				expect(geometry.detailScrollHeight).toBeLessThanOrEqual(geometry.detailClientHeight);
				expect(geometry.clippedSections).toHaveLength(0);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);
});

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

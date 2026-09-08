import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../prototype/page-strategy-list.html",
);
const navigationTimeoutMs = 10_000;

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-strategy-list prototype", () => {
	it("uses a gate-recognizable catalog shell with bounded filter, table, and detail slots", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-catalog.catalog-shell")).not.toBeNull();
		expect(document.querySelector(".filter-toolbar[data-contract-slot='header']")).not.toBeNull();
		expect(document.querySelector(".perf-summary")).not.toBeNull();
		expect(document.querySelector(".catalog-table[data-contract-slot='main']")).not.toBeNull();
		expect(document.querySelector(".catalog-detail[data-contract-slot='detail']")).not.toBeNull();
	});

	it("keeps the strategy list dense, scan-ready, and aligned with the blueprint fields", () => {
		const document = loadPage();
		const rows = document.querySelectorAll("#default-view .data-table tbody tr.row");
		const headers = Array.from(document.querySelectorAll("#default-view .data-table th")).map(
			(header) => header.textContent ?? "",
		);

		expect(rows).toHaveLength(12);
		expect(headers.join(" ")).toContain("MDD");
		expect(headers.join(" ")).toContain("操作");
		expect(document.querySelectorAll("#default-view .strategy-name-stack")).toHaveLength(12);
		expect(document.querySelectorAll("#default-view .row-action[for='overlay-strategy-clone']")).toHaveLength(13);
	});

	it("does not rely on color alone for positive performance values", () => {
		const document = loadPage();
		const positiveReturns = Array.from(document.querySelectorAll("#default-view .data-table .metric-delta"))
			.map((marker) => marker.closest("td"))
				.filter((cell): cell is HTMLTableCellElement => cell !== null);

		expect(positiveReturns.length).toBeGreaterThan(0);
		for (const cell of positiveReturns) {
			expect(cell.textContent).toContain("▲");
			expect(cell.querySelector(".metric-delta")).not.toBeNull();
		}
	});

	it("keeps all prototype markup free of inline style attributes", () => {
		expect(loadHtml()).not.toMatch(/\sstyle=/);
	});

	it("centers full-width detail action button labels", () => {
		expect(loadHtml()).toMatch(/\.detail-actions\s+\.btn\s*\{[^}]*justify-content:\s*center;/s);
	});

	it("covers filter, performance summary, table states, and both modal overlays", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#states-gallery [data-component='filter-bar'] .gallery-card")).toHaveLength(4);
		expect(document.querySelectorAll("#states-gallery [data-component='perf-summary'] .gallery-card")).toHaveLength(2);
		expect(document.querySelectorAll("#states-gallery [data-component='strategy-table'] .gallery-card")).toHaveLength(6);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(2);
		expect(document.querySelector("#overlay-strategy-clone")).not.toBeNull();
		expect(document.querySelector("#overlay-strategy-delete")).not.toBeNull();
	});

	it(
		"supports prototype zones and strategy clone/delete overlays at runtime",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				await page.locator("label[for='overlay-strategy-clone']").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-strategy-clone']", true);
				await page.locator("[data-overlay='overlay-strategy-clone'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-strategy-clone']", false);

				await page.locator("label[for='overlay-strategy-delete']").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-strategy-delete']", true);
				await page.locator("[data-overlay='overlay-strategy-delete'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-strategy-delete']", false);

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

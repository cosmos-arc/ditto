import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-backtest-list.html",
);

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-backtest-list prototype", () => {
	it("uses a gate-recognizable catalog shell with filter, table, and detail regions", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-catalog.catalog-shell")).not.toBeNull();
		expect(document.querySelector(".filter-toolbar[data-contract-slot='header']")).not.toBeNull();
		expect(document.querySelector(".catalog-table[data-contract-slot='main']")).not.toBeNull();
		expect(document.querySelector(".catalog-detail[data-contract-slot='detail']")).not.toBeNull();
	});

	it("keeps the backtest catalog dense, scan-ready, and aligned with blueprint fields", () => {
		const document = loadPage();
		const rows = document.querySelectorAll("#default-view .data-table tbody tr.row");
		const headers = Array.from(document.querySelectorAll("#default-view .data-table th")).map(
			(header) => header.textContent ?? "",
		);

		expect(rows).toHaveLength(10);
		expect(headers.join(" ")).toContain("Sharpe");
		expect(headers.join(" ")).toContain("年化收益");
		expect(headers.join(" ")).toContain("MDD");
		expect(headers.join(" ")).toContain("操作");
		expect(document.querySelectorAll("#default-view .backtest-name-stack")).toHaveLength(10);
		expect(
			document.querySelectorAll("#default-view .row-action[for='overlay-backtest-compare']").length,
		).toBeGreaterThanOrEqual(6);
	});

	it("does not rely on color alone for directional backtest metrics", () => {
		const document = loadPage();
		const metricCells = Array.from(document.querySelectorAll("#default-view .data-table .metric-delta"))
			.map((marker) => marker.closest("td"))
			.filter((cell): cell is Element => cell !== null);

		expect(metricCells.length).toBeGreaterThan(0);
		for (const cell of metricCells) {
			expect(cell.textContent).toMatch(/[▲▼]/);
			expect(cell.querySelector(".metric-delta")).not.toBeNull();
		}
	});

	it("keeps all prototype markup free of inline style attributes", () => {
		expect(loadHtml()).not.toMatch(/\sstyle=/);
	});

	it("covers filter, table states, and the compare drawer", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#states-gallery [data-component='filter-bar'] .gallery-card")).toHaveLength(4);
		expect(document.querySelectorAll("#states-gallery [data-component='backtest-table'] .gallery-card")).toHaveLength(6);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(1);
		expect(document.querySelector("#overlay-backtest-compare")).not.toBeNull();
		expect(document.querySelector("#default-view [data-overlay='overlay-backtest-compare']")).not.toBeNull();
	});

	it(
		"supports prototype zones and the backtest compare drawer at runtime",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

				await page.locator("label[for='overlay-backtest-compare']").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-backtest-compare']", true);
				await page.locator("[data-overlay='overlay-backtest-compare'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-backtest-compare']", false);

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

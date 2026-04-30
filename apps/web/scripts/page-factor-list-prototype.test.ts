import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-factor-list.html",
);
const navigationTimeoutMs = 10_000;

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-factor-list prototype", () => {
	it("uses a gate-recognizable catalog shell with filter, summary, table, and detail regions", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-catalog.catalog-shell")).not.toBeNull();
		expect(document.querySelector(".filter-toolbar[data-contract-slot='header']")).not.toBeNull();
		expect(document.querySelector(".health-summary[aria-label='因子健康摘要']")).not.toBeNull();
		expect(document.querySelector(".catalog-table[data-contract-slot='main']")).not.toBeNull();
		expect(document.querySelector(".catalog-detail[data-contract-slot='detail']")).not.toBeNull();
	});

	it("keeps the factor catalog dense, scan-ready, and aligned with blueprint fields", () => {
		const document = loadPage();
		const rows = document.querySelectorAll("#default-view .data-table tbody tr.row");
		const headers = Array.from(document.querySelectorAll("#default-view .data-table th")).map(
			(header) => header.textContent ?? "",
		);

		expect(rows).toHaveLength(12);
		expect(headers.join(" ")).toContain("衰减率");
		expect(headers.join(" ")).toContain("关联策略数");
		expect(document.querySelectorAll("#default-view .factor-name-stack")).toHaveLength(12);
		expect(document.querySelectorAll("#default-view .row-action[for='overlay-factor-compare']").length).toBeGreaterThanOrEqual(
			4,
		);
	});

	it("does not rely on color alone for directional factor metrics", () => {
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

	it("covers filter, health summary, table states, and the compare drawer", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#states-gallery [data-component='filter-bar'] .gallery-card")).toHaveLength(4);
		expect(document.querySelectorAll("#states-gallery [data-component='health-summary'] .gallery-card")).toHaveLength(2);
		expect(document.querySelectorAll("#states-gallery [data-component='factor-table'] .gallery-card")).toHaveLength(6);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(1);
		expect(document.querySelector("#overlay-factor-compare")).not.toBeNull();
		expect(document.querySelector("#default-view [data-overlay='overlay-factor-compare']")).not.toBeNull();
	});

	it(
		"supports prototype zones and the factor compare drawer at runtime",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				await page.locator("label[for='overlay-factor-compare']").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-factor-compare']", true);
				await page.locator("[data-overlay='overlay-factor-compare'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-factor-compare']", false);

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

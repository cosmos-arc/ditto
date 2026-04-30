import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-universe-list.html",
);
const navigationTimeoutMs = 10_000;

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-universe-list prototype", () => {
	it("uses a gate-recognizable catalog shell with header, filter, table, and detail slots", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-catalog.catalog-shell")).not.toBeNull();
		expect(document.querySelector(".shell-header[data-contract-slot='header']")).not.toBeNull();
		expect(document.querySelector(".filter-toolbar[data-contract-slot='header']")).not.toBeNull();
		expect(document.querySelector(".catalog-table[data-contract-slot='main']")).not.toBeNull();
		expect(document.querySelector(".catalog-detail[data-contract-slot='detail']")).not.toBeNull();
	});

	it("keeps the universe catalog dense, actionable, and aligned with the blueprint fields", () => {
		const document = loadPage();
		const rows = document.querySelectorAll("#default-view .data-table tbody tr.row");
		const headers = Array.from(document.querySelectorAll("#default-view .data-table th")).map(
			(header) => header.textContent ?? "",
		);

		expect(rows.length).toBeGreaterThanOrEqual(12);
		expect(headers.join(" ")).toContain("标的数");
		expect(headers.join(" ")).toContain("来源");
		expect(headers.join(" ")).toContain("关联策略数");
		expect(headers.join(" ")).toContain("更新时间");
		expect(document.querySelectorAll("#default-view [data-universe-id]")).toHaveLength(rows.length);
		expect(document.querySelectorAll("#default-view .row-action[for='overlay-universe-edit']").length).toBeGreaterThanOrEqual(
			4,
		);
		expect(document.querySelectorAll("#default-view .row-action[for='overlay-universe-delete']").length).toBeGreaterThanOrEqual(
			4,
		);
	});

	it("does not rely on color alone for stale and selected states", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view .freshness-badge[data-freshness='stale']")).not.toBeNull();
		expect(document.querySelector("#default-view .row.selected .selection-mark")).not.toBeNull();
		expect(document.querySelector("#default-view .batch-summary")).not.toBeNull();
	});

	it("keeps the selection column compact while preserving balanced table width", () => {
		const document = loadPage();
		const html = loadHtml();

		expect(document.querySelector("#default-view .data-table th.col-select")).not.toBeNull();
		expect(document.querySelector("#default-view .data-table tbody td.col-select")).not.toBeNull();
		expect(html).toMatch(/\.col-select\s*\{[^}]*width:\s*30px;/s);
		expect(html).toMatch(/\.col-name\s*\{[^}]*width:\s*26%;/s);
	});

	it("keeps all prototype markup free of inline style attributes", () => {
		expect(loadHtml()).not.toMatch(/\sstyle=/);
	});

	it("covers filter, table states, and both universe overlays", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#states-gallery [data-component='filter-bar'] .gallery-card")).toHaveLength(4);
		expect(document.querySelectorAll("#states-gallery [data-component='universe-table'] .gallery-card")).toHaveLength(6);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(2);
		expect(document.querySelector("#overlay-universe-edit")).not.toBeNull();
		expect(document.querySelector("#overlay-universe-delete")).not.toBeNull();
		expect(document.querySelector("#default-view [data-overlay='overlay-universe-edit']")).not.toBeNull();
		expect(document.querySelector("#default-view [data-overlay='overlay-universe-delete']")).not.toBeNull();
	});

	it(
		"supports prototype zones plus create and delete overlays at runtime",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				await page.locator("label[for='overlay-universe-edit']").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-universe-edit']", true);
				await page.locator("[data-overlay='overlay-universe-edit'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-universe-edit']", false);

				await page.locator("label[for='overlay-universe-delete']").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-universe-delete']", true);
				await page.mouse.click(20, 20);
				await expectCssVisible(page, "[data-overlay='overlay-universe-delete']", false);

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

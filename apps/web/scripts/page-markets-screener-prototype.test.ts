import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../prototype/page-markets-screener.html",
);
const navigationTimeoutMs = 10_000;

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

function elementText(root: Element | null, selector: string) {
	return root?.querySelector(selector)?.textContent ?? "";
}

describe("page-markets-screener prototype", () => {
	it("uses a gate-recognizable catalog shell with bounded main, filter, and detail slots", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-catalog.catalog-shell")).not.toBeNull();
		expect(document.querySelector(".filter-toolbar[data-contract-slot='filter-panel']")).not.toBeNull();
		expect(document.querySelector(".catalog-table[data-contract-slot='results-table']")).not.toBeNull();
		expect(document.querySelector(".catalog-detail[data-contract-slot='detail']")).not.toBeNull();
	});

	it("documents screener scope, color, rank, and active filter semantics for fast scan reading", () => {
		const document = loadPage();
		const strip = document.querySelector(".screener-insight-strip");

		expect(strip).not.toBeNull();
		expect(elementText(strip, "[data-screener-scope]")).toContain("沪深300");
		expect(elementText(strip, "[data-screener-rank]")).toContain("排序");
		expect(elementText(strip, "[data-screener-color]")).toContain("红涨绿跌");
		expect(elementText(strip, "[data-screener-filters]")).toContain("3 条");
		expect(strip?.querySelectorAll(".screener-legend-stop")).toHaveLength(5);
	});

	it("keeps result rows direction-aware without relying on color alone", () => {
		const document = loadPage();
		const rows = Array.from(document.querySelectorAll(".data-table tbody tr.row"));

		expect(rows.length).toBeGreaterThanOrEqual(12);
		for (const row of rows) {
			expect(row.getAttribute("data-direction")).toMatch(/^(up|down|flat)$/);
			expect(row.querySelector(".direction-symbol")?.textContent).toMatch(/[▲▼•]/);
		}
	});

	it("keeps default-view numeric values deterministic for visual review screenshots", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#default-view [data-ticker], #default-view [data-counter]")).toHaveLength(
			0,
		);
	});

	it("keeps default-view entrance motion subtle and non-jittery", () => {
		const defaultView = loadDefaultViewHtml();
		const delays = [...defaultView.matchAll(/data-reveal-delay="(\d+)"/g)].map((match) => Number(match[1]));

		expect(defaultView).not.toContain('data-reveal="fade-right"');
		expect(Math.max(...delays)).toBeLessThanOrEqual(220);
	});

	it("keeps screener mode tabs wired to their panels for runtime interaction", () => {
		const document = loadPage();
		const tabs = document.querySelector('[data-tabs="screener-tabs"]');
		const html = loadHtml();

		expect(tabs).not.toBeNull();
		expect(tabs?.querySelectorAll("[data-tab-target]")).toHaveLength(3);
		expect(tabs?.querySelectorAll("[data-tab-panel]")).toHaveLength(3);
		expect(tabs?.querySelector('[data-tab-panel="filter"]')?.getAttribute("aria-hidden")).toBe("false");
		expect(tabs?.querySelector('[data-tab-panel="sort"]')?.getAttribute("aria-hidden")).toBe("true");
		expect(tabs?.querySelector('[data-tab-panel="compare"]')?.getAttribute("aria-hidden")).toBe("true");
		expect(html).not.toMatch(/\.sort-panel\s*\{[^}]*display:\s*none/s);
		expect(html).not.toMatch(/\.compare-panel\s*\{[^}]*display:\s*none/s);
	});

	it("shows the full screener workflow surface for conditions, sorting, and comparison", () => {
		const document = loadPage();

		expect(document.querySelector("[data-screener-workflow]")).not.toBeNull();
		expect(document.querySelector("[data-active-conditions]")).not.toBeNull();
		expect(document.querySelector("[data-filter-action='add-condition']")).not.toBeNull();
		expect(document.querySelector("[data-filter-action='apply']")).not.toBeNull();
		expect(document.querySelectorAll("[data-sort-option]")).toHaveLength(4);
		expect(document.querySelector("[data-sort-action='apply']")).not.toBeNull();
		expect(document.querySelector(".data-table[data-compare-source='screener-results']")).not.toBeNull();
	});

	it("keeps the right rail compact enough that scoring does not crowd the compare basket", () => {
		const document = loadPage();
		const scoreSection = document.querySelector(".score-compact-grid");
		const radar = document.querySelector(".score-radar");

		expect(scoreSection).not.toBeNull();
		expect(radar).toBeNull();
		expect(document.querySelector(".catalog-detail .compare-cta")).not.toBeNull();
	});

	it(
		"supports runtime tab switching, compare overlay opening, and filter chip feedback",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				await page.getByRole("button", { name: "中证500" }).click();
				await expectActive(page, "中证500", true);
				await expectActive(page, "沪深300", false);

				await page.locator('[data-tab-target="sort"]').click();
				await expectPanelVisible(page, "sort");

				await page.locator('[data-tab-target="compare"]').click();
				await expectPanelVisible(page, "compare");

				await page.locator('[data-tab-panel="compare"] label[for="overlay-compare"]').click();
					await expect(
						await page.locator("#overlay-compare").evaluate((element) => {
							if (!(element instanceof HTMLInputElement)) throw new TypeError("Expected comparison input");
							return element.checked;
						}),
					).toBe(true);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"makes filtering, sorting, and adding to compare visible as state changes",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				await page.getByRole("button", { name: "中证500" }).click();
				await expectLocatorText(page, "[data-filter-draft]", "中证500");

				await page.locator("[data-filter-action='add-condition']").click();
				await expectLocatorText(page, "[data-active-conditions]", "PE < 20");

				await page.locator("[data-tab-panel='filter'] [data-filter-action='apply']").click();
				await expectLocatorText(page, ".filter-count", "126");
				await expectLocatorText(page, "[data-screener-filters]", "2 条");

				await page.locator('[data-tab-target="sort"]').click();
				await page.locator("[data-sort-option='volume']").click();
				await page.locator("[data-sort-action='apply']").click();
				await expectLocatorText(page, "[data-screener-rank]", "成交额");
				const volumeClassName = await page.locator("th.col-vol").evaluate((element) => element.className);
				expect(volumeClassName.split(/\s+/)).toContain("sorted");

				await page.locator('[data-tab-target="filter"]').click();
				await page.locator("button[data-compare-add='000333']").click();
				await expectLocatorText(page, "[data-compare-count]", "4");
				await expectLocatorText(page, ".catalog-detail", "美的集团");
				const insertedCompareSectionTitle = await page
					.locator(".catalog-detail .compare-item", { hasText: "美的集团" })
					.evaluate((item) => item.closest(".context-section")?.querySelector(".context-section-title")?.textContent?.trim());
				expect(insertedCompareSectionTitle).toBe("对比篮");
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it("keeps the page in restrained Graphite Studio language", () => {
		const html = loadHtml();

		expect(html).not.toContain('data-mouse-glow="true"');
		expect(html).not.toContain(".shell-catalog::before");
		expect(html).not.toContain(".shell-catalog::after");
		expect(html).not.toContain("radial-gradient");
		expect(html).not.toContain("ambient glow");
	});
});

async function expectPanelVisible(page: import("playwright").Page, panel: string) {
	const state = await page.locator(`[data-tab-panel="${panel}"]`).evaluate((element) => ({
		display: getComputedStyle(element).display,
		hidden: element.getAttribute("aria-hidden"),
	}));

	expect(state).toEqual({ display: "block", hidden: "false" });
}

async function expectActive(page: import("playwright").Page, name: string, active: boolean) {
	const classList = await page.getByRole("button", { name }).first().evaluate((element) => element.className);

	expect(classList.split(/\s+/).includes("active")).toBe(active);
}

async function expectLocatorText(page: import("playwright").Page, selector: string, text: string) {
	const content = await page.locator(selector).first().textContent();

	expect(content).toContain(text);
}

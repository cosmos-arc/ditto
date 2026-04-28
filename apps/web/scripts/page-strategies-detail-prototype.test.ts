import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-strategies-detail.html",
);

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-strategies-detail prototype", () => {
	it("keeps the object hub regions inside one gate-recognizable shell", () => {
		const document = loadPage();
		const shell = document.querySelector("#default-view > .shell-hub.object-shell");

		expect(shell).not.toBeNull();
		expect(shell?.querySelector(":scope > .shell-rail")).not.toBeNull();
		expect(shell?.querySelector(":scope > .shell-header")).not.toBeNull();
		expect(shell?.querySelector(":scope > .hub-meta")).not.toBeNull();
		expect(shell?.querySelector(":scope > .tab-group")).not.toBeNull();
		expect(shell?.querySelector(":scope > .hub-bottom")).not.toBeNull();
		expect(document.querySelector("#default-view > .shell-header")).toBeNull();
		expect(document.querySelector("#default-view > .tab-group")).toBeNull();
	});

	it("exposes main and sidebar contract slots for design-cycle gates", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view .hub-main[data-contract-slot='main']")).not.toBeNull();
		expect(document.querySelector("#main-content[data-contract-slot='main']")).toBeNull();
		expect(document.querySelector("#default-view [data-contract-slot='sidebar']")).not.toBeNull();
	});

	it("keeps the prototype markup free of inline style attributes", () => {
		expect(loadHtml()).not.toMatch(/\sstyle=/);
	});

	it("keeps default-view numeric values deterministic for visual review screenshots", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#default-view [data-ticker], #default-view [data-counter]")).toHaveLength(0);
	});

	it("uses tokenized SVG chart typography instead of hard-coded font sizes", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#default-view svg text[font-size]")).toHaveLength(0);
		expect(document.querySelectorAll("#default-view svg text.chart-axis-label")).toHaveLength(4);
	});

	it(
		"keeps the benchmark chart label inside the SVG viewport",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

				const overflow = await page.evaluate(() => {
					const benchmarkLabel = Array.from(document.querySelectorAll<SVGTextElement>("svg text")).find(
						(text) => text.textContent === "HS300",
					);
					const svg = benchmarkLabel?.closest("svg");

					if (!benchmarkLabel || !svg) {
						return Number.POSITIVE_INFINITY;
					}

					return Math.round(benchmarkLabel.getBoundingClientRect().right - svg.getBoundingClientRect().right);
				});

				expect(overflow).toBeLessThanOrEqual(0);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"keeps the default main row attached to the bottom strip in the standard viewport",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

				const gap = await page.evaluate(() => {
					const main = document.querySelector("#default-view .hub-main");
					const bottom = document.querySelector("#default-view .hub-bottom");

					if (!main || !bottom) {
						return Number.POSITIVE_INFINITY;
					}

					return Math.round(bottom.getBoundingClientRect().top - main.getBoundingClientRect().bottom);
				});

				expect(gap).toBeLessThanOrEqual(8);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"keeps all recent backtest rows visible in the compact viewport",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

				const overflow = await page.evaluate(() => {
					const recentPanel = Array.from(
						document.querySelectorAll<HTMLElement>("#default-view [data-panel='strat-overview'] .panel"),
					).find((panel) => panel.textContent?.includes("近期回测"));
					const lastRow = recentPanel?.querySelector("tbody tr:last-child");

					if (!recentPanel || !lastRow) {
						return Number.POSITIVE_INFINITY;
					}

					return Math.round(lastRow.getBoundingClientRect().bottom - recentPanel.getBoundingClientRect().bottom);
				});

				expect(overflow).toBeLessThanOrEqual(0);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"keeps the strategy status summary compact in the standard viewport",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

				const statusHeight = await page.evaluate(() => {
					const statusPanel = Array.from(
						document.querySelectorAll<HTMLElement>("#default-view [data-panel='strat-overview'] .panel"),
					).find((panel) => panel.textContent?.includes("策略状态"));

					return Math.round(statusPanel?.getBoundingClientRect().height ?? Number.POSITIVE_INFINITY);
				});

				expect(statusHeight).toBeLessThanOrEqual(180);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);
});

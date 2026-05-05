import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-trading-overview.html",
);
const navigationTimeoutMs = 10_000;

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-trading-overview prototype", () => {
	it("compresses session, margin, risk, connectivity, and execution into one trading context bar", () => {
		const document = loadPage();
		const contextBar = document.querySelector("[data-contract-slot='trading-context-bar']");

		expect(contextBar).not.toBeNull();
		expect(document.querySelector("[data-contract-slot='session-strip']")).toBeNull();
		expect(document.querySelector("[data-contract-slot='margin-strip-wrapper']")).toBeNull();
		expect(document.querySelector("[data-contract-slot='pipeline-strip']")).toBeNull();
		expect(document.querySelector("[data-contract-slot='margin-strip']")).toBeNull();

		expect(contextBar?.querySelectorAll(".trading-context-item")).toHaveLength(8);
		expect(contextBar?.textContent).toContain("连续竞价");
		expect(contextBar?.textContent).toContain("保证金");
		expect(contextBar?.textContent).toContain("券商连接");
		expect(contextBar?.textContent).toContain("风险预算");
		expect(contextBar?.textContent).toContain("执行队列");
	});

	it("folds signal-to-order pipeline state into the primary decision card", () => {
		const document = loadPage();
		const decisionBanner = document.querySelector("[data-contract-slot='decision-banner']");
		const pipelineContext = decisionBanner?.querySelector("[data-pipeline-context]");

		expect(decisionBanner).not.toBeNull();
		expect(pipelineContext).not.toBeNull();
		expect(pipelineContext?.querySelectorAll(".pipeline-stage")).toHaveLength(4);
		expect(pipelineContext?.textContent).toContain("信号池");
		expect(pipelineContext?.textContent).toContain("待复核");
		expect(pipelineContext?.textContent).toContain("已下单");
		expect(pipelineContext?.textContent).toContain("已成交");
		expect(document.querySelector(":scope > [data-contract-slot='pipeline-strip']")).toBeNull();
	});

	it("keeps the prototype markup free of inline style attributes", () => {
		expect(loadHtml()).not.toMatch(/\sstyle=/);
	});

	it(
		"gives the main trading panels the vertical room reclaimed from stacked strips",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				const metrics = await page.evaluate(() => {
					const contextBar = document.querySelector<HTMLElement>("[data-contract-slot='trading-context-bar']");
					const mainContent = document.querySelector<HTMLElement>(".main-content");
					const positionsPanel = document.querySelector<HTMLElement>(".panel-positions");
					const ordersPanel = document.querySelector<HTMLElement>(".panel-orders");
					const shell = document.querySelector<HTMLElement>(".shell-analytical.trading-variant");

					return {
						contextBarHeight: Math.round(contextBar?.getBoundingClientRect().height ?? 0),
						gridRowCount: getComputedStyle(shell ?? document.documentElement).gridTemplateRows.split(" ").length,
						mainHeight: Math.round(mainContent?.getBoundingClientRect().height ?? 0),
						ordersHeight: Math.round(ordersPanel?.getBoundingClientRect().height ?? 0),
						positionsHeight: Math.round(positionsPanel?.getBoundingClientRect().height ?? 0),
						visibleTopStripSlots: Array.from(
							document.querySelectorAll<HTMLElement>(
								"[data-contract-slot='trading-context-bar'], [data-contract-slot='session-strip'], [data-contract-slot='margin-strip-wrapper'], [data-contract-slot='pipeline-strip']",
							),
						).filter((element) => element.getBoundingClientRect().height > 0).length,
					};
				});

				expect(metrics.visibleTopStripSlots).toBe(1);
				expect(metrics.contextBarHeight).toBeLessThanOrEqual(44);
				expect(metrics.gridRowCount).toBeLessThanOrEqual(4);
				expect(metrics.mainHeight).toBeGreaterThanOrEqual(480);
				expect(metrics.positionsHeight).toBeGreaterThanOrEqual(300);
				expect(metrics.ordersHeight).toBeGreaterThanOrEqual(210);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);
});

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
const compactViewports = [
	{ width: 1536, height: 864 },
	{ width: 1366, height: 768 },
	{ width: 1024, height: 768 },
	{ width: 768, height: 768 },
] as const;

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

	it("keeps trading context and decision pipeline out of assertive live-region semantics", () => {
		const document = loadPage();
		const contextBar = document.querySelector("[data-contract-slot='trading-context-bar']");
		const decisionBanner = document.querySelector("[data-contract-slot='decision-banner'] .decision-banner");
		const pipelineContext = decisionBanner?.querySelector("[data-pipeline-context]");

		expect(contextBar?.getAttribute("role")).toBe("region");
		expect(contextBar?.getAttribute("aria-label")).toContain("交易上下文");
		expect(contextBar?.hasAttribute("aria-live")).toBe(false);
		expect(pipelineContext?.getAttribute("role")).not.toBe("status");
		expect(pipelineContext?.hasAttribute("aria-live")).toBe(false);
		expect(decisionBanner?.querySelectorAll("[role='status']")).toHaveLength(0);
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

	it("keeps state-gallery coverage aligned with the compressed trading context contract", () => {
		const html = loadHtml();
		const document = loadPage();
		const gallery = document.querySelector("#states-gallery");
		const labels = Array.from(gallery?.querySelectorAll(".gallery-card__label") ?? []).map(
			(label) => label.textContent?.trim() ?? "",
		);

		expect(html).toContain("trading-context-bar: default[covered] loading[covered] failed[covered] stale[covered]");
		expect(html).toContain("decision-pipeline: default[covered] empty[covered]");
		expect(labels).toContain("Trading Context Bar · Loading");
		expect(labels).toContain("Trading Context Bar · Failed");
		expect(labels).toContain("Trading Context Bar · Stale");
		expect(labels).toContain("Decision Pipeline · Default");
		expect(labels).toContain("Decision Pipeline · Empty");
		expect(labels.some((label) => label.startsWith("Session Strip"))).toBe(false);
	});

	it(
		"keeps the compact trading context visible and leaves the main workspace dominant across desktop widths",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });

			try {
				for (const viewport of compactViewports) {
					const page = await browser.newPage({ viewport });

					try {
						await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

						const metrics = await page.evaluate(() => {
							const contextBar = document.querySelector<HTMLElement>("[data-contract-slot='trading-context-bar']");
							const mainContent = document.querySelector<HTMLElement>(".main-content");
							const banner = document.querySelector<HTMLElement>(".trading-banner");
							const equityPanel = document.querySelector<HTMLElement>(".panel-equity");
							const positionsPanel = document.querySelector<HTMLElement>(".panel-positions");
							const ordersPanel = document.querySelector<HTMLElement>(".panel-orders");
							const shell = document.querySelector<HTMLElement>(".shell-analytical.trading-variant");
							const contextRect = contextBar?.getBoundingClientRect();
							const rootStyle = getComputedStyle(document.documentElement);
							const stripHeightValue = rootStyle.getPropertyValue("--density-strip-height").trim();
							const rootFontSize = Number.parseFloat(rootStyle.fontSize);
							const densityStripHeight = stripHeightValue.endsWith("rem")
								? Number.parseFloat(stripHeightValue) * rootFontSize
								: Number.parseFloat(stripHeightValue);
							const contextItems = Array.from(
								contextBar?.querySelectorAll<HTMLElement>(".trading-context-item") ?? [],
							);

							return {
								bannerHeight: Math.round(banner?.getBoundingClientRect().height ?? 0),
								contextBarHeight: Math.round(contextRect?.height ?? 0),
								contextItemCount: contextItems.length,
								equityHeight: Math.round(equityPanel?.getBoundingClientRect().height ?? 0),
								gridRowCount: getComputedStyle(shell ?? document.documentElement).gridTemplateRows.split(" ").length,
								mainHeight: Math.round(mainContent?.getBoundingClientRect().height ?? 0),
								ordersHeight: Math.round(ordersPanel?.getBoundingClientRect().height ?? 0),
								overflowX: contextBar ? getComputedStyle(contextBar).overflowX : "",
								overflowY: contextBar ? getComputedStyle(contextBar).overflowY : "",
								positionsHeight: Math.round(positionsPanel?.getBoundingClientRect().height ?? 0),
								stripHeightRatio: contextRect && densityStripHeight ? contextRect.height / densityStripHeight : 0,
								visibleContextItems: contextItems.filter((item) => {
									const itemRect = item.getBoundingClientRect();
									if (!contextRect) return false;

									return (
										itemRect.left >= contextRect.left - 1 &&
										itemRect.right <= contextRect.right + 1 &&
										itemRect.top >= contextRect.top - 1 &&
										itemRect.bottom <= contextRect.bottom + 1
									);
								}).length,
								visibleTopStripSlots: Array.from(
									document.querySelectorAll<HTMLElement>(
										"[data-contract-slot='trading-context-bar'], [data-contract-slot='session-strip'], [data-contract-slot='margin-strip-wrapper'], [data-contract-slot='pipeline-strip']",
									),
								).filter((element) => element.getBoundingClientRect().height > 0).length,
							};
						});

						expect(metrics.visibleTopStripSlots, `${viewport.width}: top strip slots`).toBe(1);
						expect(metrics.gridRowCount, `${viewport.width}: grid rows`).toBeLessThanOrEqual(4);
						expect(metrics.overflowX, `${viewport.width}: overflow-x`).not.toBe("hidden");
						expect(metrics.overflowY, `${viewport.width}: overflow-y`).not.toBe("hidden");
						expect(metrics.visibleContextItems, `${viewport.width}: visible context items`).toBe(
							metrics.contextItemCount,
						);
						expect(metrics.stripHeightRatio, `${viewport.width}: context bar rows`).toBeLessThanOrEqual(3);
						expect(metrics.mainHeight, `${viewport.width}: main vs banner`).toBeGreaterThan(
							metrics.bannerHeight * 2,
						);
						expect(metrics.positionsHeight, `${viewport.width}: positions vs equity`).toBeGreaterThan(
							metrics.equityHeight,
						);
						expect(metrics.ordersHeight, `${viewport.width}: orders available`).toBeGreaterThan(
							metrics.equityHeight * 0.6,
						);
					} finally {
						await page.close();
					}
				}
			} finally {
				await browser.close();
			}
		},
		15_000,
	);
});

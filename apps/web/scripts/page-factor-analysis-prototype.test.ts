import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-factor-analysis.html",
);

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

const prototypeUrl = `file://${prototypePath}`;

describe("page-factor-analysis prototype", () => {
	it("uses the gate-recognizable Object Hub shell with complete research rail navigation", () => {
		const document = loadPage();
		const shell = document.querySelector("#default-view > .object-shell.shell-hub");
		const railNav = shell?.querySelector(".shell-rail .rail-nav");

		expect(shell).not.toBeNull();
		expect(shell?.querySelector(".shell-rail")).not.toBeNull();
		expect(shell?.querySelector(".shell-header")).not.toBeNull();
		expect(shell?.querySelector(".hub-meta")).not.toBeNull();
		expect(shell?.querySelector(".tab-group")).not.toBeNull();
		expect(shell?.querySelector(".hub-bottom")).not.toBeNull();
		expect(railNav?.querySelectorAll(":scope > .rail-icon")).toHaveLength(5);
	});

	it("places contract slots on visible main and sidebar regions rather than display-contents wrappers", () => {
		const document = loadPage();
		const tabPanels = document.querySelector("#default-view .tab-panels");
		const mainRegions = document.querySelectorAll("#default-view .tab-panel .hub-main");
		const sidebarRegions = document.querySelectorAll("#default-view .tab-panel .hub-sidebar");

		expect(tabPanels?.hasAttribute("data-contract-slot")).toBe(false);
		expect(mainRegions).toHaveLength(4);
		expect(sidebarRegions).toHaveLength(4);

		for (const region of mainRegions) {
			expect(region.getAttribute("data-contract-slot")).toBe("main");
		}
		for (const region of sidebarRegions) {
			expect(region.getAttribute("data-contract-slot")).toBe("sidebar");
		}
	});

	it("provides real default-view overlays for every header action", () => {
		const document = loadPage();
		const overlayIds = [
			"overlay-add-backtest",
			"overlay-add-experiment",
			"overlay-ai-analysis",
			"overlay-diagnostic-detail",
		];

		for (const overlayId of overlayIds) {
			expect(document.querySelector(`#${overlayId}`)).not.toBeNull();
			expect(document.querySelector(`#default-view [data-overlay="${overlayId}"]`)).not.toBeNull();
		}
	});

	it("keeps visual review screenshots deterministic and tokenized", () => {
		const document = loadPage();
		const defaultView = document.querySelector("#default-view");
		const html = loadHtml();

		expect(defaultView).not.toBeNull();
		expect(defaultView?.querySelectorAll("[data-ticker], [data-counter]")).toHaveLength(0);
		expect(html).not.toMatch(/\sstyle="/);
		expect(html).not.toMatch(/\sfont-size="/);
	});

	it("opens and closes header overlays from the default view", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load" });

			for (const overlayId of ["overlay-add-backtest", "overlay-add-experiment", "overlay-ai-analysis"]) {
				await page.click(`label[for="${overlayId}"]`);
				await expectOverlayState(page, overlayId, true);
				await page.click(`[data-overlay="${overlayId}"] .overlay-close`);
				await expectOverlayState(page, overlayId, false);
			}
		} finally {
			await browser.close();
		}
	});

	it("keeps compact IC diagnostics readable without hiding the statistics rows", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load" });

			const layout = await page.evaluate(() => {
				const contextStrip = document.querySelector(".context-strip");
				const summaryPanel = Array.from(document.querySelectorAll<HTMLElement>("[data-panel='fact-ic'] .panel"))
					.find((panel) => panel.querySelector(".panel-title")?.textContent?.includes("统计摘要"));
				const panelBody = summaryPanel?.querySelector<HTMLElement>(".panel-body");
				const bottom = document.querySelector(".hub-bottom")?.getBoundingClientRect();
				const panelRect = summaryPanel?.getBoundingClientRect();

				return {
					contextDisplay: contextStrip ? getComputedStyle(contextStrip).display : "",
					bodyClientHeight: panelBody?.clientHeight ?? 0,
					bodyScrollHeight: panelBody?.scrollHeight ?? 0,
					panelBottom: panelRect?.bottom ?? 0,
					bottomTop: bottom?.top ?? 0,
				};
			});

			expect(layout.contextDisplay).toBe("none");
			expect(layout.bodyScrollHeight).toBeLessThanOrEqual(layout.bodyClientHeight + 2);
			expect(layout.panelBottom).toBeLessThan(layout.bottomTop);
		} finally {
			await browser.close();
		}
	});
});

async function expectOverlayState(page: import("playwright").Page, overlayId: string, visible: boolean) {
	const state = await page.$eval(`[data-overlay="${overlayId}"]`, (element) => {
		const rect = element.getBoundingClientRect();
		const computed = getComputedStyle(element);
		return {
			display: computed.display,
			width: rect.width,
			height: rect.height,
		};
	});

	if (visible) {
		expect(state.display).not.toBe("none");
		expect(state.width).toBeGreaterThan(0);
		expect(state.height).toBeGreaterThan(0);
	} else {
		expect(state.display).toBe("none");
	}
}

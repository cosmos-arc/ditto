import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-strategy-studio.html",
);

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

const prototypeUrl = `file://${prototypePath}`;
const navigationTimeoutMs = 10_000;
const playwrightTestTimeoutMs = 15_000;

describe("page-strategy-studio prototype", () => {
	it("keeps all studio regions inside the gate-recognizable shell grid", () => {
		const document = loadPage();
		const shell = document.querySelector("#default-view > .shell-studio");

		expect(shell).not.toBeNull();
		expect(shell?.querySelector(".shell-rail")).not.toBeNull();
		expect(shell?.querySelector(".studio-header[data-contract-slot='header']")).not.toBeNull();
		expect(shell?.querySelector(".studio-sources")).not.toBeNull();
		expect(shell?.querySelector(".studio-main[data-contract-slot='main']")).not.toBeNull();
		expect(shell?.querySelector(".studio-inspector")).not.toBeNull();
		expect(shell?.querySelector(".studio-logs")).not.toBeNull();
	});

	it("keeps the bottom log drawer collapsed by default so it does not mask the editor", () => {
		const html = loadHtml();
		const document = loadPage();

		expect(html).toMatch(
			/grid-template-rows:\s*var\(--shell-header-height\)\s+auto\s+minmax\(0,\s*1fr\)\s+auto;/,
		);
		expect(html).toMatch(/\.studio-logs\s*\{[^}]*--bottom-tray-expanded-content-max-height:\s*min\(24vh,\s*16rem\);/s);
		expect(html).toMatch(/\.logs-header\s*\{[^}]*gap:\s*var\(--space-8\);/s);
		expect(document.querySelector("[data-bottom-tray]")?.getAttribute("data-bottom-tray-state")).toBe("collapsed");
	});

	it("keeps default-view numeric values deterministic for visual review screenshots", () => {
		const document = loadPage();
		const defaultView = document.querySelector("#default-view");

		expect(defaultView).not.toBeNull();
		if (!defaultView) {
			throw new Error("default view not found");
		}
		expect(defaultView.querySelectorAll("[data-ticker], [data-counter]")).toHaveLength(0);
	});

	it("keeps the strategy header on one readable row in compact desktop viewports", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load", timeout: navigationTimeoutMs });

			const header = await page.evaluate(() => {
				const shellHeader = document.querySelector<HTMLElement>(".studio-header");
				const strategyName = document.querySelector<HTMLElement>(".strategy-name");
				const actions = document.querySelector<HTMLElement>(".studio-actions");
				if (!shellHeader || !strategyName || !actions) return null;

				const headerRect = shellHeader.getBoundingClientRect();
				const strategyRect = strategyName.getBoundingClientRect();
				const actionsRect = actions.getBoundingClientRect();

				return {
					headerHeight: Math.round(headerRect.height),
					headerScrollHeight: shellHeader.scrollHeight,
					headerClientHeight: shellHeader.clientHeight,
					strategyHeight: Math.round(strategyRect.height),
					actionsCenterGap: Math.round(
						Math.abs((actionsRect.top + actionsRect.height / 2) - (strategyRect.top + strategyRect.height / 2)),
					),
				};
			});

			expect(header).not.toBeNull();
			if (!header) return;
			expect(header.headerScrollHeight).toBeLessThanOrEqual(header.headerClientHeight + 1);
			expect(header.strategyHeight).toBeLessThanOrEqual(header.headerHeight);
			expect(header.actionsCenterGap).toBeLessThanOrEqual(2);
		} finally {
			await browser.close();
		}
	}, playwrightTestTimeoutMs);

	it("keeps the factor preprocessing pipeline within the source rail", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load", timeout: navigationTimeoutMs });
			const pipeline = await page.$eval(".pipeline-visual", (element) => {
				const rect = element.getBoundingClientRect();
				const children = Array.from(element.children).map((child) => {
					const childRect = child.getBoundingClientRect();
					return {
						right: childRect.right,
						bottom: childRect.bottom,
					};
				});

				return {
					clientWidth: element.clientWidth,
					scrollWidth: element.scrollWidth,
					right: rect.right,
					bottom: rect.bottom,
					children,
				};
			});

			expect(pipeline.scrollWidth).toBeLessThanOrEqual(pipeline.clientWidth);
			for (const child of pipeline.children) {
				expect(child.right).toBeLessThanOrEqual(pipeline.right + 1);
				expect(child.bottom).toBeLessThanOrEqual(pipeline.bottom + 1);
			}
		} finally {
			await browser.close();
		}
	}, playwrightTestTimeoutMs);

	it("keeps the collapsed log drawer below the main workspace in the standard viewport", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load", timeout: navigationTimeoutMs });
			const layout = await page.evaluate(() => {
				const main = document.querySelector(".studio-main");
				const logs = document.querySelector(".studio-logs");
				const content = document.querySelector("[data-bottom-tray-content]");
				if (!main || !logs || !content) return null;

				const mainRect = main.getBoundingClientRect();
				const logsRect = logs.getBoundingClientRect();
				const contentRect = content.getBoundingClientRect();

				return {
					gap: Math.round(logsRect.top - mainRect.bottom),
					logsHeight: Math.round(logsRect.height),
					contentHeight: Math.round(contentRect.height),
				};
			});

			expect(layout).not.toBeNull();
			expect(layout?.gap).toBeGreaterThanOrEqual(-1);
			expect(layout?.logsHeight).toBeLessThanOrEqual(48);
			expect(layout?.contentHeight).toBe(0);
		} finally {
			await browser.close();
		}
	}, playwrightTestTimeoutMs);

	it("switches bottom log tabs between validation, dry run, and compile output", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load", timeout: navigationTimeoutMs });

			await page.click('[data-log-tab="dry-run"]');
			await expectLogState(page, {
				active: "dry-run",
				visiblePanel: "dry-run",
				expectedText: "Dry Run",
			});

			await page.click('[data-log-tab="compile"]');
			await expectLogState(page, {
				active: "compile",
				visiblePanel: "compile",
				expectedText: "编译",
			});

			await page.click('[data-log-tab="validation"]');
			await expectLogState(page, {
				active: "validation",
				visiblePanel: "validation",
				expectedText: "策略校验完成",
			});
		} finally {
			await browser.close();
		}
	}, playwrightTestTimeoutMs);
});

async function expectLogState(
	page: import("playwright").Page,
	expected: { active: string; visiblePanel: string; expectedText: string },
) {
	const state = await page.$eval(".studio-logs", (element) => {
		const activeTab = element.querySelector(".logs-tab.active");
		const visiblePanel = Array.from(element.querySelectorAll<HTMLElement>(".logs-body")).find((panel) => {
			const style = getComputedStyle(panel);
			return style.display !== "none" && panel.getAttribute("aria-hidden") !== "true";
		});

		return {
			active: activeTab?.getAttribute("data-log-tab") ?? "",
			selected: activeTab?.getAttribute("aria-selected") ?? "",
			visiblePanel: visiblePanel?.getAttribute("data-tab-panel") ?? "",
			text: visiblePanel?.textContent ?? "",
		};
	});

	expect(state.active).toBe(expected.active);
	expect(state.selected).toBe("true");
	expect(state.visiblePanel).toBe(expected.visiblePanel);
	expect(state.text).toContain(expected.expectedText);
}

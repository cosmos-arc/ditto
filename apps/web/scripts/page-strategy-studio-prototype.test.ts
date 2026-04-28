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

	it("allocates a readable log drawer row instead of collapsing logs to status-bar height", () => {
		const html = loadHtml();

		expect(html).toMatch(
			/grid-template-rows:\s*var\(--shell-header-height\)\s+auto\s+minmax\(0,\s*1fr\)\s+minmax\(128px,\s*15vh\);/,
		);
		expect(html).not.toContain(
			"grid-template-rows: var(--shell-header-height) auto 1fr var(--shell-status-bar-height);",
		);
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

	it("keeps the factor preprocessing pipeline within the source rail", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load" });
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
	});

	it("switches bottom log tabs between validation, dry run, and compile output", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load" });

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
	});
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

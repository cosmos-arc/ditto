import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-agent-console.html",
);

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

function pageStyleText(document: Document) {
	return Array.from(document.querySelectorAll("style"))
		.map((style) => style.textContent ?? "")
		.join("\n");
}

const prototypeUrl = `file://${prototypePath}`;

describe("page-agent-console prototype", () => {
	it("keeps the agent workspace in a gate-recognizable studio shell", () => {
		const document = loadPage();
		const shell = document.querySelector("#default-view > .shell-agent.studio-shell");

		expect(shell).not.toBeNull();
		expect(shell?.querySelector(".shell-rail")).not.toBeNull();
		expect(shell?.querySelector(".shell-header")).not.toBeNull();
		expect(shell?.querySelector("[data-contract-slot='main']")).not.toBeNull();
		expect(shell?.querySelector(".agent-detail[data-contract-slot='detail']")).not.toBeNull();
	});

	it("keeps status bar in normal default-view flow so it cannot cover cards", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load" });
			const statusBar = await page.$eval(".status-bar", (element) => {
				const style = getComputedStyle(element);
				return {
					position: style.position,
					flexBasis: style.flexBasis,
					height: Math.round(element.getBoundingClientRect().height),
				};
			});

			expect(statusBar.position).toBe("relative");
			expect(statusBar.flexBasis).toBe("24px");
			expect(statusBar.height).toBeGreaterThanOrEqual(22);
		} finally {
			await browser.close();
		}
	});

	it("scopes status filter tabs and panels to the same interaction group", () => {
		const document = loadPage();
		const filterScope = document.querySelector("[data-tabs='agent-status-filter']");

		expect(filterScope).not.toBeNull();
		expect(filterScope?.querySelectorAll("[data-tab-target]")).toHaveLength(4);
		expect(filterScope?.querySelectorAll("[data-tab-panel]")).toHaveLength(4);
		expect(filterScope?.querySelector("[data-tab-panel='all']")).not.toBeNull();
		expect(filterScope?.querySelector("[data-tab-panel='running']")).not.toBeNull();
		expect(filterScope?.querySelector("[data-tab-panel='completed']")).not.toBeNull();
		expect(filterScope?.querySelector("[data-tab-panel='failed']")).not.toBeNull();
	});

	it("gives the right detail panel breathing room without changing the studio shell pattern", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load" });
			const detailMetrics = await page.$eval(".agent-detail", (element) => {
				const rect = element.getBoundingClientRect();
				const style = getComputedStyle(element);
				return {
					width: Math.round(rect.width),
					background: style.backgroundColor,
				};
			});
			const headerMeta = await page.$eval(".detail-header-meta", (element) => {
				const style = getComputedStyle(element);
				return {
					display: style.display,
					columns: style.gridTemplateColumns.split(" ").filter(Boolean).length,
				};
			});

			expect(detailMetrics.width).toBeGreaterThanOrEqual(360);
			expect(headerMeta.display).toBe("grid");
			expect(headerMeta.columns).toBe(2);
		} finally {
			await browser.close();
		}
	});

	it("keeps right-panel actions aligned with the compact workspace button system", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load" });
			const actions = await page.$$eval(".detail-actions .btn-ghost", (buttons) =>
				buttons.map((button) => {
					const rect = button.getBoundingClientRect();
					const style = getComputedStyle(button);
					return {
						height: Math.round(rect.height),
						fontSize: style.fontSize,
						justifyContent: style.justifyContent,
						overflowing: button.scrollWidth > button.clientWidth,
					};
				}),
			);

			expect(actions).toHaveLength(3);
			for (const action of actions) {
				expect(action.height).toBe(28);
				expect(action.fontSize).toBe("12px");
				expect(action.justifyContent).toBe("center");
				expect(action.overflowing).toBe(false);
			}
		} finally {
			await browser.close();
		}
	});

	it("keeps the current-agent blocks fully visible in compact right panel", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load" });
			const currentAgentSection = await page.$eval(".detail-section-current", (section) => {
				const body = section.querySelector<HTMLElement>(".detail-section-body");
				const sectionRect = section.getBoundingClientRect();
				const bodyRect = body?.getBoundingClientRect();
				const blocks = Array.from(section.querySelectorAll<HTMLElement>(".agent-status-block")).map((block) => {
					const rect = block.getBoundingClientRect();
					return {
						top: rect.top,
						bottom: rect.bottom,
					};
				});

				return {
					bodyClientHeight: body?.clientHeight ?? 0,
					bodyScrollHeight: body?.scrollHeight ?? 0,
					sectionBottom: sectionRect.bottom,
					bodyBottom: bodyRect?.bottom ?? 0,
					blocks,
				};
			});

			expect(currentAgentSection.bodyScrollHeight).toBeLessThanOrEqual(
				currentAgentSection.bodyClientHeight + 1,
			);
			for (const block of currentAgentSection.blocks) {
				expect(block.bottom).toBeLessThanOrEqual(currentAgentSection.bodyBottom + 1);
			}
		} finally {
			await browser.close();
		}
	});

	it("uses the same subdued right-panel typography and status color language as other studio pages", () => {
		const document = loadPage();
		const styleText = pageStyleText(document);

		expect(styleText).toContain(".detail-section-title");
		expect(styleText).toContain("color: var(--text-secondary)");
		expect(styleText).toContain(".agent-status-block.running");
		expect(styleText).toContain("color-mix(in oklch, var(--brand-accent) 8%, transparent)");
		expect(styleText).toContain(".tool-trace-tool");
		expect(styleText).toContain("font-size: var(--font-size-10)");
	});

	it("switches status filter panels between all, running, completed, and failed", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load" });

			await page.click('[data-tab-target="running"]');
			await expectFilterState(page, "running", "多因子合成模型优化");

			await page.click('[data-tab-target="completed"]');
			await expectFilterState(page, "completed", "北向资金异常流入检测");

			await page.click('[data-tab-target="failed"]');
			await expectFilterState(page, "failed", "行业轮动策略回测");

			await page.click('[data-tab-target="all"]');
			await expectFilterState(page, "all", "Alpha 因子挖掘计划");
		} finally {
			await browser.close();
		}
	});

	it("keeps default-view numeric copy deterministic for visual review screenshots", () => {
		const document = loadPage();
		const defaultView = document.querySelector("#default-view");

		expect(defaultView).not.toBeNull();
		if (!defaultView) {
			throw new Error("default view not found");
		}

		expect(defaultView.querySelectorAll("[data-ticker], [data-counter]")).toHaveLength(0);
	});

	it("preserves declared state and overlay coverage without inline styles or duplicate ids", () => {
		const document = loadPage();
		const ids = Array.from(document.querySelectorAll("[id]")).map((element) => element.id);
		const uniqueIds = new Set(ids);

		expect(document.querySelectorAll("#states-gallery .gallery-card")).toHaveLength(19);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(4);
		expect(document.querySelectorAll(".overlay-radio")).toHaveLength(4);
		expect(document.querySelectorAll("[style]")).toHaveLength(0);
		expect(uniqueIds.size).toBe(ids.length);
	});
});

async function expectFilterState(page: import("playwright").Page, target: string, expectedText: string) {
	const state = await page.$eval("[data-tabs='agent-status-filter']", (element) => {
		const activeTab = element.querySelector("[data-tab-target].active");
		const visiblePanels = Array.from(element.querySelectorAll<HTMLElement>("[data-tab-panel]"))
			.filter((panel) => getComputedStyle(panel).display !== "none");

		return {
			active: activeTab?.getAttribute("data-tab-target") ?? "",
			selected: activeTab?.getAttribute("aria-selected") ?? "",
			visiblePanels: visiblePanels.map((panel) => panel.getAttribute("data-tab-panel") ?? ""),
			text: visiblePanels.map((panel) => panel.textContent ?? "").join("\n"),
		};
	});

	expect(state.active).toBe(target);
	expect(state.selected).toBe("true");
	expect(state.visiblePanels).toEqual([target]);
	expect(state.text).toContain(expectedText);
}

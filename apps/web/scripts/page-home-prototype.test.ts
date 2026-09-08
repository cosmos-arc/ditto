import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium, type Browser } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const prototypePath = resolve(import.meta.dirname, "../prototype/page-home.html");
const navigationTimeoutMs = 10_000;
let browser: Browser;

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-home prototype", () => {
	beforeAll(async () => {
		browser = await chromium.launch({ channel: "chromium" });
	});

	afterAll(async () => {
		await browser.close();
	});

	it("keeps the default-view markup deterministic for visual review screenshots", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#default-view [data-ticker], #default-view [data-counter]")).toHaveLength(0);
	});

	it("keeps hidden queue detail rows renderable when the disclosure opens", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#default-view details .queue-item[data-reveal]")).toHaveLength(0);
	});

	it("keeps the prototype markup free of inline style attributes", () => {
		expect(loadHtml()).not.toMatch(/\sstyle=/);
	});

	it("exposes a dense operating summary across account, risk, work, execution, model, and data", () => {
		const document = loadPage();
		const summary = document.querySelector("[data-operating-summary]");
		const metrics = Array.from(document.querySelectorAll("[data-operating-metric]"));
		const categories = new Set(metrics.map((metric) => metric.getAttribute("data-operating-category")));

		expect(summary).not.toBeNull();
		expect(metrics.length).toBeGreaterThanOrEqual(8);
		expect(categories).toEqual(new Set(["account", "risk", "work", "execution", "model", "data"]));
	});

	it("shows the expected impact before users act on the primary decision", () => {
		const document = loadPage();
		const decisionCard = document.querySelector("[data-command-decision-card]");
		const impactRows = Array.from(document.querySelectorAll("[data-decision-impact] [data-impact-row]"));
		const impactKinds = new Set(impactRows.map((row) => row.getAttribute("data-impact-kind")));

		expect(decisionCard).not.toBeNull();
		expect(impactRows.length).toBeGreaterThanOrEqual(3);
		expect(impactKinds).toEqual(new Set(["concentration", "var", "risk-budget"]));
		expect(impactRows.every((row) => row.querySelector("[data-impact-before]"))).toBe(true);
		expect(impactRows.every((row) => row.querySelector("[data-impact-after]"))).toBe(true);
		expect(document.querySelector("[data-decision-impact]")?.textContent).toContain("VaR");
		expect(document.querySelector("[data-decision-impact]")?.textContent).toContain("科技集中度");
		expect(document.querySelector("[data-decision-impact]")?.textContent).toContain("风险预算");
		expect(document.querySelector("[data-impact-cost]")?.textContent).toContain("冲击成本");
	});

	it("keeps the home priority surface dense enough for expert scanning", () => {
		const document = loadPage();
		const rows = Array.from(document.querySelectorAll("[data-worklist-row]"));
		const p1Rows = rows.filter((row) => row.getAttribute("data-priority") === "P1");

		expect(rows.length).toBeGreaterThanOrEqual(6);
		expect(p1Rows.length).toBeGreaterThanOrEqual(2);
		expect(rows.every((row) => row.querySelector("[data-worklist-level]"))).toBe(true);
		expect(rows.every((row) => row.querySelector("[data-worklist-domain]"))).toBe(true);
		expect(rows.every((row) => row.querySelector("[data-worklist-object]"))).toBe(true);
		expect(rows.every((row) => row.querySelector("[data-worklist-impact]"))).toBe(true);
		expect(rows.every((row) => row.querySelector("[data-worklist-sla]"))).toBe(true);
		expect(rows.every((row) => row.querySelector("[data-worklist-action]"))).toBe(true);
	});

	it("merges activity events and AI insights into one intelligence stream", () => {
		const document = loadPage();
		const stream = document.querySelector("[data-intelligence-stream]");
		const activityEntries = stream?.querySelectorAll('[data-stream-entry="activity"]') ?? [];
		const insightEntries = stream?.querySelectorAll('[data-stream-entry="insight"]') ?? [];

		expect(stream).not.toBeNull();
		expect(activityEntries.length).toBeGreaterThanOrEqual(3);
		expect(insightEntries.length).toBeGreaterThanOrEqual(2);
		expect(document.querySelector('#default-view [data-contract-slot="agent-findings"]')).toBeNull();
	});

	it("keeps the right command-center rail dense with decision constraints", () => {
		const document = loadPage();
		const rail = document.querySelector("[data-command-center-rail]");
		const constraints = document.querySelector('[data-contract-slot="decision-constraints"]');
		const requiredSlots = ["market-pulse", "global-alerts", "decision-constraints", "data-health"];

		expect(rail).not.toBeNull();
		for (const slot of requiredSlots) {
			expect(rail?.querySelector(`[data-contract-slot="${slot}"]`)).not.toBeNull();
		}
		expect(constraints).not.toBeNull();
		expect(constraints?.querySelectorAll("[data-constraint-row]")).toHaveLength(4);
		expect(constraints?.textContent).toContain("下单前约束");
	});

	it(
		"opens the signal detail drawer from the primary decision CTA",
		async () => {
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				await page.click("#default-view .decision-cta.primary");

				const overlayState = await page.evaluate(() => {
					const checkbox = document.querySelector<HTMLInputElement>("#overlay-signal-detail");
					const overlay = document.querySelector<HTMLElement>('[data-overlay="overlay-signal-detail"]');

					return {
						checked: checkbox?.checked ?? false,
						display: overlay ? getComputedStyle(overlay).display : "missing",
					};
				});

				expect(overlayState).toEqual({ checked: true, display: "flex" });
			} finally {
				await page.close();
			}
		},
		15_000,
	);

	it(
		"collapses and expands the right sidebar from the sidebar toggle",
		async () => {
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

			try {
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				await page.click("[data-sidebar-toggle]");
				const collapsed = await page.evaluate(() => {
					const shell = document.querySelector<HTMLElement>("[data-sidebar-shell]");
					const toggle = document.querySelector<HTMLElement>("[data-sidebar-toggle]");
					const collapsedStrip = document.querySelector<HTMLElement>("[data-sidebar-collapsed-strip]");

					return {
						state: shell?.getAttribute("data-sidebar-state"),
						expanded: toggle?.getAttribute("aria-expanded"),
						label: toggle?.getAttribute("aria-label"),
						stripDisplay: collapsedStrip ? getComputedStyle(collapsedStrip).display : "missing",
					};
				});

				expect(collapsed).toEqual({
					state: "collapsed",
					expanded: "false",
					label: "展开侧边栏",
					stripDisplay: "flex",
				});

				await page.click("[data-sidebar-toggle]");
				const expanded = await page.evaluate(() => {
					const shell = document.querySelector<HTMLElement>("[data-sidebar-shell]");
					const toggle = document.querySelector<HTMLElement>("[data-sidebar-toggle]");

					return {
						state: shell?.getAttribute("data-sidebar-state"),
						expanded: toggle?.getAttribute("aria-expanded"),
						label: toggle?.getAttribute("aria-label"),
					};
				});

				expect(expanded).toEqual({
					state: "expanded",
					expanded: "true",
					label: "折叠侧边栏",
				});
			} finally {
				await page.close();
			}
		},
		15_000,
	);

	it(
		"supports direct header theme and density icon toggles",
		async () => {
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(3_000);

			try {
				await page.addInitScript(() => {
					localStorage.removeItem("ditto-theme");
					localStorage.removeItem("ditto-density");
				});
				await page.goto(`file://${prototypePath}`, { waitUntil: "load", timeout: navigationTimeoutMs });

				await page.click("#theme-toggle");
				await page.click("#density-toggle");
				await page.click("#density-toggle");

				const state = await page.evaluate(() => ({
					density: document.documentElement.getAttribute("data-density"),
					themePreference: document.documentElement.getAttribute("data-theme-preference"),
					themeLabel: document.querySelector("#theme-toggle")?.getAttribute("aria-label"),
					densityLabel: document.querySelector("#density-toggle")?.getAttribute("aria-label"),
					hasMenu: Boolean(document.querySelector("[data-view-preferences-menu]")),
				}));

				expect(state).toMatchObject({
					density: "compact",
					themePreference: "light",
					themeLabel: "主题切换 — 当前: 浅色",
					densityLabel: "密度切换 — 当前: 紧凑",
					hasMenu: false,
				});
			} finally {
				await page.close();
			}
		},
		15_000,
	);
});

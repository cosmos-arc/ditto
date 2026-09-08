import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../prototype/page-alpha-explorer.html",
);

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

const prototypeUrl = `file://${prototypePath}`;
const playwrightTestTimeoutMs = 15_000;
const railDomains = ["home", "markets", "research", "trading", "platform"] as const;

describe("page-alpha-explorer prototype", () => {
	it("uses Chinese-first product copy for the default research workspace", () => {
		const document = loadPage();
		const defaultViewText =
			document.querySelector("#default-view")?.textContent ?? "";
		const requiredCopy = [
			"Alpha 探索器",
			"Copilot 探索",
			"研究空间",
			"探索流",
			"帕累托前沿",
			"采纳队列",
			"实验图",
			"候选检查器",
			"证据链",
			"启动探索",
			"确认采纳",
		];
		const demoEnglishCopy = [
			"Alpha Explorer",
			"Copilot Explore",
			"Search Space",
			"Exploration Stream",
			"Pareto Frontier",
			"State Matrix",
			"Adoption Queue",
			"Experiment Graph",
			"Candidate Inspector",
			"Formula & Rationale",
			"Out-of-sample",
			"Sector Exposure",
			"Evidence Chain",
			"Approval Required",
			"Start Run",
			"Pause",
			"Reject",
			"Approve",
			"Evidence",
			"Send",
		];

		for (const copy of requiredCopy) {
			expect(defaultViewText).toContain(copy);
		}
		for (const copy of demoEnglishCopy) {
			expect(defaultViewText).not.toContain(copy);
		}
	});

	it("keeps the alpha workspace in a gate-recognizable studio shell", () => {
		const document = loadPage();
		const shell = document.querySelector("#default-view > .alpha-shell.studio-shell");

		expect(shell).not.toBeNull();
		expect(shell?.querySelector(".shell-rail[data-contract-slot='rail']")).not.toBeNull();
		expect(shell?.querySelector(".alpha-header.shell-header[data-contract-slot='header']")).not.toBeNull();
		expect(shell?.querySelector(".stream-panel[data-contract-slot='main']")).not.toBeNull();
		expect(shell?.querySelector(".inspector[data-contract-slot='inspector']")).not.toBeNull();
		expect(shell?.querySelector(".queue-panel[data-contract-slot='adoption']")).not.toBeNull();
		expect(shell?.querySelector(".graph-panel[data-contract-slot='graph']")).not.toBeNull();
	});

	it("matches active studio pages for rail, header utilities, and primary answer markers", () => {
		const document = loadPage();
		const defaultView = document.querySelector("#default-view");
		const shell = defaultView?.querySelector(".alpha-shell");
		const railItems = Array.from(document.querySelectorAll<HTMLElement>(".shell-rail [data-rail-domain]"));
		const utilities = Array.from(document.querySelectorAll(".shell-header [data-shell-utility]")).map(
			(element) => element.getAttribute("data-shell-utility"),
		);
		const primaryAnswer = document.querySelector("[data-primary-answer]");
		const resizeSeparators = defaultView?.querySelectorAll("[data-resize-separator]");
		const statusBar = defaultView?.querySelector(":scope > .status-bar[data-contract-slot='status']");

		expect(document.querySelectorAll("h1")).toHaveLength(1);
		expect(defaultView?.querySelector(".style-label")?.textContent).toContain("Graphite Studio");
		expect(shell?.getAttribute("data-resizable-panel-group")).toBe("alpha-workbench");
		expect(railItems.map((item) => item.dataset["railDomain"])).toEqual(railDomains);
		expect(railItems.filter((item) => item.getAttribute("aria-current") === "page")).toHaveLength(1);
		expect(document.querySelector(".shell-rail [data-rail-domain='research']")?.getAttribute("aria-current")).toBe(
			"page",
		);
		expect(document.querySelectorAll("[data-header-utility-bar]")).toHaveLength(1);
		expect(utilities).toEqual(["command", "copilot", "notifications", "help", "theme", "density", "account"]);
		expect(document.querySelectorAll(".shell-header [data-shell-utility]:not(button)")).toHaveLength(0);
		expect(primaryAnswer?.querySelectorAll("[data-answer-judgment]").length).toBeGreaterThanOrEqual(1);
		expect(primaryAnswer?.querySelectorAll("[data-answer-metric]").length).toBeGreaterThanOrEqual(1);
		expect(primaryAnswer?.querySelectorAll("[data-answer-evidence]")).toHaveLength(2);
		expect(primaryAnswer?.querySelectorAll("[data-answer-action]").length).toBeGreaterThanOrEqual(1);
		expect(resizeSeparators).toHaveLength(2);
		expect(statusBar?.textContent).toContain("Alpha 探索器");
	});

	it("makes alpha candidate and queue cards keyboard reachable", () => {
		const document = loadPage();
		const controls = document.querySelectorAll(".candidate-card, .queue-item");

		expect(controls.length).toBeGreaterThan(0);
		for (const control of controls) {
			expect(control.getAttribute("tabindex")).toBe("0");
			expect(["button", "option"]).toContain(control.getAttribute("role"));
		}
	});

	it("encodes alpha statuses and focus states beyond color", () => {
		const styleText = loadHtml();

		expect(styleText).toMatch(
			/\.status-pill\.running::before\s*\{[^}]*content:\s*"● "/s,
		);
		expect(styleText).toMatch(
			/\.status-pill\.partial::before\s*\{[^}]*content:\s*"◐ "/s,
		);
		expect(styleText).toMatch(
			/\.status-pill\.blocked::before\s*\{[^}]*content:\s*"✕ "/s,
		);
		expect(styleText).not.toMatch(
			/\.status-pill\.[a-z-]+::before\s*\{[^}]*font-size:\s*\d+px/s,
		);
		expect(styleText).toMatch(
			/\.candidate-card:focus-visible,\s*\.queue-item:focus-visible,\s*\.node:focus-visible,\s*\.point:focus-visible\s*\{[^}]*--interaction-focus-ring/s,
		);
	});

	it("keeps compact sidecar behavior and Pareto decision surface stable", async () => {
		const browser = await chromium.launch({ channel: "chromium" });

		try {
			const compactPage = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			await compactPage.goto(prototypeUrl, { waitUntil: "load" });
			const metrics = await compactPage.evaluate(() => {
				const copilot = document.querySelector<HTMLElement>(".copilot-rail");
				const headerActions = document.querySelector<HTMLElement>(".alpha-header .header-actions");
				if (!copilot || !headerActions) return null;

				const copilotRect = copilot.getBoundingClientRect();
				const actionsRect = headerActions.getBoundingClientRect();
				const style = getComputedStyle(copilot);
				const visible =
					style.display !== "none" &&
					style.visibility !== "hidden" &&
					copilotRect.width > 0 &&
					copilotRect.height > 0;
				const overlaps =
					visible &&
					copilotRect.right > actionsRect.left &&
					copilotRect.left < actionsRect.right &&
					copilotRect.bottom > actionsRect.top &&
					copilotRect.top < actionsRect.bottom;

				return {
					position: style.position,
					overlaps,
				};
			});

			expect(metrics).not.toBeNull();
			expect(metrics?.position).not.toBe("fixed");
			expect(metrics?.overlaps).toBe(false);

			const standardPage = await browser.newPage({ viewport: { width: 1536, height: 1080 } });
			await standardPage.goto(prototypeUrl, { waitUntil: "load" });
			const frontier = await standardPage.$eval(".pareto", (element) => {
				const rect = element.getBoundingClientRect();
				const points = Array.from(element.querySelectorAll<HTMLElement>(".point"));

				return {
					height: Math.round(rect.height),
					width: Math.round(rect.width),
					pointCount: points.length,
					visiblePointCount: points.filter((point) => point.getBoundingClientRect().height > 0).length,
				};
			});

			expect(frontier.height).toBeGreaterThanOrEqual(150);
			expect(frontier.width).toBeGreaterThanOrEqual(420);
			expect(frontier.pointCount).toBe(6);
			expect(frontier.visiblePointCount).toBe(6);

			await standardPage.click("#theme-toggle");
			await standardPage.click("#density-toggle");
			const preferenceState = await standardPage.evaluate(() => ({
				theme: document.documentElement.getAttribute("data-theme"),
				preference: document.documentElement.getAttribute("data-theme-preference"),
				density: document.documentElement.getAttribute("data-density"),
				themeLabel: document.querySelector("#theme-toggle")?.getAttribute("aria-label"),
				densityLabel: document.querySelector("#density-toggle")?.getAttribute("aria-label"),
				hasMenu: Boolean(document.querySelector("[data-view-preferences-menu]")),
			}));

			expect(preferenceState.theme).toBe("light");
			expect(preferenceState.preference).toBe("light");
			expect(preferenceState.density).toBe("comfortable");
			expect(preferenceState.themeLabel).toContain("浅色");
			expect(preferenceState.densityLabel).toContain("宽松");
			expect(preferenceState.hasMenu).toBe(false);
		} finally {
			await browser.close();
		}
	}, playwrightTestTimeoutMs);

	it("switches alpha workspace modes with shared tabs and consistent action typography", async () => {
		const browser = await chromium.launch({ channel: "chromium" });

		try {
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });
			await page.goto(prototypeUrl, { waitUntil: "load" });

			const initialTabs = await page.$$eval(".mode-tabs [role='tab']", (tabs) =>
				tabs.map((tab) => ({
					id: tab.id,
					target: tab.getAttribute("data-tab-target"),
					selected: tab.getAttribute("aria-selected"),
					controls: tab.getAttribute("aria-controls"),
				})),
			);

			expect(initialTabs).toEqual([
				{
					id: "tab-alpha-mode-copilot",
					target: "copilot",
					selected: "true",
					controls: "panel-alpha-mode-copilot",
				},
				{
					id: "tab-alpha-mode-autoresearch",
					target: "autoresearch",
					selected: "false",
					controls: "panel-alpha-mode-autoresearch",
				},
				{
					id: "tab-alpha-mode-factor-lab",
					target: "factor-lab",
					selected: "false",
					controls: "panel-alpha-mode-factor-lab",
				},
			]);

			await page.click("#tab-alpha-mode-autoresearch");
			const autoresearchState = await page.evaluate(() => ({
				selectedTab: document.querySelector(".mode-tabs [aria-selected='true']")?.id,
				copilotHidden: document.querySelector("#panel-alpha-mode-copilot")?.getAttribute("aria-hidden"),
				autoresearchHidden: document.querySelector("#panel-alpha-mode-autoresearch")?.getAttribute("aria-hidden"),
				factorLabHidden: document.querySelector("#panel-alpha-mode-factor-lab")?.getAttribute("aria-hidden"),
				activeText: document.querySelector("#panel-alpha-mode-autoresearch")?.textContent,
			}));

			expect(autoresearchState.selectedTab).toBe("tab-alpha-mode-autoresearch");
			expect(autoresearchState.copilotHidden).toBe("true");
			expect(autoresearchState.autoresearchHidden).toBe("false");
			expect(autoresearchState.factorLabHidden).toBe("true");
			expect(autoresearchState.activeText).toContain("运行路线图");
			expect(autoresearchState.activeText).toContain("来自 Agent 控制台");

			await page.click("#tab-alpha-mode-factor-lab");
			const factorLabState = await page.evaluate(() => ({
				selectedTab: document.querySelector(".mode-tabs [aria-selected='true']")?.id,
				autoresearchHidden: document.querySelector("#panel-alpha-mode-autoresearch")?.getAttribute("aria-hidden"),
				factorLabHidden: document.querySelector("#panel-alpha-mode-factor-lab")?.getAttribute("aria-hidden"),
				activeText: document.querySelector("#panel-alpha-mode-factor-lab")?.textContent,
			}));

			expect(factorLabState.selectedTab).toBe("tab-alpha-mode-factor-lab");
			expect(factorLabState.autoresearchHidden).toBe("true");
			expect(factorLabState.factorLabHidden).toBe("false");
			expect(factorLabState.activeText).toContain("手动诊断");
			expect(factorLabState.activeText).toContain("因子产物");

			const visualContract = await page.evaluate(() => {
				const panelKicker = document.querySelector<HTMLElement>(".panel-kicker");
				const statusBar = document.querySelector<HTMLElement>(".status-bar");
				const miniValue = document.querySelector<HTMLElement>(".mini-value");

				return {
					legacyPrimaryButtonCount: document.querySelectorAll(".btn.primary").length,
					sharedPrimaryButtonCount: document.querySelectorAll(".btn.btn-primary").length,
					panelKickerFamily: panelKicker ? getComputedStyle(panelKicker).fontFamily : "",
					statusBarFamily: statusBar ? getComputedStyle(statusBar).fontFamily : "",
					miniValueFamily: miniValue ? getComputedStyle(miniValue).fontFamily : "",
				};
			});

			expect(visualContract.legacyPrimaryButtonCount).toBe(0);
			expect(visualContract.sharedPrimaryButtonCount).toBeGreaterThanOrEqual(4);
			expect(visualContract.panelKickerFamily).not.toContain("JetBrains Mono");
			expect(visualContract.statusBarFamily).not.toContain("JetBrains Mono");
			expect(visualContract.miniValueFamily).toContain("JetBrains Mono");
		} finally {
			await browser.close();
		}
	}, playwrightTestTimeoutMs);

	it("preserves state and overlay coverage without inline styles or duplicate ids", () => {
		const document = loadPage();
		const ids = Array.from(document.querySelectorAll("[id]")).map((element) => element.id);
		const uniqueIds = new Set(ids);

		expect(document.querySelectorAll("#states-gallery .gallery-card").length).toBeGreaterThanOrEqual(12);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(6);
		expect(document.querySelectorAll("[style]")).toHaveLength(0);
		expect(uniqueIds.size).toBe(ids.length);
	});
});

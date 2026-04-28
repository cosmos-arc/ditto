import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-ai-copilot.html",
);
const prototypeUrl = `file://${prototypePath}`;

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-ai-copilot prototype", () => {
	it("uses a gate-recognizable studio shell with explicit contract regions", () => {
		const document = loadPage();
		const shell = document.querySelector("#default-view > .shell-copilot.shell-studio");

		expect(shell).not.toBeNull();
		expect(shell?.querySelector(".shell-rail[data-contract-slot='rail']")).not.toBeNull();
		expect(shell?.querySelector(".shell-header[data-contract-slot='header']")).not.toBeNull();
		expect(shell?.querySelector(".copilot-sessions[data-contract-slot='sessions']")).not.toBeNull();
		expect(shell?.querySelector(".copilot-conversation[data-contract-slot='main']")).not.toBeNull();
		expect(shell?.querySelector(".copilot-context[data-contract-slot='sidebar']")).not.toBeNull();
	});

	it("lets the mode radio state drive active styling instead of a stale static active class", () => {
		const document = loadPage();
		const tabs = Array.from(document.querySelectorAll("#default-view .mode-tab"));

		expect(tabs).toHaveLength(4);
		expect(tabs.every((tab) => !tab.classList.contains("active"))).toBe(true);
		expect(document.querySelector("#copilot-market-analysis:checked")).not.toBeNull();
	});

	it("keeps all prototype markup free of inline style attributes", () => {
		expect(loadHtml()).not.toMatch(/\sstyle=/);
	});

	it(
		"switches first-row copilot modes with visible mode-specific context",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });
			page.setDefaultTimeout(2_000);

			const modes = [
				{
					id: "copilot-market-analysis",
					expectedText: "市场结构",
				},
				{
					id: "copilot-stock-discovery",
					expectedText: "个股发现",
				},
				{
					id: "copilot-strategy-draft",
					expectedText: "策略草案",
				},
				{
					id: "copilot-factor-discovery",
					expectedText: "因子发现",
				},
			];

			try {
				await page.goto(prototypeUrl, { waitUntil: "load" });

				for (const mode of modes) {
					await page.locator(`label[for='${mode.id}']`).click();
					await expectModeState(page, mode.id, mode.expectedText);
				}
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"supports conversation tabs, overlays, and prototype zones at runtime",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(prototypeUrl, { waitUntil: "load" });

				await page.click("[data-tab-target='analysis']");
				await expectTabState(page, "analysis", "分析推理时间线");

				await page.click("[data-tab-target='recommendations']");
				await expectTabState(page, "recommendations", "推荐结论");

				await page.locator("label[for='overlay-session-template']").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-session-template']", true);
				await page.locator("[data-overlay='overlay-session-template'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-session-template']", false);

				await page.locator(".action-card").first().click();
				await expectCssVisible(page, "[data-overlay='overlay-send-workspace']", true);
				await page.locator("[data-overlay='overlay-send-workspace'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-send-workspace']", false);

				await page.locator(".action-card").last().click();
				await expectCssVisible(page, "[data-overlay='overlay-save-conclusion']", true);
				await page.locator("[data-overlay='overlay-save-conclusion'] .overlay-close").click();
				await expectCssVisible(page, "[data-overlay='overlay-save-conclusion']", false);

				await checkRadio(page, "view-states");
				await expectCssVisible(page, "#states-gallery", true);
				await expectCssVisible(page, "#default-view", false);

				await checkRadio(page, "view-overlays");
				await expectCssVisible(page, "#overlays-gallery", true);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);

	it(
		"keeps the compact status bar in document flow without covering shell content",
		async () => {
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
			page.setDefaultTimeout(2_000);

			try {
				await page.goto(prototypeUrl, { waitUntil: "load" });

				const geometry = await page.evaluate(() => {
					const statusBar = document.querySelector(".status-bar");
					const shell = document.querySelector(".shell-copilot");

					if (!(statusBar instanceof HTMLElement) || !(shell instanceof HTMLElement)) {
						return { hasRequiredRegions: false };
					}

					const statusRect = statusBar.getBoundingClientRect();
					const shellRect = shell.getBoundingClientRect();

					return {
						hasRequiredRegions: true,
						position: getComputedStyle(statusBar).position,
						shellBottom: Math.round(shellRect.bottom),
						statusTop: Math.round(statusRect.top),
						statusBottom: Math.round(statusRect.bottom),
						viewportBottom: window.innerHeight,
					};
				});

				expect(geometry).toMatchObject({ hasRequiredRegions: true });
				if (!("position" in geometry)) {
					throw new Error("compact geometry did not include status data");
				}
				expect(geometry.position).toBe("static");
				expect(geometry.shellBottom).toBeLessThanOrEqual(geometry.statusTop);
				expect(geometry.statusBottom).toBeLessThanOrEqual(geometry.viewportBottom);
			} finally {
				await browser.close();
			}
		},
		15_000,
	);
});

async function expectCssVisible(page: import("playwright").Page, selector: string, visible: boolean) {
	const isVisible = await page.locator(selector).first().evaluate((element) => {
		const style = getComputedStyle(element);
		const rect = element.getBoundingClientRect();

		return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
	});

	expect(isVisible).toBe(visible);
}

async function expectTabState(page: import("playwright").Page, panel: string, expectedText: string) {
	const state = await page.locator("[data-tabs='copilot-tabs']").evaluate((element, expectedPanel) => {
		const activeButton = element.querySelector("[data-tab-target].active");
		const visiblePanel = Array.from(element.querySelectorAll<HTMLElement>("[data-tab-panel]")).find((candidate) => {
			const style = getComputedStyle(candidate);
			return style.display !== "none" && candidate.getAttribute("aria-hidden") !== "true";
		});

		return {
			active: activeButton?.getAttribute("data-tab-target") ?? "",
			selected: activeButton?.getAttribute("aria-selected") ?? "",
			visiblePanel: visiblePanel?.getAttribute("data-tab-panel") ?? "",
			text: visiblePanel?.textContent ?? "",
			expectedPanel,
		};
	}, panel);

	expect(state.active).toBe(panel);
	expect(state.selected).toBe("true");
	expect(state.visiblePanel).toBe(panel);
	expect(state.text).toContain(expectedText);
}

async function expectModeState(page: import("playwright").Page, id: string, expectedText: string) {
	const state = await page.evaluate((mode) => {
		const input = document.getElementById(mode.id);
		const panel = document.querySelector<HTMLElement>(`[data-panel="${mode.id}"]`);

		if (!(input instanceof HTMLInputElement)) {
			return { hasInput: false };
		}

		if (!panel) {
			return {
				hasInput: true,
				checked: input.checked,
				hasPanel: false,
			};
		}

		const style = getComputedStyle(panel);
		const rect = panel.getBoundingClientRect();

		return {
			hasInput: true,
			checked: input.checked,
			hasPanel: true,
			visible: style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0,
			text: panel.textContent ?? "",
		};
	}, { id, expectedText });

	expect(state).toMatchObject({ hasInput: true, checked: true, hasPanel: true, visible: true });
	if (!("text" in state)) {
		throw new Error(`Mode panel did not expose text: ${id}`);
	}
	expect(state.text).toContain(expectedText);
}

async function checkRadio(page: import("playwright").Page, id: string) {
	await page.evaluate((radioId) => {
		const input = document.getElementById(radioId);

		if (!(input instanceof HTMLInputElement)) {
			throw new Error(`Radio not found: ${radioId}`);
		}

		input.checked = true;
		input.dispatchEvent(new Event("change", { bubbles: true }));
	}, id);
}

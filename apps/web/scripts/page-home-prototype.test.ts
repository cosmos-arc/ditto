import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium, type Browser } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const prototypePath = resolve(import.meta.dirname, "../docs/designs/specs/prototypes/page-home.html");
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

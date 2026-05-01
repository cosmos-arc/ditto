import { resolve } from "node:path";
import { chromium, type Browser } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const navigationTimeoutMs = 10_000;
let browser: Browser;

function prototypeUrl(file: string): string {
	return `file://${resolve(import.meta.dirname, "../docs/designs/specs/prototypes", file)}`;
}

describe("prototype primary answer actions", () => {
	beforeAll(async () => {
		browser = await chromium.launch({ channel: "chromium" });
	});

	afterAll(async () => {
		await browser.close();
	});

	it(
		"opens the Research run queue drilldown from the primary answer action",
		async () => {
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

			try {
				await page.goto(prototypeUrl("page-research.html"), { waitUntil: "load", timeout: navigationTimeoutMs });
				await page.click('[data-answer-action][data-action-target="tab-backtest"]');

				const state = await page.evaluate(() => {
					const tab = document.querySelector<HTMLElement>("#tab-backtest");
					const panel = document.querySelector<HTMLElement>("#panel-backtest");

					return {
						selected: tab?.getAttribute("aria-selected"),
						hidden: panel?.getAttribute("aria-hidden"),
						display: panel ? getComputedStyle(panel).display : "missing",
					};
				});

				expect(state).toMatchObject({ selected: "true", hidden: "false" });
				expect(state.display).not.toBe("none");
			} finally {
				await page.close();
			}
		},
		15_000,
	);

	it(
		"opens the Portfolio attribution drilldown from the primary answer action",
		async () => {
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

			try {
				await page.goto(prototypeUrl("page-portfolio.html"), { waitUntil: "load", timeout: navigationTimeoutMs });
				await page.click('[data-answer-action][for="tab-attribution"]');

				const state = await page.evaluate(() => {
					const radio = document.querySelector<HTMLInputElement>("#tab-attribution");
					const panel = document.querySelector<HTMLElement>("#panel-attribution");

					return {
						checked: radio?.checked ?? false,
						hidden: panel?.getAttribute("aria-hidden"),
						display: panel ? getComputedStyle(panel).display : "missing",
					};
				});

				expect(state).toMatchObject({ checked: true });
				expect(state.display).not.toBe("none");
			} finally {
				await page.close();
			}
		},
		15_000,
	);
});

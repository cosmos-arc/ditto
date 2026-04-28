import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(import.meta.dirname, "../docs/designs/specs/prototypes/page-home.html");

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-home prototype", () => {
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
			const browser = await chromium.launch({ channel: "chromium" });
			const page = await browser.newPage({ viewport: { width: 1536, height: 1080 } });

			try {
				await page.goto(`file://${prototypePath}`);
				await page.waitForLoadState("load");

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
				await browser.close();
			}
		},
		15_000,
	);
});

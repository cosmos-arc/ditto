import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { chromium } from "playwright";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-instrument-hub.html",
);
const layoutCssPath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/shared/layout-shell.css",
);
const prototypeUrl = `file://${prototypePath}`;
const navigationTimeoutMs = 10_000;
function loadPage() {
	return new JSDOM(readFileSync(prototypePath, "utf-8")).window.document;
}

describe("page-instrument-hub prototype", () => {
	it("uses the relaxed Object Hub header rhythm shared by detail pages", () => {
		const layoutCss = readFileSync(layoutCssPath, "utf-8");

		expect(layoutCss).toMatch(/\.shell-hub\s*\{[^}]*--shell-header-height:\s*76px;/s);
		expect(layoutCss).toMatch(/\.shell-hub\s+\.shell-header\s*\{[^}]*padding-inline:/s);
	});

	it("keeps the bottom timeline as a compact horizontal digest in constrained viewports", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load", timeout: navigationTimeoutMs });

			const timeline = await page.evaluate(() => {
				const content = document.querySelector<HTMLElement>(".hub-bottom [data-panel='bottom-events']");
				const list = content?.querySelector<HTMLElement>(".timeline-list");
				const first = list?.querySelector<HTMLElement>(".timeline-item");
				const second = list?.querySelectorAll<HTMLElement>(".timeline-item")[1];
				if (!content || !list || !first || !second) return null;

				const contentRect = content.getBoundingClientRect();
				const firstRect = first.getBoundingClientRect();
				const secondRect = second.getBoundingClientRect();
				const listStyle = getComputedStyle(list);

				return {
					display: listStyle.display,
					columns: listStyle.gridTemplateColumns.split(" ").length,
					contentHeight: Math.round(contentRect.height),
					sameRow: Math.abs(Math.round(firstRect.top - secondRect.top)) <= 1,
				};
			});

			expect(timeline).toMatchObject({
				display: "grid",
				columns: 3,
				sameRow: true,
			});
			expect(timeline?.contentHeight).toBeLessThanOrEqual(104);
		} finally {
			await browser.close();
		}
	}, 15_000);

	it("keeps the instrument identity fully inside the relaxed header frame", async () => {
		const browser = await chromium.launch({ channel: "chromium" });
		const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });

		try {
			await page.goto(prototypeUrl, { waitUntil: "load", timeout: navigationTimeoutMs });

			const header = await page.evaluate(() => {
				const shellHeader = document.querySelector<HTMLElement>(".shell-header");
				const objectHeader = document.querySelector<HTMLElement>(".object-header");
				if (!shellHeader || !objectHeader) return null;

				const shellRect = shellHeader.getBoundingClientRect();
				const objectRect = objectHeader.getBoundingClientRect();

				return {
					shellTop: Math.round(shellRect.top),
					shellBottom: Math.round(shellRect.bottom),
					shellHeight: Math.round(shellRect.height),
					objectTop: Math.round(objectRect.top),
					objectBottom: Math.round(objectRect.bottom),
					objectHeight: Math.round(objectRect.height),
					headerScrollHeight: shellHeader.scrollHeight,
					headerClientHeight: shellHeader.clientHeight,
				};
			});

			expect(header).not.toBeNull();
			if (!header) return;
			expect(header.objectTop).toBeGreaterThanOrEqual(header.shellTop);
			expect(header.objectBottom).toBeLessThanOrEqual(header.shellBottom + 1);
			expect(header.objectHeight).toBeLessThanOrEqual(header.shellHeight);
			expect(header.headerScrollHeight).toBeLessThanOrEqual(header.headerClientHeight + 1);
		} finally {
			await browser.close();
		}
	}, 15_000);

	it("lets the right sidebar own the bottom-right height instead of wasting it on the timeline bar", () => {
		const document = loadPage();
		const html = readFileSync(prototypePath, "utf-8");
		const layoutCss = readFileSync(layoutCssPath, "utf-8");

		expect(document.querySelector(".object-shell > .hub-sidebar")).not.toBeNull();
		expect(document.querySelector(".object-shell.shell-hub--with-sidebar")).not.toBeNull();
		expect(layoutCss).toMatch(
			/\.shell-hub--with-sidebar\s*\{[\s\S]*--shell-hub-grid-areas:[\s\S]*"rail main\s+sidebar"[\s\S]*"rail bottom\s+sidebar"/,
		);
		expect(html).toMatch(/\.hub-sidebar\s*\{[^}]*grid-area:\s*sidebar;/s);
	});

	it("keeps all prototype markup free of inline style attributes", () => {
		const document = loadPage();

		expect(readFileSync(prototypePath, "utf-8")).not.toMatch(/\sstyle=/);
		expect(document.querySelector("#default-view > .object-shell.shell-hub")).not.toBeNull();
		expect(document.querySelector(".object-shell > .hub-sidebar")).not.toBeNull();
	});
});

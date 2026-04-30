import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-instrument-hub.html",
);
const layoutCssPath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/shared/layout-base.css",
);
function loadPage() {
	return new JSDOM(readFileSync(prototypePath, "utf-8")).window.document;
}

describe("page-instrument-hub prototype", () => {
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

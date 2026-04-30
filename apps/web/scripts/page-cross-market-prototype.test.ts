import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-cross-market.html",
);
function loadPage() {
	return new JSDOM(readFileSync(prototypePath, "utf-8")).window.document;
}

describe("page-cross-market prototype", () => {
	it("keeps the sticky scope leader readable as a distinct chip while scrolling", () => {
		const document = loadPage();
		const html = readFileSync(prototypePath, "utf-8");

		expect(document.querySelector(".scope-strip .scope-strip-item--lead")).not.toBeNull();
		expect(html).toMatch(/\.scope-strip\s*\{[^}]*box-shadow:/s);
		expect(html).toMatch(/\.scope-strip\s+\.scope-strip-item--lead\s*\{[^}]*background:/s);
		expect(html).toMatch(/\.scope-strip\s+\.scope-strip-item--lead\s*\{[^}]*border:/s);
	});

	it("keeps all prototype markup free of inline style attributes", () => {
		expect(readFileSync(prototypePath, "utf-8")).not.toMatch(/\sstyle=/);
		expect(loadPage().querySelector("#default-view > .shell-radar")).not.toBeNull();
	});
});

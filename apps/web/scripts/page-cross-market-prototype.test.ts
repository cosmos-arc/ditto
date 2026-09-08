import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../prototype/page-cross-market.html",
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
		expect(html).toMatch(/\.scope-strip\s+\.scope-strip-item--lead\s+\.context-bar-label\s*\{[^}]*border-right:/s);
		expect(html).toMatch(/\.scope-strip\s+\.scope-strip-item--lead\s+\.context-bar-value\s*\{[^}]*max-width:/s);
	});

	it("uses a non-modal pin state for fixed viewpoint instead of blocking the market workspace", () => {
		const document = loadPage();
		const html = readFileSync(prototypePath, "utf-8");

		expect(document.querySelector("#default-view [data-pin-viewpoint-status]")).not.toBeNull();
		expect(document.querySelector("#default-view [data-overlay='overlay-pin-viewpoint']")).toBeNull();
		expect(html).toMatch(/:root:has\(#overlay-pin-viewpoint:checked\)\s+\.pin-viewpoint-trigger/s);
		expect(html).toMatch(/\.pin-viewpoint-status\s*\{[^}]*display:\s*none;/s);
	});

	it("keeps all prototype markup free of inline style attributes", () => {
		expect(readFileSync(prototypePath, "utf-8")).not.toMatch(/\sstyle=/);
		expect(loadPage().querySelector("#default-view > .shell-radar")).not.toBeNull();
	});
});

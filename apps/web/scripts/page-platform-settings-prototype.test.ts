import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-platform-settings.html",
);

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

describe("page-platform-settings prototype", () => {
	it("uses a gate-recognizable ops shell with config console regions", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-ops")).not.toBeNull();
		expect(document.querySelector("#default-view .skip-link")).not.toBeNull();
		expect(loadHtml()).toContain("left: -9999px");
		expect(document.querySelector(".shell-rail")).not.toBeNull();
		expect(document.querySelector(".shell-header[data-contract-slot='header']")).not.toBeNull();
		expect(document.querySelector(".ops-health[data-contract-slot='health']")).not.toBeNull();
		expect(document.querySelector(".ops-main[data-contract-slot='main']")).not.toBeNull();
		expect(document.querySelector(".ops-detail[data-contract-slot='inspector']")).not.toBeNull();
	});

	it("keeps every settings tab validation-ready with editor, test, log, and diff evidence", () => {
		const document = loadPage();
		const tabPanels = Array.from(document.querySelectorAll("#default-view .tab-panel"));

		expect(tabPanels).toHaveLength(3);
		for (const panel of tabPanels) {
			expect(panel.querySelector(".config-workspace")).not.toBeNull();
			expect(panel.querySelector("[data-config-list]")).not.toBeNull();
			expect(panel.querySelector("[data-config-editor]")).not.toBeNull();
			expect(panel.querySelector("[data-validation-evidence]")).not.toBeNull();
		}

		expect(document.querySelector("[data-inspector-test-result]")).not.toBeNull();
		expect(document.querySelectorAll("[data-log-row]").length).toBeGreaterThanOrEqual(5);
		expect(document.querySelectorAll("[data-config-diff-row]").length).toBeGreaterThanOrEqual(4);
	});

	it("covers the declared settings states and overlays", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#states-gallery [data-component='datasource-list'] .gallery-card")).toHaveLength(5);
		expect(document.querySelectorAll("#states-gallery [data-component='broker-list'] .gallery-card")).toHaveLength(5);
		expect(document.querySelectorAll("#states-gallery [data-component='settings-form'] .gallery-card")).toHaveLength(2);
		expect(document.querySelectorAll("#overlays-gallery .gallery-card")).toHaveLength(3);
		expect(document.querySelector("#overlay-datasource-test")).not.toBeNull();
		expect(document.querySelector("#overlay-broker-test")).not.toBeNull();
		expect(document.querySelector("#overlay-reset-config")).not.toBeNull();
	});

	it("keeps prototype markup free of inline style attributes and TypeScript bypasses", () => {
		const html = loadHtml();

		expect(html).not.toMatch(/\sstyle=/);
		expect(html).not.toMatch(/@ts-ignore|@ts-expect-error|\bany\b/);
	});
});

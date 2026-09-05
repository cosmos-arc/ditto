import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../docs/designs/specs/prototypes/page-factor-analysis.html",
);
function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}
describe("page-factor-analysis prototype", () => {
	it("inherits the relaxed Object Hub header rhythm shared by detail pages", () => {
		const layoutCss = readFileSync(
			resolve(import.meta.dirname, "../docs/designs/specs/prototypes/shared/layout-shell.css"),
			"utf-8",
		);

		expect(layoutCss).toMatch(/\.shell-hub\s*\{[^}]*--shell-header-height:\s*76px;/s);
		expect(layoutCss).toMatch(/\.shell-hub\s+\.shell-header\s*\{[^}]*padding-inline:/s);
	});

	it("uses the gate-recognizable Object Hub shell with complete research rail navigation", () => {
		const document = loadPage();
		const shell = document.querySelector("#default-view > .object-shell.shell-hub");
		const railNav = shell?.querySelector(".shell-rail .rail-nav");

		expect(shell).not.toBeNull();
		expect(shell?.querySelector(".shell-rail")).not.toBeNull();
		expect(shell?.querySelector(".shell-header")).not.toBeNull();
		expect(shell?.querySelector(".hub-meta")).not.toBeNull();
		expect(shell?.querySelector(".tab-group")).not.toBeNull();
		expect(shell?.querySelector(".hub-bottom")).not.toBeNull();
		expect(railNav?.querySelectorAll(":scope > .rail-icon")).toHaveLength(5);
	});

	it("places contract slots on visible main and sidebar regions rather than display-contents wrappers", () => {
		const document = loadPage();
		const tabPanels = document.querySelector("#default-view .tab-panels");
		const mainRegions = document.querySelectorAll("#default-view .tab-panel .hub-main");
		const sidebarRegions = document.querySelectorAll("#default-view .tab-panel .hub-sidebar");

		expect(tabPanels?.hasAttribute("data-contract-slot")).toBe(false);
		expect(mainRegions).toHaveLength(4);
		expect(sidebarRegions).toHaveLength(4);

		for (const region of mainRegions) {
			expect(region.getAttribute("data-contract-slot")).toBe("main");
		}
		for (const region of sidebarRegions) {
			expect(region.getAttribute("data-contract-slot")).toBe("sidebar");
		}
	});

	it("provides real default-view overlays for every header action", () => {
		const document = loadPage();
		const overlayIds = [
			"overlay-add-backtest",
			"overlay-add-experiment",
			"overlay-ai-analysis",
			"overlay-diagnostic-detail",
		];

		for (const overlayId of overlayIds) {
			expect(document.querySelector(`#${overlayId}`)).not.toBeNull();
			expect(document.querySelector(`#default-view [data-overlay="${overlayId}"]`)).not.toBeNull();
		}
	});

	it("keeps visual review screenshots deterministic and tokenized", () => {
		const document = loadPage();
		const defaultView = document.querySelector("#default-view");
		const html = loadHtml();

		expect(defaultView).not.toBeNull();
		expect(defaultView?.querySelectorAll("[data-ticker], [data-counter]")).toHaveLength(0);
		expect(html).not.toMatch(/\sstyle="/);
		expect(html).not.toMatch(/\sfont-size="/);
	});

	it("wires header overlays through default-view controls and CSS activation rules", () => {
		const document = loadPage();
		const html = loadHtml();

		for (const overlayId of ["overlay-add-backtest", "overlay-add-experiment", "overlay-ai-analysis"]) {
			expect(document.querySelector(`#${overlayId}`)).not.toBeNull();
			expect(document.querySelector(`#default-view label[for="${overlayId}"]`)).not.toBeNull();
			expect(
				document.querySelector(`#default-view [data-overlay="${overlayId}"] .overlay-close[for="${overlayId}"]`),
			).not.toBeNull();
			expect(html).toMatch(
				new RegExp(
					`:root:has\\(#${overlayId}:checked\\)\\s*\\[data-overlay="${overlayId}"\\]\\s*\\{\\s*display:\\s*flex;\\s*\\}`,
				),
			);
		}
	});

	it("keeps compact IC diagnostics readable without hiding the statistics rows", () => {
		const document = loadPage();
		const html = loadHtml();
		const summaryPanel = Array.from(document.querySelectorAll("[data-panel='fact-ic'] .panel"))
			.find((panel) => panel.querySelector(".panel-title")?.textContent?.includes("统计摘要"));

		expect(summaryPanel?.querySelectorAll(".stats-row")).toHaveLength(3);
		expect(html).toMatch(/@media\s*\(max-height:\s*820px\)\s*\{[\s\S]*\.context-strip\s*\{\s*display:\s*none;/);
		expect(html).toMatch(
			/@media\s*\(max-height:\s*820px\)\s*\{[\s\S]*\.panel-body\s*\{\s*padding:\s*var\(--space-8\)\s+var\(--space-10\);/,
		);
		expect(html).toMatch(
			/@media\s*\(max-height:\s*820px\)\s*\{[\s\S]*\.stats-row\s*\{\s*padding:\s*var\(--space-6\)\s+0;/,
		);
	});
});

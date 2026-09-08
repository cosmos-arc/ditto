import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../prototype/page-markets-intelligence.html",
);

function loadPage() {
	const html = readFileSync(prototypePath, "utf-8");
	return new JSDOM(html).window.document;
}

function elementText(root: Element | null, selector: string) {
	return root?.querySelector(selector)?.textContent ?? "";
}

describe("page-markets-intelligence prototype", () => {
	it("uses a gate-recognizable analytical shell with bounded analysis and right rail slots", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .intel-shell.shell-intel")).not.toBeNull();
		expect(document.querySelector(".intel-right-rail[data-contract-slot='right-rail']")).not.toBeNull();
		expect(document.querySelector(".analysis-band[data-contract-slot='analysis']")).not.toBeNull();
		expect(document.querySelectorAll(".analysis-band .analysis-band-section")).toHaveLength(3);
		expect(elementText(document.body, ".analysis-band")).toContain("行动窗口");
	});

	it("documents heatmap size, color, scope, and range semantics for fast scan reading", () => {
		const document = loadPage();
		const heatmap = document.querySelector(".heatmap-intel-card");

		expect(heatmap).not.toBeNull();
		expect(elementText(heatmap, "[data-heatmap-size]")).toContain("成交额权重");
		expect(elementText(heatmap, "[data-heatmap-color]")).toContain("净流入强度");
		expect(elementText(heatmap, "[data-heatmap-scope]")).toContain("申万一级");
		expect(heatmap?.querySelectorAll(".heatmap-legend-stop")).toHaveLength(5);
		expect(elementText(heatmap, ".heatmap-reading-hint")).toContain("红绿深浅");
	});

	it("keeps sector flow rows direction-aware without relying on color alone", () => {
		const document = loadPage();
		const rows = Array.from(document.querySelectorAll(".flow-sector-row"));

		expect(rows).toHaveLength(10);
		for (const row of rows) {
			expect(row.getAttribute("data-flow-direction")).toMatch(/^(up|down|flat)$/);
			expect(row.querySelector(".direction-symbol")?.textContent).toMatch(/[▲▼•]/);
		}
	});

	it("keeps default-view numeric values deterministic for visual review screenshots", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#default-view [data-ticker], #default-view [data-counter]")).toHaveLength(
			0,
		);
	});
});

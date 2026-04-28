import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(import.meta.dirname, "../docs/designs/specs/prototypes/page-a-shares.html");

function loadPage() {
	const html = readFileSync(prototypePath, "utf-8");
	return new JSDOM(html).window.document;
}

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function elementText(root: Element | null, selector: string) {
	return root?.querySelector(selector)?.textContent ?? "";
}

describe("page-a-shares market structure map", () => {
	it("documents size, color, grouping, and interaction semantics for professional map reading", () => {
		const document = loadPage();
		const map = document.querySelector(".map-container");

		expect(map).not.toBeNull();
		expect(elementText(map, "[data-map-size]")).toContain("成交额");
		expect(elementText(map, "[data-map-color]")).toContain("涨跌幅");
		expect(elementText(map, "[data-map-grouping]")).toContain("申万");
		expect(map?.querySelectorAll(".map-legend-scale .map-legend-stop")).toHaveLength(5);
		expect(elementText(map, ".map-interaction-hint")).toContain("点击");
	});

	it("keeps treemap and heatmap cells grouped, direction-aware, and keyboard reachable", () => {
		const document = loadPage();
		const treemapCells = document.querySelectorAll(".treemap-cell-iv");
		const heatmapCells = document.querySelectorAll(".heatmap-cell");

		expect(treemapCells.length).toBeGreaterThanOrEqual(16);
		expect(heatmapCells.length).toBeGreaterThanOrEqual(32);
		expect(document.querySelectorAll(".treemap-group-label")).toHaveLength(4);

		for (const cell of [...treemapCells, ...heatmapCells]) {
			expect(cell.getAttribute("tabindex")).toBe("0");
			expect(cell.getAttribute("data-direction")).toMatch(/^(up|down|flat)$/);
			expect(cell.getAttribute("data-sector-family")).toMatch(/^(growth|cyclical|defensive|financial)$/);
		}
	});

	it("renders industry-map density with nested constituents instead of flat sector cards", () => {
		const document = loadPage();
		const treemap = document.querySelector(".treemap");

		expect(treemap?.querySelectorAll(".map-stock-chip").length).toBeGreaterThanOrEqual(40);
		expect(treemap?.querySelectorAll(".map-stock-chip[data-direction='up']").length).toBeGreaterThan(20);
		expect(treemap?.querySelectorAll(".map-stock-chip[data-direction='down']").length).toBeGreaterThan(8);
		expect(treemap?.querySelectorAll(".map-sector-boundary")).toHaveLength(4);
	});

	it("uses a restrained red-green stepped heat palette instead of bright accent glows", () => {
		const document = loadPage();
		const html = loadHtml();
		const mapCells = document.querySelectorAll(".treemap-cell-iv, .heatmap-cell");

		for (const step of [1, 2, 3, 4]) {
			expect(html).toContain(`--heat-up-${step}`);
			expect(html).toContain(`--heat-down-${step}`);
		}

		expect(html).toContain("--heat-flat");
		expect(html).toContain("oklch(from var(--market-up-fg)");
		expect(html).toContain("oklch(from var(--market-down-fg)");
		expect(html).not.toContain("--direction-glow");
		expect(html).not.toContain("--family-edge");
		expect(html).not.toMatch(/radial-gradient\(circle[^;]+--market-(up|down)-fg/s);

		for (const cell of mapCells) {
			expect(cell.getAttribute("data-heat")).toMatch(/^(up|down)-[1-4]$|^flat$/);
		}
	});
});

describe("page-a-shares visual system alignment", () => {
	it("keeps the page in the restrained Graphite Studio workbench language", () => {
		const document = loadPage();
		const html = loadHtml();
		const revealDelays = [...document.querySelectorAll("[data-reveal-delay]")]
			.map((element) => Number(element.getAttribute("data-reveal-delay")))
			.filter(Number.isFinite);
		const maxRevealDelay = revealDelays.length === 0 ? 0 : Math.max(...revealDelays);

		expect(document.querySelector(".shell-radar")).not.toBeNull();
		expect(html).not.toContain('data-mouse-glow="true"');
		expect(html).not.toContain(".shell-radar::before");
		expect(html).not.toContain(".shell-radar::after");
		expect(html).not.toContain(".shell-radar .shell-header::after");
		expect(html).not.toContain(".panel::before");
		expect(html).not.toContain(".right-rail::before");
		expect(html).not.toContain("radial-gradient(ellipse");
		expect(html).toContain("contain: paint;");
		expect(maxRevealDelay).toBeLessThanOrEqual(240);
	});
});

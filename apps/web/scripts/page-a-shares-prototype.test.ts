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
	it("models a T0 market-map workbench with explicit modes, metrics, and accessible cells", () => {
		const document = loadPage();
		const map = document.querySelector(".map-container");
		const modeLabels = [...document.querySelectorAll("[data-map-mode-option]")].map((label) =>
			label.textContent?.trim(),
		);
		const mapCells = document.querySelectorAll(".treemap-cell-iv, .heatmap-cell");

		expect(map?.getAttribute("data-map-quality")).toBe("t0-market-map");
		expect(map?.querySelector("[data-map-mode='sector-treemap']")).not.toBeNull();
		expect(map?.querySelector("[data-map-mode='stock-heatmap']")).not.toBeNull();
		expect(modeLabels).toEqual(["行业矩阵", "个股热区"]);
		expect(elementText(map, "[data-map-breadcrumb]")).toContain("A股");
		expect(elementText(map, "[data-map-selected-summary]")).toContain("电子");
		expect(elementText(map, "[data-map-metric-switcher]")).toContain("Size");
		expect(map?.querySelector("[data-size-legend]")).not.toBeNull();
		expect(map?.querySelector("[data-color-legend]")).not.toBeNull();
		expect(elementText(map, "[data-map-threshold='negative-extreme']")).toContain("≤ -5%");
		expect(elementText(map, "[data-map-threshold='neutral']")).toContain("0");
		expect(elementText(map, "[data-map-threshold='positive-extreme']")).toContain("≥ +5%");

		for (const cell of mapCells) {
			expect(cell.getAttribute("data-size-metric")).toBeTruthy();
			expect(cell.getAttribute("data-color-metric")).toBe("change-pct");
			expect(cell.getAttribute("aria-label")).toMatch(/(涨幅|跌幅|涨跌幅|成交额|占比|行业)/);
		}
	});

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

	it("makes A-share map color semantics explicit instead of relying on perceived purple-cyan tint", () => {
		const document = loadPage();
		const html = loadHtml();
		const map = document.querySelector(".map-container");

		expect(elementText(map, "[data-map-color]")).toContain("涨跌幅");
		expect(elementText(map, "[data-map-color]")).toContain("A股：红涨绿跌");
		expect(elementText(map, "[data-map-metric-switcher]")).toContain("行业 Size 成交额占比");
		expect(elementText(map, "[data-map-metric-switcher]")).toContain("个股 Size 成交额");
		expect(elementText(map, "[data-map-metric-switcher]")).toContain("Color 涨跌幅");
		expect(elementText(map, "[data-map-breadcrumb]")).toContain("申万一级");
		expect(html).toContain("--map-market-up-1");
		expect(html).toContain("--map-market-down-1");
		expect(html).not.toContain("--map-positive-1");
		expect(html).not.toContain("--map-negative-1");
	});

	it("requires sector treemap cells to encode direction through sign, text, and aria labels", () => {
		const document = loadPage();
		const cells = [...document.querySelectorAll<HTMLElement>(".treemap-cell-iv")];

		expect(cells.length).toBeGreaterThanOrEqual(16);

		for (const [index, cell] of cells.entries()) {
			const direction = cell.getAttribute("data-direction");
			const label = cell.getAttribute("aria-label") ?? "";
			const sign = cell.querySelector<HTMLElement>(':scope > .treemap-cell-sign[aria-hidden="true"]');

			expect(direction).toMatch(/^(up|down|flat)$/);
			if (direction === "up") {
				expect(sign?.textContent?.trim(), `cell ${index + 1}`).toBe("▲");
				expect(label, `cell ${index + 1}`).toContain("涨幅");
			}
			if (direction === "down") {
				expect(sign?.textContent?.trim(), `cell ${index + 1}`).toBe("▼");
				expect(label, `cell ${index + 1}`).toContain("跌幅");
			}
			if (direction === "flat") {
				expect(sign?.textContent?.trim(), `cell ${index + 1}`).toBe("•");
				expect(label, `cell ${index + 1}`).toMatch(/持平|涨跌幅/);
			}
		}
	});

	it("applies a deterministic treemap label budget so small rectangles do not become text clutter", () => {
		const document = loadPage();
		const cells = [...document.querySelectorAll<HTMLElement>(".treemap-cell-iv")];

		expect(cells.length).toBeGreaterThanOrEqual(16);

		for (const [index, cell] of cells.entries()) {
			const budget = cell.getAttribute("data-label-budget");
			const name = cell.querySelector(".treemap-cell-name");
			const change = cell.querySelector(".treemap-cell-change");
			const volume = cell.querySelector(".treemap-cell-vol");

			expect(budget, `cell ${index + 1}`).toMatch(/^(full|compact|name-only)$/);
			expect(name, `cell ${index + 1}`).not.toBeNull();

			if (budget === "full") {
				expect(change, `cell ${index + 1}`).not.toBeNull();
				expect(volume, `cell ${index + 1}`).not.toBeNull();
			}
			if (budget === "compact") {
				expect(change, `cell ${index + 1}`).not.toBeNull();
				expect(volume, `cell ${index + 1}`).toBeNull();
			}
			if (budget === "name-only") {
				expect(change, `cell ${index + 1}`).toBeNull();
				expect(volume, `cell ${index + 1}`).toBeNull();
			}
		}
	});

	it("keeps treemap and heatmap cells grouped, direction-aware, and keyboard reachable", () => {
		const document = loadPage();
		const treemapCells = document.querySelectorAll(".treemap-cell-iv");
		const heatmapCells = document.querySelectorAll(".heatmap-cell");

		expect(treemapCells.length).toBeGreaterThanOrEqual(16);
		expect(heatmapCells.length).toBeGreaterThanOrEqual(32);
		expect(document.querySelectorAll(".treemap-group-label")).toHaveLength(0);

		for (const cell of [...treemapCells, ...heatmapCells]) {
			expect(cell.getAttribute("tabindex")).toBe("0");
			expect(cell.getAttribute("data-direction")).toMatch(/^(up|down|flat)$/);
			expect(cell.getAttribute("data-sector-family")).toMatch(/^(growth|cyclical|defensive|financial)$/);
		}
	});

	it("sizes stock heat-map tiles by turnover and keeps labels neutral for readable market scanning", () => {
		const document = loadPage();
		const html = loadHtml();
		const heatmap = document.querySelector(".map-view-heatmap");
		const heatmapCells = [...document.querySelectorAll(".heatmap-cell")];
		const sizeBuckets = new Set(heatmapCells.map((cell) => cell.getAttribute("data-size-bucket")));

		expect(heatmap?.getAttribute("aria-label")).toContain("面积表示成交额");
		expect(elementText(document.querySelector(".map-container"), "[data-map-metric-switcher]")).toContain(
			"个股 Size 成交额",
		);
		expect(sizeBuckets).toEqual(new Set(["xl", "lg", "md", "sm"]));
		expect(html).toContain("grid-auto-flow: dense");
		expect(html).toContain("grid-template-rows: repeat(6");
		expect(html).toContain("--market-map-cell-title");
		expect(html).toContain("--market-map-cell-value");
		expect(html).toContain('.heatmap-cell[data-size-bucket="xl"]');
		expect(html).toContain('.heatmap-cell[data-size-bucket="sm"]');
		expect(html).toContain(".map-view-heatmap .heatmap-cell:nth-child(32)");
		expect(html).not.toContain('data-size-metric="mono-size"');

		for (const cell of heatmapCells) {
			expect(cell.getAttribute("data-size-metric")).toBe("turnover-value");
			expect(cell.getAttribute("data-size-bucket")).toMatch(/^(xl|lg|md|sm)$/);
		}
	});

	it("keeps the industry map focused on sector-level signal without in-cell stock chips", () => {
		const document = loadPage();
		const treemap = document.querySelector(".treemap");

		expect(treemap?.querySelectorAll(".map-stock-chip")).toHaveLength(0);
		expect(treemap?.querySelectorAll(".map-stock-strip")).toHaveLength(0);
		expect(treemap?.querySelectorAll(".treemap-group-label")).toHaveLength(0);
		expect(treemap?.querySelectorAll(".map-sector-boundary")).toHaveLength(4);
		expect(treemap?.textContent ?? "").not.toMatch(/成长科技|金融地产|防御消费|周期制造/);
	});

	it("uses a calibrated stepped diverging palette instead of glossy accent glows", () => {
		const document = loadPage();
		const html = loadHtml();
		const mapCells = document.querySelectorAll(".treemap-cell-iv, .heatmap-cell");

		for (const step of [1, 2, 3, 4]) {
			expect(html).toContain(`--map-market-up-${step}`);
			expect(html).toContain(`--map-market-down-${step}`);
			expect(html).toContain(`--heat-up-${step}`);
			expect(html).toContain(`--heat-down-${step}`);
		}

		expect(html).not.toContain("--map-positive-");
		expect(html).not.toContain("--map-negative-");
		expect(html).toContain("--map-neutral-fill");
		expect(html).toContain("--map-text-on-cell");
		expect(html).toContain("--heat-flat");
		expect(html).toContain("color-mix(in oklch, var(--market-up-fg)");
		expect(html).toContain("color-mix(in oklch, var(--market-down-fg)");
		expect(html).not.toContain(".treemap::after");
		expect(html).not.toContain("mix-blend-mode: screen");
		expect(html).not.toContain("inset 0 -32px 44px");
		expect(html).not.toContain("inset 4px 0 0 var(--heat-line)");
		expect(html).not.toContain("inset 3px 0 0 var(--heat-line)");
		expect(html).not.toContain("inset 2px 0 0 var(--chip-line)");
		expect(html).toContain("border: 1px solid color-mix(in oklch, var(--heat-line) 12%, var(--map-cell-border));");
		expect(html).toContain("border-color: color-mix(in oklch, var(--heat-line)");
		expect(html).not.toContain("oklch(from var(--market-up-fg)");
		expect(html).not.toContain("oklch(from var(--market-down-fg)");
		expect(html).not.toContain("--direction-glow");
		expect(html).not.toContain("--family-edge");
		expect(html).not.toMatch(/radial-gradient\(circle[^;]+--market-(up|down)-fg/s);

		for (const cell of mapCells) {
			expect(cell.getAttribute("data-heat")).toMatch(/^(up|down)-[1-4]$|^flat$/);
		}
	});

	it("normalizes in-cell typography and keeps direction color out of label clutter", () => {
		const html = loadHtml();
		const document = loadPage();
		const treemapCells = document.querySelectorAll(".treemap-cell-iv");
		const heatmapCells = document.querySelectorAll(".heatmap-cell");

		expect(html).toContain("--market-map-cell-title");
		expect(html).toContain("--market-map-cell-value");
		expect(html).toContain("--market-map-cell-meta");
		expect(html).toMatch(/\.treemap-cell-name,\s*\.hm-name\s*\{/s);
		expect(html).toMatch(/\.treemap-cell-change,\s*\.hm-change\s*\{[^}]*font-family:\s*var\(--font-family-ui\);[^}]*font-weight:\s*var\(--font-weight-medium\);/s);
		expect(html).toMatch(/\.treemap-cell-vol,\s*\.hm-vol\s*\{[^}]*font-family:\s*var\(--font-family-ui\);/s);
		expect(html).toContain('.heatmap-cell[data-size-bucket="sm"] .hm-change { display: none; }');
		expect(html).not.toContain("color-mix(in oklch, var(--heat-text) 82%");
		expect(html).not.toMatch(/\.treemap-cell-change,\s*\.hm-change\s*\{[^}]*font-family:\s*var\(--font-family-numeric\)/s);
		expect(html).not.toMatch(/\.map-stock-chip\b/s);

		for (const cell of treemapCells) {
			expect(cell.querySelector(".treemap-cell-name")?.textContent?.trim()).toBeTruthy();
			if (cell.getAttribute("data-label-budget") !== "name-only") {
				expect(cell.querySelector(".treemap-cell-change")?.textContent?.trim()).toMatch(/^[+-]\d/);
			}
		}

		for (const cell of heatmapCells) {
			expect(cell.querySelector(".hm-name")?.textContent?.trim()).toBeTruthy();
			expect(cell.querySelector(".hm-change")?.textContent?.trim()).toMatch(/^[+-]\d/);
		}
	});

	it("shows turnover on every stock heat-map tile", () => {
		const document = loadPage();
		const heatmapCells = [...document.querySelectorAll(".heatmap-cell")];

		expect(heatmapCells.length).toBeGreaterThanOrEqual(32);

		for (const cell of heatmapCells) {
			const turnover = cell.querySelector(".hm-vol")?.textContent?.trim();

			expect(turnover).toMatch(/^\d+(\.\d+)?亿$/);
			expect(cell.getAttribute("aria-label")).toContain("成交");
		}
	});

	it("keeps heat-map numbers crisp without redundant direction tint or shadow shelves", () => {
		const html = loadHtml();

		expect(html).not.toContain("--market-map-cell-value-up");
		expect(html).not.toContain("--market-map-cell-value-down");
		expect(html).not.toContain("--market-map-info-shelf");
		expect(html).not.toMatch(/\.heatmap-cell::before\s*\{[^}]*linear-gradient\(180deg/s);
		expect(html).not.toMatch(/\.heatmap-cell\[data-direction="(?:up|down)"\]\s*\{[^}]*--market-map-cell-value/s);
		expect(html).not.toMatch(/--market-map-cell-(?:title|value|meta):[^;]*transparent/);
		expect(html).not.toContain("opacity: 0.94;");
		expect(html).not.toContain("opacity: 0.96;");
		expect(html).not.toContain("0 6px 16px");
		expect(html).not.toContain("0 8px 18px");
		expect(html).not.toMatch(/\.(?:treemap-cell-iv|heatmap-cell)\[data-direction="(?:up|down|flat)"\]::after/s);
		expect(html).not.toMatch(/\.hm-change\s*\{[^}]*font-size:\s*var\(--font-size-10\)/s);
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

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(import.meta.dirname, "../prototype/page-platform.html");

function loadPage() {
	const html = readFileSync(prototypePath, "utf-8");
	return new JSDOM(html).window.document;
}

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadDefaultViewHtml() {
	const html = loadHtml();
	const start = html.indexOf('<section id="default-view"');
	const end = html.indexOf('<section id="states-gallery"');

	return start >= 0 && end > start ? html.slice(start, end) : html;
}

describe("page-platform prototype", () => {
	it("keeps every data table row aligned with its visible header contract", () => {
		const document = loadPage();
		const tables = Array.from(document.querySelectorAll("#default-view .data-table"));

		expect(tables.length).toBeGreaterThanOrEqual(3);

		for (const table of tables) {
			const headerCount = table.querySelectorAll("thead th").length;
			const rows = Array.from(table.querySelectorAll("tbody tr"));

			expect(headerCount).toBeGreaterThan(0);
			for (const row of rows) {
				expect(row.querySelectorAll("td").length).toBe(headerCount);
			}
		}
	});

	it("uses the default workspace for data quality history and incident evidence", () => {
		const document = loadPage();
		const html = loadHtml();
		const evidence = document.querySelector("[data-ops-evidence-strip]");
		const heightClasses = Array.from(document.querySelectorAll("[data-dq-point] .dq-bar"))
			.map((element) => Array.from(element.classList).find((className) => /^dq-h-\d+$/.test(className)))
			.filter((className): className is string => Boolean(className));

		expect(evidence).not.toBeNull();
		expect(evidence?.querySelector("[data-dq-score-history]")).not.toBeNull();
		expect(evidence?.querySelector("[data-incident-history]")).not.toBeNull();
		expect(evidence?.querySelectorAll("[data-dq-point]").length).toBeGreaterThanOrEqual(12);
		expect(evidence?.querySelectorAll("[data-incident-row]").length).toBeGreaterThanOrEqual(5);
		for (const heightClass of heightClasses) {
			expect(html).toContain(`.${heightClass}`);
		}
	});

	it("keeps system monitor compact labels and numeric values styled in the right order", () => {
		const document = loadPage();
		const html = loadHtml();
		const compactItems = Array.from(document.querySelectorAll(".resource-compact-item"));

		expect(compactItems).toHaveLength(3);
		expect(html).toMatch(/\.resource-compact-item\s*\{[^}]*font-family:\s*var\(--font-family-ui\);/s);
		expect(html).toMatch(/\.resource-compact-value\s*\{[^}]*font-family:\s*var\(--font-family-numeric\);/s);

		for (const item of compactItems) {
			const label = item.querySelector(".resource-compact-label");
			const value = item.querySelector(".resource-compact-value");

			expect(label?.textContent?.trim()).toMatch(/^(CPU|内存|磁盘)$/);
			expect(label?.textContent ?? "").not.toMatch(/\d|%/);
			expect(value?.textContent?.trim()).toMatch(/^\d+%$/);
		}
	});

	it("renders system health as text without any circular ring gauge in the strip", () => {
		const document = loadPage();
		const html = loadHtml();
		const summary = document.querySelector(".health-score-summary");

		expect(document.querySelector(".ops-health .health-score-ring")).toBeNull();
		expect(document.querySelector(".ops-health .health-score-visual")).toBeNull();
		expect(document.querySelector(".ops-health svg[data-donut]")).toBeNull();
		expect(summary?.querySelector(".health-score-value")?.textContent?.trim()).toBe("97");
		expect(summary?.querySelector(".health-score-unit")?.textContent?.trim()).toBe("%");
		expect(summary?.querySelector(".health-score-scale")?.textContent?.trim()).toBe("/100");
		expect(html).not.toContain("health-score-ring");
		expect(html).not.toContain("health-score-visual");
	});

	it("keeps strip health metrics as text-first values without inline donut rings", () => {
		const document = loadPage();
		const html = loadHtml();
		const metrics = Array.from(document.querySelectorAll(".ops-health .health-metric"));

		expect(metrics.length).toBeGreaterThanOrEqual(6);
		expect(document.querySelector(".ops-health .health-inline-gauge")).toBeNull();
		expect(html).not.toContain("health-inline-gauge");

		for (const metric of metrics) {
			const label = metric.querySelector(".health-metric-label");
			const value = metric.querySelector(".health-metric-value");

			expect(metric.querySelector("svg[data-donut]")).toBeNull();
			expect(label?.textContent?.trim()).toMatch(/^(新鲜度|完整度|准确度|数据源|任务|负载)$/);
			expect(value?.textContent?.trim()).toMatch(/^(\d+(\.\d+)?%|\d+\/\d+)$/);
		}
	});

	it("keeps default-view entrance motion subtle and non-jittery", () => {
		const defaultView = loadDefaultViewHtml();
		const delays = [...defaultView.matchAll(/data-reveal-delay="(\d+)"/g)].map((match) => Number(match[1]));

		expect(defaultView).not.toContain('data-reveal="fade-right"');
		expect(Math.max(...delays)).toBeLessThanOrEqual(220);
	});
});

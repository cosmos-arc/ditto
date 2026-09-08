import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(
	import.meta.dirname,
	"../prototype/page-markets-calendar.html",
);

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
}

function loadPage() {
	return new JSDOM(loadHtml()).window.document;
}

function elementText(root: Element | null, selector: string) {
	return root?.querySelector(selector)?.textContent ?? "";
}

describe("page-markets-calendar prototype", () => {
	it("uses a gate-recognizable catalog shell with bounded calendar and right rail slots", () => {
		const document = loadPage();

		expect(document.querySelector("#default-view > .shell-catalog.catalog-shell")).not.toBeNull();
		expect(document.querySelector(".filter-toolbar[data-contract-slot='filter-bar']")).not.toBeNull();
		expect(document.querySelector(".workspace-body.catalog-main[data-contract-slot='main']")).not.toBeNull();
		expect(document.querySelector(".workspace-right.catalog-detail[data-contract-slot='right-rail']")).not.toBeNull();
	});

	it("documents horizon, impact, color, and destination semantics for fast calendar reading", () => {
		const document = loadPage();
		const strip = document.querySelector(".calendar-reading-strip");

		expect(strip).not.toBeNull();
		expect(elementText(strip, "[data-calendar-horizon]")).toContain("未来 10 日");
		expect(elementText(strip, "[data-calendar-impact]")).toContain("高影响");
		expect(elementText(strip, "[data-calendar-color]")).toContain("红涨绿跌");
		expect(elementText(strip, "[data-calendar-destination]")).toContain("详情");
		expect(strip?.querySelectorAll(".calendar-legend-stop")).toHaveLength(4);
	});

	it("renders eventful days as scan-readable cells instead of color-only dots", () => {
		const document = loadPage();
		const eventDays = Array.from(document.querySelectorAll(".cal-day[data-event-count]"));

		expect(eventDays.length).toBeGreaterThanOrEqual(6);
		for (const day of eventDays) {
			expect(day.getAttribute("data-impact")).toMatch(/^(high|medium|low)$/);
			expect(day.querySelector(".cal-event-tag")).not.toBeNull();
			expect(day.querySelector(".cal-impact-symbol")?.textContent).toMatch(/[▲◆•]/);
		}
	});

	it("keeps list and timeline events impact-aware without relying on color alone", () => {
		const document = loadPage();
		const rows = Array.from(document.querySelectorAll(".event-row"));
		const timelineItems = Array.from(document.querySelectorAll(".timeline-item"));

		expect(rows).toHaveLength(7);
		for (const row of rows) {
			expect(row.getAttribute("data-impact")).toMatch(/^(high|medium|low)$/);
			expect(row.getAttribute("data-event-type")).toBeTruthy();
			expect(row.querySelector(".impact-symbol")?.textContent).toMatch(/[▲◆•]/);
		}

		expect(timelineItems).toHaveLength(5);
		for (const item of timelineItems) {
			expect(item.getAttribute("data-impact")).toMatch(/^(high|medium)$/);
			expect(item.querySelector(".timeline-impact-symbol")?.textContent).toMatch(/[▲◆]/);
		}
	});

	it("keeps economic timeline content comfortably away from the right rail divider", () => {
		const html = loadHtml();

		expect(html).toMatch(
			/\.timeline-header\s*\{[^}]*padding:\s*var\(--space-10\)\s+var\(--space-20\)\s+var\(--space-10\)\s+var\(--density-panel-padding\)/s,
		);
		expect(html).toMatch(
			/\.timeline-body\s*\{[^}]*padding:\s*var\(--space-10\)\s+var\(--space-20\)\s+var\(--space-10\)\s+var\(--density-panel-padding\)/s,
		);
		expect(html).toMatch(/\.timeline-item\s*\{[^}]*padding:\s*var\(--space-8\)\s+var\(--space-24\)/s);
		expect(html).toMatch(/\.timeline-item:hover\s*\{[^}]*margin:\s*0;/s);
	});

	it("wires the month and list view switcher to real prototype state", () => {
		const document = loadPage();
		const html = loadHtml();

		expect(document.querySelector("#calendar-view-month[name='calendar-view'][checked]")).not.toBeNull();
		expect(document.querySelector("#calendar-view-list[name='calendar-view']")).not.toBeNull();
		expect(document.querySelector("label.view-switcher-btn[for='calendar-view-month']")?.textContent).toContain(
			"月历",
		);
		expect(document.querySelector("label.view-switcher-btn[for='calendar-view-list']")?.textContent).toContain(
			"列表",
		);
		expect(html).not.toContain('class="view-switcher-btn active"');
		expect(html).toMatch(/\.view-switcher\s+input:checked\s+\+\s+\.view-switcher-btn\s*\{/s);
		expect(html).toMatch(
			/\.shell-catalog:has\(#calendar-view-list:checked\)\s+\.calendar-section\s*\{[^}]*display:\s*none;/s,
		);
		expect(html).toMatch(
			/\.shell-catalog:has\(#calendar-view-list:checked\)\s+\.event-list-section\s*\{[^}]*flex:\s*1\s+1\s+auto;[^}]*max-height:\s*none;/s,
		);
	});

	it("keeps default-view numeric values deterministic for visual review screenshots", () => {
		const document = loadPage();

		expect(document.querySelectorAll("#default-view [data-ticker], #default-view [data-counter]")).toHaveLength(
			0,
		);
	});

	it("keeps the page in restrained Graphite Studio workbench language", () => {
		const html = loadHtml();

		expect(html).not.toContain('data-mouse-glow="true"');
		expect(html).not.toContain(".shell-catalog::before");
		expect(html).not.toContain(".shell-catalog::after");
		expect(html).not.toContain("radial-gradient");
	});
});

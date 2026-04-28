import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypePath = resolve(import.meta.dirname, "../docs/designs/specs/prototypes/page-platform.html");

function loadPage() {
	const html = readFileSync(prototypePath, "utf-8");
	return new JSDOM(html).window.document;
}

function loadHtml() {
	return readFileSync(prototypePath, "utf-8");
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
});

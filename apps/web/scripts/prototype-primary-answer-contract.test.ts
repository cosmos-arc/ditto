import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");

const activePrototypeFiles = readdirSync(prototypesDir).filter(
	(file) => /^page-.*\.html$/.test(file) && file !== "page-agent-console.html",
).sort();

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(join(prototypesDir, file), "utf8")).window.document;
}

describe("prototype primary answer contract", () => {
	it("gives every active route exactly one dominant primary answer region", () => {
		const failures: string[] = [];

		for (const file of activePrototypeFiles) {
			const document = loadDocument(file);
			const primaryRegions = [
				...document.querySelectorAll("[data-primary-answer-equivalent], [data-primary-answer]"),
			];
			const dominantRegions = primaryRegions.filter(
				(element) => element.getAttribute("data-primary-weight") === "dominant",
			);

			if (dominantRegions.length !== 1) {
				failures.push(`${file}: expected 1 dominant primary answer, got ${dominantRegions.length}`);
			}
		}

		expect(failures).toEqual([]);
	});

	it("marks secondary context regions so visual hierarchy can be audited", () => {
		const failures: string[] = [];

		for (const file of activePrototypeFiles) {
			const document = loadDocument(file);
			const primaryRegions = [
				...document.querySelectorAll(
					"[data-primary-answer][data-primary-weight='dominant'], [data-primary-answer-equivalent][data-primary-weight='dominant']",
				),
			];
			const secondaryRegions = [...document.querySelectorAll("[data-secondary-context]")];

			if (primaryRegions.length === 1 && secondaryRegions.length === 0) {
				failures.push(`${file}: missing [data-secondary-context]`);
			}
		}

		expect(failures).toEqual([]);
	});
});

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");
const sharedLayoutComponentsCss = join(prototypesDir, "shared/layout-components.css");

const activePrototypeFiles = readdirSync(prototypesDir).filter(
	(file) => /^page-.*\.html$/.test(file),
).sort();

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(join(prototypesDir, file), "utf8")).window.document;
}

describe("prototype primary answer contract", () => {
	it("defines one shared visual weight grammar for primary answers", () => {
		const css = readFileSync(sharedLayoutComponentsCss, "utf8");
		const grammarSelectors = [
			{ label: "dominant-region", pattern: /\[data-primary-weight="dominant"\]/ },
			{ label: "judgment", pattern: /\[data-answer-judgment\]/ },
			{ label: "metric", pattern: /\[data-answer-metric\]/ },
			{ label: "evidence", pattern: /\[data-answer-evidence\]/ },
			{ label: "action", pattern: /\[data-answer-action\]/ },
		];
		const domainFocusSelectors = ["home", "markets", "research", "trading", "platform"].map((domain) => ({
			label: `domain-${domain}`,
			pattern: new RegExp(`\\[data-domain="${domain}"\\][\\s\\S]*--primary-answer-focus`),
		}));
		const missingSelectors = [...grammarSelectors, ...domainFocusSelectors]
			.filter(({ pattern }) => !pattern.test(css))
			.map(({ label }) => label);
		const missingVariables = [
			"--primary-answer-judgment-scale",
			"--primary-answer-evidence-scale",
			"--primary-answer-action-scale",
		].filter((token) => !css.includes(token));

		expect(missingSelectors).toEqual([]);
		expect(missingVariables).toEqual([]);
	});

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
	}, 20_000);

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
	}, 20_000);
});

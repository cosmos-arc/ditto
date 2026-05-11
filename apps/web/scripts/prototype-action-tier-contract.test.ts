import { readFileSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const root = process.cwd();
const prototypesDir = join(root, "docs/designs/specs/prototypes");

const highDensityPages = [
	"page-markets-screener.html",
	"page-strategy-studio.html",
	"page-signals-inbox.html",
	"page-strategy-list.html",
	"page-a-shares.html",
	"page-cross-market.html",
	"page-instrument-hub.html",
	"page-orders-ledger.html",
] as const;

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(join(prototypesDir, file), "utf8")).window.document;
}

describe("prototype action tier contract", () => {
	it("marks visible decision actions with an explicit action tier", () => {
		const failures: string[] = [];

		for (const file of highDensityPages) {
			const document = loadDocument(file);
			const actions = [
				...document.querySelectorAll<HTMLElement>(
					"[data-decision-option], [data-answer-action], .btn-primary, .header-action-btn, .studio-action, .row-action",
				),
			];

			for (const action of actions) {
				const text =
					action.textContent?.replace(/\s+/g, " ").trim() ||
					action.getAttribute("aria-label") ||
					"unnamed";
				if (!action.hasAttribute("data-action-tier")) {
					failures.push(`${file}: missing data-action-tier on "${text}"`);
				}
			}
		}

		expect(failures).toEqual([]);
	});

	it("keeps primary visible actions capped at three per high-density page", () => {
		const failures: string[] = [];

		for (const file of highDensityPages) {
			const document = loadDocument(file);
			const primaryActions = [...document.querySelectorAll("[data-action-tier='primary']")];

			if (primaryActions.length > 3) {
				failures.push(`${file}: ${primaryActions.length} primary actions`);
			}
		}

		expect(failures).toEqual([]);
	});
});

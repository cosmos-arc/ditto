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

const actionTierValues = new Set(["primary", "context", "overflow", "command"]);
const actionCandidateSelector =
	"[data-decision-option], [data-answer-action], .btn-primary, .header-action-btn, .studio-action, .row-action";
const hiddenContextSelector =
	"#states-gallery, #overlays-gallery, [aria-hidden='true'], [hidden], template";

function loadDocument(file: string): Document {
	return new JSDOM(readFileSync(join(prototypesDir, file), "utf8")).window.document;
}

function isInHiddenContext(element: Element): boolean {
	return element.closest(hiddenContextSelector) !== null;
}

function getVisibleActionCandidates(document: Document): HTMLElement[] {
	return [...document.querySelectorAll<HTMLElement>(actionCandidateSelector)].filter(
		(action) => !isInHiddenContext(action),
	);
}

describe("prototype action tier contract", () => {
	it("marks visible decision actions with an explicit action tier", () => {
		const failures: string[] = [];

		for (const file of highDensityPages) {
			const document = loadDocument(file);
			const actions = getVisibleActionCandidates(document);

			for (const action of actions) {
				const text =
					action.textContent?.replace(/\s+/g, " ").trim() ||
					action.getAttribute("aria-label") ||
					"unnamed";
				const actionTier = action.getAttribute("data-action-tier");

				if (actionTier === null) {
					failures.push(`${file}: missing data-action-tier on "${text}"`);
					continue;
				}

				if (!actionTierValues.has(actionTier)) {
					failures.push(`${file}: invalid data-action-tier "${actionTier}" on "${text}"`);
				}
			}
		}

		expect(failures).toEqual([]);
	});

	it("keeps primary visible actions capped at three per high-density page", () => {
		const failures: string[] = [];

		for (const file of highDensityPages) {
			const document = loadDocument(file);
			const primaryActions = getVisibleActionCandidates(document).filter(
				(action) => action.getAttribute("data-action-tier") === "primary",
			);

			if (primaryActions.length > 3) {
				failures.push(`${file}: ${primaryActions.length} primary actions`);
			}
		}

		expect(failures).toEqual([]);
	});
});

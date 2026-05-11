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
	[
		"[data-decision-option]",
		"[data-answer-action]",
		".btn-primary",
		".header-action-btn",
		".header-utility-btn",
		".studio-action",
		".row-action",
		".batch-btn",
		".batch-action-btn",
		".detail-action",
		".trace-action-btn",
	].join(", ");
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

	it("keeps screener result rows exposing compare actions", () => {
		const document = loadDocument("page-markets-screener.html");
		const resultRows = [
			...document.querySelectorAll<HTMLElement>(
				'table[data-compare-source="screener-results"] tbody tr',
			),
		].filter((row) => !isInHiddenContext(row));
		const failures: string[] = [];

		for (const row of resultRows) {
			const code = row.querySelector(".cell-ticker")?.textContent?.trim() ?? "unknown";
			const compareAction = row.querySelector<HTMLElement>(".row-action");

			if (compareAction === null) {
				failures.push(`page-markets-screener.html: missing row compare action on ${code}`);
				continue;
			}

			const actionText = compareAction.textContent?.replace(/\s+/g, " ").trim();
			const actionTier = compareAction.getAttribute("data-action-tier");

			if (actionText !== "+ 对比") {
				failures.push(
					`page-markets-screener.html: invalid row compare action "${actionText}" on ${code}`,
				);
			}

			if (actionTier !== "context" && actionTier !== "overflow") {
				failures.push(
					`page-markets-screener.html: row compare action on ${code} must be context or overflow`,
				);
			}
		}

		expect(failures).toEqual([]);
	});
});

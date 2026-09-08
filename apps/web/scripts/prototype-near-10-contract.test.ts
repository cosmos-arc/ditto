import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const prototypesDir = resolve(import.meta.dirname, "../prototype");
const archivedPrototypeIds = new Set(["ai-overview", "ai-copilot"]);
const catalogTasksByPageId: Record<string, string> = {
	"markets-screener": "screener-result-routing",
	"markets-calendar": "event-calendar",
	watchlist: "watchlist-next-action",
	"factor-list": "factor-validity",
	"strategy-list": "strategy-health",
	"backtest-list": "backtest-comparison",
	"experiment-list": "experiment-result-matrix",
	"universe-list": "universe-impact",
};
const objectHubPageIds = [
	"instrument-hub",
	"factor-analysis",
	"strategies-detail",
	"backtest-result",
] as const;

type ManifestPage = {
	id: string;
	file: string;
	shellFamily?: string;
};

type EditionManifest = {
	pages: ManifestPage[];
};

function readManifest(): EditionManifest {
	return JSON.parse(
		readFileSync(join(prototypesDir, ".edition-manifest.json"), "utf8"),
	) as EditionManifest;
}

function activePages(): ManifestPage[] {
	return readManifest().pages.filter(
		(page) =>
			page.file?.startsWith("page-") &&
			page.file.endsWith(".html") &&
			page.id !== "token-showcase" &&
			!archivedPrototypeIds.has(page.id),
	);
}

function readDocument(page: ManifestPage): Document {
	return new JSDOM(readFileSync(join(prototypesDir, page.file), "utf8")).window.document;
}

describe("near-10 primary answer contract", () => {
	for (const page of activePages()) {
		it(`${page.id} exposes one complete primary answer`, () => {
			const document = readDocument(page);
			const answers = document.querySelectorAll(
				"[data-primary-answer], [data-primary-answer-equivalent]",
			);

			expect(answers, `${page.id}: expected exactly one primary answer`).toHaveLength(1);

				const answer = answers[0];
				if (answer === undefined) throw new Error(`${page.id}: primary answer disappeared after validation`);
			expect(answer.querySelectorAll("[data-answer-judgment]").length).toBeGreaterThanOrEqual(1);
			expect(answer.querySelectorAll("[data-answer-metric]").length).toBeGreaterThanOrEqual(1);
			expect(answer.querySelectorAll("[data-answer-evidence]").length).toBeGreaterThanOrEqual(2);
			expect(answer.querySelectorAll("[data-answer-action]").length).toBeGreaterThanOrEqual(1);
			expect((answer.textContent ?? "").replace(/\s+/g, " ").trim().length).toBeGreaterThan(40);
		});
	}

	it("marks catalog pages with distinct task-specific workflow contracts", () => {
		const violations: string[] = [];

		for (const [pageId, expectedTask] of Object.entries(catalogTasksByPageId)) {
			const page = activePages().find((candidate) => candidate.id === pageId);
			if (!page) {
				violations.push(`${pageId}: missing active page`);
				continue;
			}

			const document = readDocument(page);
			if (!document.querySelector(`[data-catalog-task="${expectedTask}"]`)) {
				violations.push(`${pageId}: missing data-catalog-task="${expectedTask}"`);
			}
		}

		expect(violations).toEqual([]);
	});

	it("previews action consequences on object hub pages", () => {
		const violations: string[] = [];

		for (const pageId of objectHubPageIds) {
			const page = activePages().find((candidate) => candidate.id === pageId);
			if (!page) {
				violations.push(`${pageId}: missing active page`);
				continue;
			}

			const document = readDocument(page);
			const preview = document.querySelector("[data-object-consequence-preview]");
			if (!preview) {
				violations.push(`${pageId}: missing data-object-consequence-preview`);
				continue;
			}

			const impactRows = preview.querySelectorAll("[data-consequence-impact]");
			const destinationAction = preview.querySelector("[data-consequence-destination-action]");
			if (impactRows.length < 2) {
				violations.push(`${pageId}: consequence impacts ${impactRows.length}`);
			}
			if (!destinationAction) {
				violations.push(`${pageId}: missing destination action`);
			}
		}

		expect(violations).toEqual([]);
	});
});

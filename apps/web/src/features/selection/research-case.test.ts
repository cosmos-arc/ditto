import { describe, expect, it } from "vitest";
import { researchCaseFixture, selectionRunFixtures } from "@/mocks/fixtures/selection";
import type { CreateResearchCaseBody, ResearchCase, SelectionRun } from "./api";
import { toResearchCaseView } from "./research-case";

/** live 车道样例：knowledge 晚于 as_of（发起时刻签发），publication ≤ knowledge。 */
function liveLaneCase(): { readonly value: ResearchCase; readonly run: SelectionRun } {
	const run: SelectionRun = {
		...selectionRunFixtures[0],
		as_of: "2026-11-10T07:00:00Z",
		knowledge_cutoff: "2026-11-11T09:30:00Z",
		publication_cutoff: "2026-11-11T09:00:00Z",
	};
	const value: ResearchCase = {
		...researchCaseFixture,
		as_of: run.as_of,
		knowledge_cutoff: run.knowledge_cutoff,
		publication_cutoff: run.publication_cutoff,
	};
	return { value, run };
}

describe("toResearchCaseView", () => {
	it("accepts a live-lane case whose knowledge cutoff follows the decision time", () => {
		const { value, run } = liveLaneCase();
		const submitted: CreateResearchCaseBody = {
			objective: value.objective,
			candidate_instrument_ids: [...value.candidate_instrument_ids],
		};

		const view = toResearchCaseView(value, run, submitted);

		expect(view.caseId).toBe(value.case_id);
		expect(view.degraded).toBe(false);
	});

	it("rejects a case whose publication cutoff violates the knowledge cutoff", () => {
		const { value, run } = liveLaneCase();
		const broken: ResearchCase = {
			...value,
			publication_cutoff: "2026-11-11T10:00:00Z",
		};

		expect(() =>
			toResearchCaseView(
				broken,
				{ ...run, publication_cutoff: broken.publication_cutoff },
				{ candidate_instrument_ids: [], objective: broken.objective },
			),
		).toThrow(/lineage、schema 版本或提交范围与请求不一致/);
	});

	it("rejects a case whose lineage drifts from the originating run", () => {
		const { value, run } = liveLaneCase();

		expect(() =>
			toResearchCaseView(
				value,
				{ ...run, input_hash: "f".repeat(64) },
				{ candidate_instrument_ids: [], objective: value.objective },
			),
		).toThrow(/lineage、schema 版本或提交范围与请求不一致/);
	});
});

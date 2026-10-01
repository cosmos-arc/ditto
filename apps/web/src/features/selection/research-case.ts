import type { ResearchCase, SelectionRun } from "./api";

function sameSnapshotSet(left: readonly string[], right: readonly string[]): boolean {
	return [...left].sort().join("\n") === [...right].sort().join("\n");
}

export function toResearchCaseView(value: ResearchCase, run: SelectionRun) {
	if (
		!/^[a-f0-9]{64}$/.test(value.content_hash) ||
		value.case_id !== `research-case:sha256:${value.content_hash}` ||
		value.selection_run_id !== run.run_id ||
		value.selection_input_hash !== run.input_hash ||
		value.selection_spec_hash !== run.spec_hash ||
		value.universe_snapshot_id !== run.universe_snapshot_id ||
		value.industry_rotation_snapshot_id !== run.industry_rotation_snapshot_id ||
		value.as_of !== run.as_of ||
		value.knowledge_cutoff !== run.knowledge_cutoff ||
		value.publication_cutoff !== run.publication_cutoff ||
		!sameSnapshotSet(value.source_snapshot_ids, run.source_snapshot_ids) ||
		value.selection_status !== run.status ||
		!Number.isSafeInteger(value.schema_version) ||
		Number.isNaN(Date.parse(value.as_of)) ||
		!Array.isArray(value.candidate_instrument_ids) ||
		value.candidate_instrument_ids.some((instrumentId) => !Number.isSafeInteger(instrumentId) || instrumentId <= 0) ||
		!Array.isArray(value.missing_inputs) ||
		(value.selection_status !== "ready" && value.selection_status !== "degraded")
	)
		throw new Error("研究用例响应的 lineage 与所选运行不一致");
	return {
		caseId: value.case_id,
		contentHash: value.content_hash,
		degraded: value.selection_status === "degraded",
		missingInputs: value.missing_inputs.join("、"),
	};
}
export type ResearchCaseView = ReturnType<typeof toResearchCaseView>;

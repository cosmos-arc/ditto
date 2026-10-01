import type { ResearchCase } from "./api";

export function toResearchCaseView(value: ResearchCase, runId: string) {
	if (
		!/^[a-f0-9]{64}$/.test(value.content_hash) ||
		value.case_id !== `research-case:sha256:${value.content_hash}` ||
		value.selection_run_id !== runId ||
		!Number.isSafeInteger(value.schema_version) ||
		Number.isNaN(Date.parse(value.as_of)) ||
		!Array.isArray(value.candidate_instrument_ids) ||
		value.candidate_instrument_ids.some((instrumentId) => !Number.isSafeInteger(instrumentId) || instrumentId <= 0) ||
		!Array.isArray(value.missing_inputs) ||
		!Array.isArray(value.source_snapshot_ids) ||
		(value.selection_status !== "ready" && value.selection_status !== "degraded")
	)
		throw new Error("研究用例响应的身份或 lineage 无效");
	return {
		caseId: value.case_id,
		contentHash: value.content_hash,
		degraded: value.selection_status === "degraded",
		missingInputs: value.missing_inputs.join("、"),
	};
}
export type ResearchCaseView = ReturnType<typeof toResearchCaseView>;

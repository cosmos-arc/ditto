import type { CreateResearchCaseBody, ResearchCase, SelectionRun } from "./api";

const SUPPORTED_RESEARCH_CASE_SCHEMA_VERSION = 1;

function sameSnapshotSet(left: readonly string[], right: readonly string[]): boolean {
	return [...left].sort().join("\n") === [...right].sort().join("\n");
}

function sameIdSequence(left: readonly number[], right: readonly number[]): boolean {
	return left.length === right.length && [...left].sort().join(",") === [...right].sort().join(",");
}

export function toResearchCaseView(value: ResearchCase, run: SelectionRun, submitted: CreateResearchCaseBody) {
	const asOfInstant = Date.parse(value.as_of);
	const knowledgeInstant = Date.parse(value.knowledge_cutoff);
	const publicationInstant = Date.parse(value.publication_cutoff);
	if (
		value.schema_version !== SUPPORTED_RESEARCH_CASE_SCHEMA_VERSION ||
		!/^[a-f0-9]{64}$/.test(value.content_hash) ||
		value.case_id !== `research-case:sha256:${value.content_hash}` ||
		value.selection_run_id !== run.run_id ||
		value.selection_run_id !== `selection-run:sha256:${value.selection_run_hash}` ||
		value.selection_input_hash !== run.input_hash ||
		value.selection_spec_hash !== run.spec_hash ||
		value.asset_kind !== run.asset_kind ||
		value.universe_snapshot_id !== run.universe_snapshot_id ||
		value.industry_rotation_snapshot_id !== run.industry_rotation_snapshot_id ||
		value.as_of !== run.as_of ||
		value.knowledge_cutoff !== run.knowledge_cutoff ||
		value.publication_cutoff !== run.publication_cutoff ||
		!sameSnapshotSet(value.source_snapshot_ids, run.source_snapshot_ids) ||
		!sameSnapshotSet(value.missing_inputs, run.missing_inputs) ||
		value.selection_status !== run.status ||
		Number.isNaN(asOfInstant) ||
		Number.isNaN(knowledgeInstant) ||
		Number.isNaN(publicationInstant) ||
		publicationInstant > knowledgeInstant ||
		knowledgeInstant > asOfInstant ||
		value.objective !== submitted.objective ||
		!sameIdSequence(value.candidate_instrument_ids, submitted.candidate_instrument_ids ?? []) ||
		(value.selection_status === "ready" && value.missing_inputs.length > 0) ||
		(value.selection_status !== "ready" && value.selection_status !== "degraded")
	)
		throw new Error("研究用例响应的 lineage、schema 版本或提交范围与请求不一致");
	return {
		caseId: value.case_id,
		contentHash: value.content_hash,
		degraded: value.selection_status === "degraded",
		missingInputs: value.missing_inputs.join("、"),
	};
}
export type ResearchCaseView = ReturnType<typeof toResearchCaseView>;

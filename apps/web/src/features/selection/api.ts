import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

export type AdmissionResponse = components["schemas"]["SelectionAdmissionResponse"];
export type CreateSelectionRunBody = components["schemas"]["CreateSelectionRunBody"];
export type IndustryRotation = components["schemas"]["IndustryRotationResponse"];
export type SelectionRun = components["schemas"]["SelectionRunResponse"];
export type SelectionRunDiff = components["schemas"]["SelectionRunDiffResponse"];
export type SelectionWorkspaceReceipt = components["schemas"]["SelectionWorkspaceReceiptResponse"];

export const selectionKeys = {
	all: ["selection"] as const,
	runs: (specId: string) => [...selectionKeys.all, "runs", specId] as const,
	run: (runId: string) => [...selectionKeys.all, "run", runId] as const,
	rotation: (snapshotId: string) => [...selectionKeys.all, "rotation", snapshotId] as const,
	compare: (beforeRunId: string, afterRunId: string) =>
		[...selectionKeys.all, "compare", beforeRunId, afterRunId] as const,
};

export function listSelectionRuns(specId: string, limit = 20): Promise<readonly SelectionRun[]> {
	return apiClient.get("/api/v1/selections/runs", { params: { query: { limit, spec_id: specId } } });
}

export function getSelectionRun(runId: string): Promise<SelectionRun> {
	return apiClient.get("/api/v1/selections/runs/{run_id}", { params: { path: { run_id: runId } } });
}

export function getIndustryRotation(snapshotId: string): Promise<IndustryRotation> {
	return apiClient.get("/api/v1/selections/industry-rotations/{snapshot_id}", {
		params: { path: { snapshot_id: snapshotId } },
	});
}

export function compareSelectionRuns(beforeRunId: string, afterRunId: string): Promise<SelectionRunDiff> {
	if (!beforeRunId || !afterRunId || beforeRunId === afterRunId) {
		throw new Error("selection comparison requires distinct exact run IDs");
	}
	return apiClient.get("/api/v1/selections/runs/{before_run_id}/compare/{after_run_id}", {
		params: { path: { before_run_id: beforeRunId, after_run_id: afterRunId } },
	});
}

export function createSelectionRun(body: CreateSelectionRunBody): Promise<SelectionWorkspaceReceipt> {
	return apiClient.post("/api/v1/selections/runs", { body });
}

export function assessSelectionAdmission(body: CreateSelectionRunBody, instrumentId?: number) {
	return apiClient.post("/api/v1/selections/admission", {
		body,
		params: { query: instrumentId === undefined ? {} : { instrument_id: instrumentId } },
	});
}

export async function resolveSelectionUniverse(input: CreateSelectionRunBody) {
	if (!input.universe_sources) throw new Error("输入包缺少历史证券池来源");
	const asOf = new Intl.DateTimeFormat("en-CA", {
		timeZone: "Asia/Shanghai",
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
	}).format(new Date(input.as_of));
	const value = await apiClient.post("/api/v1/universes/{universe_id}/history", {
		params: { path: { universe_id: input.universe_sources.universe_id } },
		body: {
			sources: input.universe_sources,
			as_of: asOf,
			knowledge_cutoff: input.knowledge_cutoff,
			publication_cutoff: input.publication_cutoff,
		},
	});
	if (
		!/^universe:sha256:[a-f0-9]{64}$/.test(value.snapshot_id) ||
		value.rule_version !== "historical-universe-v1" ||
		value.as_of !== asOf ||
		Date.parse(value.knowledge_cutoff) !== Date.parse(input.knowledge_cutoff) ||
		Date.parse(value.publication_cutoff) !== Date.parse(input.publication_cutoff) ||
		!value.sources ||
		(["universe_id", "asset_kind", "index_id"] as const).some(
			(key) => (value.sources[key] ?? null) !== (input.universe_sources?.[key] ?? null),
		) ||
		(["master_snapshot_ids", "status_snapshot_ids", "membership_snapshot_ids"] as const).some(
			(key) => JSON.stringify(value.sources[key] ?? null) !== JSON.stringify(input.universe_sources?.[key] ?? null),
		) ||
		!Array.isArray(value.members) ||
		value.members.some(
			(member) =>
				!Number.isSafeInteger(member.instrument_id) ||
				member.instrument_id <= 0 ||
				typeof member.investable !== "boolean" ||
				!Array.isArray(member.exclusion_reasons) ||
				member.exclusion_reasons.some((reason) => typeof reason !== "string" || !reason) ||
				member.investable !== (member.exclusion_reasons.length === 0),
		) ||
		new Set(value.members.map((member) => member.instrument_id)).size !== value.members.length
	)
		throw new Error("历史证券池响应的身份或投资资格无效");
	return {
		snapshotId: value.snapshot_id,
		asOf: value.as_of,
		knowledgeCutoff: value.knowledge_cutoff,
		publicationCutoff: value.publication_cutoff,
		members: value.members.map((member) => ({
			instrumentId: member.instrument_id,
			investable: member.investable,
			reasons: member.exclusion_reasons.join("、") || "符合历史池条件",
		})),
	};
}

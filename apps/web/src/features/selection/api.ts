import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

export type AssembledSelectionRunResponse = components["schemas"]["AssembledSelectionRunResponse"];
export type AssembleSelectionRunBody = components["schemas"]["AssembleSelectionRunBody"];
export type CreateResearchCaseBody = components["schemas"]["CreateResearchCaseBody"];
export type IndustryRotation = components["schemas"]["IndustryRotationResponse"];
export type ResearchCase = components["schemas"]["ResearchCaseResponse"];
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
	researchCases: (runId: string) => [...selectionKeys.all, "research-cases", runId] as const,
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

export function createSelectionRun(body: AssembleSelectionRunBody): Promise<SelectionWorkspaceReceipt> {
	return apiClient.post("/api/v1/selections/runs", { body });
}

export function assembleSelectionRun(body: AssembleSelectionRunBody): Promise<AssembledSelectionRunResponse> {
	return apiClient.post("/api/v1/selections/runs:assembled", { body });
}

export interface UniverseOption {
	readonly universeId: string;
	readonly name: string;
	readonly universeType: string;
}

export async function listUniverseOptions(): Promise<UniverseOption[]> {
	// 服务端默认每页 20 条：逐页拉全，避免可用池被静默截断。
	const pageSize = 100;
	const rows: components["schemas"]["UniverseResponse"][] = [];
	for (let offset = 0; offset < 10_000; offset += pageSize) {
		const page: components["schemas"]["UniverseResponse"][] = await apiClient.get("/api/v1/universes", {
			params: { query: { limit: pageSize, offset } },
		});
		rows.push(...page);
		if (page.length < pageSize) break;
	}
	return rows.map((row) => ({
		universeId: row.universe_id,
		name: row.name,
		universeType: row.universe_type,
	}));
}

export function createResearchCase(runId: string, body: CreateResearchCaseBody): Promise<ResearchCase> {
	return apiClient.post("/api/v1/selections/runs/{run_id}/research-cases", {
		params: { path: { run_id: runId } },
		body,
	});
}

import { apiClient } from "@/api";
import type { components } from "@/api/generated/schema";

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

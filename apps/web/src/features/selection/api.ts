import { apiClient, withQueryParams } from "@/lib/api-client";
import type { components } from "@/types/generated/api";

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
	return apiClient.get<readonly SelectionRun[]>(withQueryParams("/v1/selections/runs", { limit, spec_id: specId }));
}

export function getSelectionRun(runId: string): Promise<SelectionRun> {
	return apiClient.get<SelectionRun>(`/v1/selections/runs/${encodeURIComponent(runId)}`);
}

export function getIndustryRotation(snapshotId: string): Promise<IndustryRotation> {
	return apiClient.get<IndustryRotation>(`/v1/selections/industry-rotations/${encodeURIComponent(snapshotId)}`);
}

export function compareSelectionRuns(beforeRunId: string, afterRunId: string): Promise<SelectionRunDiff> {
	if (!beforeRunId || !afterRunId || beforeRunId === afterRunId) {
		throw new Error("selection comparison requires distinct exact run IDs");
	}
	return apiClient.get<SelectionRunDiff>(
		`/v1/selections/runs/${encodeURIComponent(beforeRunId)}/compare/${encodeURIComponent(afterRunId)}`,
	);
}

export function createSelectionRun(body: CreateSelectionRunBody): Promise<SelectionWorkspaceReceipt> {
	return apiClient.post<SelectionWorkspaceReceipt>("/v1/selections/runs", body);
}

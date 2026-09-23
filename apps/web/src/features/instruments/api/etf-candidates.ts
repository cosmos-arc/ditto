import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

export type ETFCandidate = components["schemas"]["ETFCandidateResponse"];
export type ETFField = components["schemas"]["ETFFieldResponse"];

export async function fetchETFReferenceSnapshots(cutoff: string): Promise<string[]> {
	const response = await apiClient.getPayload("/api/v1/metadata/etf-reference-snapshots", {
		params: { query: { cutoff } },
	});
	return response.data;
}

export async function fetchETFCandidates(query: {
	readonly asof: string;
	readonly cutoff: string;
	readonly sourceSnapshotId: string;
	readonly exposure?: string;
	readonly search?: string;
	readonly sortField?: string;
}): Promise<ETFCandidate[]> {
	const response = await apiClient.getPayload("/api/v1/metadata/etf-candidates", {
		params: {
			query: {
				asof: query.asof,
				cutoff: query.cutoff,
				source_snapshot_id: query.sourceSnapshotId,
				...(query.exposure ? { exposure: query.exposure } : {}),
				...(query.search ? { search: query.search } : {}),
				...(query.sortField ? { sort_field: query.sortField } : {}),
			},
		},
	});
	return response.data;
}

import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

type CandidateDTO = components["schemas"]["ETFCandidateResponse"];
type FieldDTO = components["schemas"]["ETFFieldResponse"];

export type ETFField = {
	readonly value: FieldDTO["value"];
	readonly unit: string | null;
	readonly observedOn: string | null;
	readonly publishedAt: string | null;
	readonly source: string | null;
	readonly sourceSnapshotId: string | null;
	readonly eligibility: string | null;
	readonly eligibilityReasons: readonly string[];
	readonly missingReason: string | null;
	readonly sampleCount: number | null;
	readonly effectiveFrom: string | null;
	readonly effectiveTo: string | null;
};

export type ETFCandidate = {
	readonly instrumentId: number;
	readonly ticker: string;
	readonly name: string;
	readonly exchange: string;
	readonly isActiveCurrent: boolean;
	readonly fields: Record<string, ETFField>;
};

function toField(field: FieldDTO): ETFField {
	return {
		value: field.value,
		unit: field.unit,
		observedOn: field.observed_on,
		publishedAt: field.published_at,
		source: field.source,
		sourceSnapshotId: field.source_snapshot_id,
		eligibility: field.eligibility,
		eligibilityReasons: field.eligibility_reasons ?? [],
		missingReason: field.missing_reason,
		sampleCount: field.sample_count ?? null,
		effectiveFrom: field.effective_from ?? null,
		effectiveTo: field.effective_to ?? null,
	};
}

function toCandidate(candidate: CandidateDTO): ETFCandidate {
	return {
		instrumentId: candidate.instrument_id,
		ticker: candidate.ticker,
		name: candidate.name,
		exchange: candidate.exchange,
		isActiveCurrent: candidate.is_active,
		fields: Object.fromEntries(Object.entries(candidate.fields).map(([key, value]) => [key, toField(value)])),
	};
}

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
	readonly assetExposure?: string;
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
				...(query.assetExposure ? { asset_exposure: query.assetExposure } : {}),
				...(query.search ? { search: query.search } : {}),
				...(query.sortField ? { sort_field: query.sortField } : {}),
			},
		},
	});
	return response.data.map(toCandidate);
}

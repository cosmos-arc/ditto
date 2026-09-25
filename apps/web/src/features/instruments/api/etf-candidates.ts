import type { components } from "@/api/generated/schema";
import { apiClient } from "@/api/transport";

type CandidateDTO = components["schemas"]["ETFCandidateResponse"];
type FieldDTO = components["schemas"]["ETFFieldResponse"];
type TrackingDTO = components["schemas"]["ETFTrackingResponse"];

export type ETFTracking = {
	readonly status: TrackingDTO["status"];
	readonly reason: string | null;
	readonly trackingDeviationPct: number | null;
	readonly trackingErrorPct: number | null;
	readonly sampleCount: number;
	readonly start: string | null;
	readonly end: string | null;
	readonly currency: string | null;
	readonly benchmarkId: string | null;
	readonly sourceSnapshotId: string | null;
	readonly calendarSnapshotIds: readonly string[];
	readonly method: string;
};

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
	readonly tracking: ETFTracking | null;
};

function toTracking(value: TrackingDTO | null | undefined): ETFTracking | null {
	if (!value) return null;
	return {
		status: value.status,
		reason: value.reason,
		trackingDeviationPct: value.tracking_deviation_pct ?? null,
		trackingErrorPct: value.tracking_error_pct ?? null,
		sampleCount: value.sample_count,
		start: value.start ?? null,
		end: value.end ?? null,
		currency: value.currency ?? null,
		benchmarkId: value.benchmark_id ?? null,
		sourceSnapshotId: value.source_snapshot_id ?? null,
		calendarSnapshotIds: value.calendar_snapshot_ids ?? [],
		method: value.method,
	};
}

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
		tracking: toTracking(candidate.tracking),
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
